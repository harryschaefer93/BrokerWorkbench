"""
Claims Impact Agent

Analyzes how claims history affects renewal pricing and provides
mitigation strategies and carrier recommendations.
"""
import json
from typing import List, Dict, Any, Optional

from openai import AsyncAzureOpenAI
from azure.identity import get_bearer_token_provider

from .config import AGENT_CONFIGS, AgentConfig, get_credential
from .tools import TOOL_DEFINITIONS, execute_tool


class ClaimsImpactAgent:
    """Agent that analyzes claims impact on renewals."""
    
    def __init__(self, config: Optional[AgentConfig] = None):
        self.config = config or AgentConfig.from_env()
        self.agent_config = AGENT_CONFIGS["claims_impact"]
        self.name = self.agent_config["name"]
        self.instructions = self.agent_config["instructions"]
        self.available_tools = [
            "get_client_info",
            "get_client_policies",
            "get_claims_history",
            "get_loss_ratio_trend",
            "get_carriers_for_policy_type",
            "get_renewals_by_urgency",
            "get_policy_details",
        ]
    
    def get_tool_definitions(self) -> List[Dict[str, Any]]:
        tools = []
        for t in TOOL_DEFINITIONS:
            if t["name"] in self.available_tools:
                tools.append({
                    "type": "function",
                    "function": {
                        "name": t["name"],
                        "description": t["description"],
                        "parameters": t["parameters"]
                    }
                })
        return tools
    
    def handle_tool_call(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        if tool_name not in self.available_tools:
            return json.dumps({"error": f"Tool not available: {tool_name}"})
        return execute_tool(tool_name, arguments)
    
    async def run(self, user_message: str, conversation_id: Optional[str] = None) -> Dict[str, Any]:
        token_provider = get_bearer_token_provider(
            get_credential(),
            "https://cognitiveservices.azure.com/.default"
        )
        
        client = AsyncAzureOpenAI(
            azure_endpoint=self.config.endpoint,
            azure_ad_token_provider=token_provider,
            api_version=self.config.api_version
        )
        
        messages = [
            {"role": "system", "content": self.instructions},
            {"role": "user", "content": user_message}
        ]
        
        tools = self.get_tool_definitions()
        
        response = await client.chat.completions.create(
            model=self.config.model_deployment,
            messages=messages,
            tools=tools if tools else None,
            tool_choice="auto" if tools else None,
            max_tokens=self.config.max_tokens,
            temperature=self.config.temperature
        )
        
        assistant_message = response.choices[0].message
        
        while assistant_message.tool_calls:
            messages.append({
                "role": "assistant",
                "content": assistant_message.content,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments
                        }
                    }
                    for tc in assistant_message.tool_calls
                ]
            })
            
            for tool_call in assistant_message.tool_calls:
                func_name = tool_call.function.name
                func_args = json.loads(tool_call.function.arguments)
                result = self.handle_tool_call(func_name, func_args)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": result
                })
            
            response = await client.chat.completions.create(
                model=self.config.model_deployment,
                messages=messages,
                tools=tools if tools else None,
                tool_choice="auto" if tools else None,
                max_tokens=self.config.max_tokens,
                temperature=self.config.temperature
            )
            
            assistant_message = response.choices[0].message
        
        return {
            "response": assistant_message.content or "I couldn't generate a response.",
            "conversation_id": conversation_id,
            "agent": self.name,
        }
