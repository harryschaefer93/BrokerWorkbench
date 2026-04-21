"""
Triage / Broker Agent

Receives all user messages, classifies intent via a lightweight LLM call,
then either routes to the correct specialist agent or answers directly
for general broker queries.
"""
import json
import logging
from typing import List, Dict, Any, Optional

from openai import AsyncAzureOpenAI
from azure.identity import get_bearer_token_provider

from .config import AGENT_CONFIGS, AgentConfig, get_credential
from .tools import TOOL_DEFINITIONS, execute_tool

logger = logging.getLogger(__name__)

CLASSIFY_SYSTEM_PROMPT = """\
You are a message classifier for an insurance broker workbench. Classify the user's intent into exactly one category.

Categories:
- "claims" → claims history, claims impact on pricing, loss ratios, claims analysis, how claims affect renewals
- "crosssell" → coverage gaps, cross-sell opportunities, missing coverage, what additional insurance a client needs
- "quote" → compare quotes, get pricing, carrier rates, find the best rate, premium comparison
- "general" → renewals, upcoming renewals, policy lookups, client info, general book-of-business questions, dashboard-type queries, "what can you help with", greetings, anything that doesn't fit the above

Respond with JSON only: {"intent": "<category>", "confidence": "high" | "medium" | "low"}
"""


class TriageAgent:
    """Agent that classifies intent and routes to specialists or answers directly."""

    def __init__(self, config: Optional[AgentConfig] = None):
        self.config = config or AgentConfig.from_env()
        self.agent_config = AGENT_CONFIGS["triage"]
        self.name = self.agent_config["name"]
        self.instructions = self.agent_config["instructions"]
        self.available_tools = [
            "get_client_info",
            "get_client_policies",
            "get_claims_history",
            "get_carriers_for_policy_type",
            "get_renewals_by_urgency",
            "get_policy_details",
            "get_coverage_gaps",
            "compare_carrier_rates",
            "get_all_clients",
        ]

    # ── helpers shared with other agents ────────────────────────────────

    def get_tool_definitions(self) -> List[Dict[str, Any]]:
        tools = []
        for t in TOOL_DEFINITIONS:
            if t["name"] in self.available_tools:
                tools.append({
                    "type": "function",
                    "function": {
                        "name": t["name"],
                        "description": t["description"],
                        "parameters": t["parameters"],
                    },
                })
        return tools

    def handle_tool_call(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        if tool_name not in self.available_tools:
            return json.dumps({"error": f"Tool not available: {tool_name}"})
        return execute_tool(tool_name, arguments)

    # ── classification ──────────────────────────────────────────────────

    async def classify(self, user_message: str) -> Dict[str, str]:
        """Cheap LLM call to classify intent.

        Returns e.g. {"intent": "claims", "confidence": "high"}
        """
        token_provider = get_bearer_token_provider(
            get_credential(), "https://cognitiveservices.azure.com/.default"
        )
        client = AsyncAzureOpenAI(
            azure_endpoint=self.config.endpoint,
            azure_ad_token_provider=token_provider,
            api_version=self.config.api_version,
        )

        response = await client.chat.completions.create(
            model=self.config.model_deployment,
            messages=[
                {"role": "system", "content": CLASSIFY_SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            max_tokens=100,
            temperature=0.1,
            response_format={"type": "json_object"},
        )

        raw = response.choices[0].message.content or "{}"
        try:
            result = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("Classification returned non-JSON: %s", raw)
            result = {"intent": "general", "confidence": "low"}

        # Validate
        valid_intents = {"claims", "crosssell", "quote", "general"}
        if result.get("intent") not in valid_intents:
            logger.warning("Invalid intent '%s', falling back to general", result.get("intent"))
            result["intent"] = "general"

        logger.info("Triage classification: %s", result)
        return result

    # ── non-streaming run (used by POST /api/agent/chat) ────────────────

    async def run(self, user_message: str, conversation_id: Optional[str] = None) -> Dict[str, Any]:
        classification = await self.classify(user_message)
        intent = classification["intent"]

        if intent != "general":
            # Delegate to specialist
            from .claims_agent import ClaimsImpactAgent
            from .crosssell_agent import CrossSellAgent
            from .quote_agent import QuoteComparisonAgent

            specialists = {
                "claims": ClaimsImpactAgent,
                "crosssell": CrossSellAgent,
                "quote": QuoteComparisonAgent,
            }
            agent_cls = specialists[intent]
            agent = agent_cls(config=self.config)
            return await agent.run(user_message, conversation_id=conversation_id)

        # General: answer directly
        token_provider = get_bearer_token_provider(
            get_credential(), "https://cognitiveservices.azure.com/.default"
        )
        client = AsyncAzureOpenAI(
            azure_endpoint=self.config.endpoint,
            azure_ad_token_provider=token_provider,
            api_version=self.config.api_version,
        )

        messages = [
            {"role": "system", "content": self.instructions},
            {"role": "user", "content": user_message},
        ]
        tools = self.get_tool_definitions()

        response = await client.chat.completions.create(
            model=self.config.model_deployment,
            messages=messages,
            tools=tools if tools else None,
            tool_choice="auto" if tools else None,
            max_tokens=self.config.max_tokens,
            temperature=self.config.temperature,
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
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in assistant_message.tool_calls
                ],
            })
            for tool_call in assistant_message.tool_calls:
                func_args = json.loads(tool_call.function.arguments)
                result = self.handle_tool_call(tool_call.function.name, func_args)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": result,
                })

            response = await client.chat.completions.create(
                model=self.config.model_deployment,
                messages=messages,
                tools=tools if tools else None,
                tool_choice="auto" if tools else None,
                max_tokens=self.config.max_tokens,
                temperature=self.config.temperature,
            )
            assistant_message = response.choices[0].message

        return {
            "response": assistant_message.content or "I couldn't generate a response.",
            "conversation_id": conversation_id,
            "agent": self.name,
        }
