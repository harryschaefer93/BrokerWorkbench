"""
Quote Comparison Agent

Helps insurance brokers compare quotes across multiple carriers to find
the best rates and coverage options for their clients.
"""
import json
from typing import List, Dict, Any, Optional

from openai import AsyncAzureOpenAI
from azure.identity import get_bearer_token_provider

from .config import AGENT_CONFIGS, AgentConfig, get_credential
from .tools import TOOL_DEFINITIONS, execute_tool


class QuoteComparisonAgent:
    """
    Agent that compares insurance quotes across carriers.
    
    This agent can:
    - Look up client information and current policies
    - Find carriers that offer specific policy types
    - Compare rates across multiple carriers
    - Provide recommendations based on coverage and price
    """
    
    def __init__(self, config: Optional[AgentConfig] = None):
        """Initialize the Quote Comparison Agent."""
        self.config = config or AgentConfig.from_env()
        self.agent_config = AGENT_CONFIGS["quote_comparison"]
        self.name = self.agent_config["name"]
        self.instructions = self.agent_config["instructions"]
        
        # Tools this agent can use
        self.available_tools = [
            "get_client_info",
            "get_client_policies", 
            "get_carriers_for_policy_type",
            "compare_carrier_rates",
            "get_policy_details",
        ]
    
    def get_tool_definitions(self) -> List[Dict[str, Any]]:
        """Get the tool definitions in OpenAI function format."""
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
        """Execute a tool call and return the result."""
        if tool_name not in self.available_tools:
            return json.dumps({"error": f"Tool not available: {tool_name}"})
        return execute_tool(tool_name, arguments)
    
    async def run(self, user_message: str, conversation_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Run the agent using Azure OpenAI with function calling.
        
        Args:
            user_message: The user's query
            conversation_id: Optional existing conversation to continue
        
        Returns:
            Agent response with any tool calls resolved
        """
        # Set up Azure OpenAI client with Entra (Azure AD) token.
        # Credential source is resolved once via the shared factory (SP or CLI).
        token_provider = get_bearer_token_provider(
            get_credential(),
            "https://cognitiveservices.azure.com/.default"
        )
        
        client = AsyncAzureOpenAI(
            azure_endpoint=self.config.endpoint,
            azure_ad_token_provider=token_provider,
            api_version=self.config.api_version
        )
        
        # Build messages
        messages = [
            {"role": "system", "content": self.instructions},
            {"role": "user", "content": user_message}
        ]
        
        # Get tools
        tools = self.get_tool_definitions()
        
        # Initial request
        response = await client.chat.completions.create(
            model=self.config.model_deployment,
            messages=messages,
            tools=tools if tools else None,
            tool_choice="auto" if tools else None,
            max_tokens=self.config.max_tokens,
            temperature=self.config.temperature
        )
        
        assistant_message = response.choices[0].message
        
        # Process tool calls if any
        while assistant_message.tool_calls:
            # Add assistant message to conversation
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
            
            # Execute each tool call
            for tool_call in assistant_message.tool_calls:
                func_name = tool_call.function.name
                func_args = json.loads(tool_call.function.arguments)
                
                # Execute the tool
                result = self.handle_tool_call(func_name, func_args)
                
                # Add tool result to messages
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": result
                })
            
            # Get next response
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
