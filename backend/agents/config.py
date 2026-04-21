"""
Configuration for Azure AI Foundry Agents

This module handles the connection to Azure AI Foundry and provides
configuration for all agents in the Broker Workbench.
"""
import logging
import os
from dataclasses import dataclass
from pathlib import Path

# Load .env from project root
from dotenv import load_dotenv
env_path = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(env_path)

logger = logging.getLogger(__name__)


@dataclass
class AgentConfig:
    """Configuration settings for Azure AI Foundry agents."""
    
    # Azure AI Foundry connection
    endpoint: str
    model_deployment: str
    
    # Optional settings
    api_version: str = "2024-12-01-preview"
    max_tokens: int = 4096
    temperature: float = 0.4
    
    @classmethod
    def from_env(cls) -> "AgentConfig":
        """Load configuration from environment variables."""
        endpoint = os.getenv("AZURE_AI_FOUNDRY_ENDPOINT")
        model = os.getenv("AZURE_AI_MODEL_DEPLOYMENT", "gpt-4o")
        
        if not endpoint:
            raise ValueError(
                "AZURE_AI_FOUNDRY_ENDPOINT environment variable is required. "
                "Set it to your Azure AI Foundry project endpoint."
            )
        
        return cls(
            endpoint=endpoint,
            model_deployment=model,
            api_version=os.getenv("AZURE_AI_API_VERSION", "2024-12-01-preview"),
            max_tokens=int(os.getenv("AZURE_AI_MAX_TOKENS", "4096")),
            temperature=float(os.getenv("AZURE_AI_TEMPERATURE", "0.7")),
        )


def get_credential():
    """
    Return an Azure token credential suitable for the running environment.

    Credential resolution order (first that succeeds wins):

    1. EnvironmentCredential     — Service principal via AZURE_CLIENT_ID +
                                   AZURE_TENANT_ID + AZURE_CLIENT_SECRET (or CERT).
                                   Use this for CI pipelines or shared dev SPs.

    2. ManagedIdentityCredential — Used automatically in Azure Container Apps /
                                   Azure VMs / App Service. The Bicep sets
                                   AZURE_CLIENT_ID to the user-assigned managed
                                   identity's client ID so the correct identity is
                                   selected when multiple are present.

    3. AzureCliCredential        — Local development fallback. Reads the token
                                   cache produced by `az login` on the host.
                                   In Docker the cache is mounted to
                                   /home/appuser/.azure and AZURE_CONFIG_DIR is
                                   set to that path by docker-compose.

    This explicit chain is more predictable than DefaultAzureCredential (which
    probes ~10 sources) and makes it obvious in logs which path succeeded.
    """
    from azure.identity import (
        ChainedTokenCredential,
        EnvironmentCredential,
        ManagedIdentityCredential,
        AzureCliCredential,
    )

    client_id = os.getenv("AZURE_CLIENT_ID")
    has_sp_secret = bool(
        client_id
        and os.getenv("AZURE_TENANT_ID")
        and (os.getenv("AZURE_CLIENT_SECRET") or os.getenv("AZURE_CLIENT_CERTIFICATE_PATH"))
    )

    if has_sp_secret:
        logger.info("Entra auth: AZURE_CLIENT_ID+SECRET set — EnvironmentCredential (SP) is primary.")
    elif client_id:
        logger.info(
            "Entra auth: AZURE_CLIENT_ID=%s set without SECRET — "
            "ManagedIdentityCredential (user-assigned) is primary (Container Apps path).",
            client_id,
        )
    else:
        logger.info(
            "Entra auth: no AZURE_CLIENT_ID — AzureCliCredential is primary (local dev path). "
            "Ensure 'az login' was run on the host and ~/.azure is mounted "
            "(AZURE_CONFIG_DIR=%s).",
            os.getenv("AZURE_CONFIG_DIR", "~/.azure (default)"),
        )

    # ManagedIdentityCredential respects AZURE_CLIENT_ID to select a specific
    # user-assigned identity; passing client_id=None falls back to system-assigned.
    return ChainedTokenCredential(
        EnvironmentCredential(),
        ManagedIdentityCredential(client_id=client_id),
        AzureCliCredential(),
    )


def get_project_client():
    """
    Create and return an AIProjectClient for Azure AI Foundry.
    
    Returns:
        AIProjectClient configured with credentials from environment.
    """
    from azure.ai.projects import AIProjectClient
    
    config = AgentConfig.from_env()
    credential = get_credential()
    
    return AIProjectClient(
        endpoint=config.endpoint,
        credential=credential,
    )


# Agent-specific configurations
AGENT_CONFIGS = {
    "quote_comparison": {
        "name": "QuoteComparisonAgent",
        "description": "Compares insurance quotes across multiple carriers to find the best rates and coverage options for clients.",
        "instructions": """You are a senior insurance broker's quote analyst. When a broker asks you to compare quotes, pull the relevant data using your tools and give them a clear, concise answer.

Use a markdown table when comparing carriers side-by-side. After the table, give your recommendation in 1-2 sentences and flag any coverage gaps worth noting.

Write like a sharp colleague on Slack — direct, no filler. Never use slide-deck formatting, numbered sections, or headers like "Section 1". Keep it under 300 words unless the broker asks for more detail."""
    },
    
    "cross_sell": {
        "name": "CrossSellAgent", 
        "description": "Identifies coverage gaps and cross-sell opportunities for existing clients.",
        "instructions": """You are a coverage gap analyst for an insurance brokerage. When asked about a client, pull their portfolio using your tools and identify what's missing.

Lead with the most important gap first. Use bold text for urgency — e.g. **No cyber liability coverage** — followed by a brief explanation of why it matters for their industry.

Keep responses tight. Use a short table if comparing multiple gaps, otherwise 2-3 short paragraphs max. Write like you're briefing a broker before a client meeting — no corporate fluff, no slide-deck formatting, no numbered sections."""
    },
    
    "triage": {
        "name": "BrokerAgent",
        "description": "Routes questions to the right specialist and handles general broker queries.",
        "instructions": """You are BrokerHub's AI assistant \u2014 a knowledgeable insurance broker's right hand. You handle general book-of-business queries directly: policy lookups, renewal timelines, client info, and dashboard summaries.

When asked about claims impact, loss ratios, or how claims affect pricing, defer to the Claims specialist. When asked to compare quotes or find the best rate, defer to the Quote specialist. When asked about coverage gaps or cross-sell opportunities, defer to the Cross-Sell specialist.

For everything else \u2014 renewals, client lookups, policy details, general questions \u2014 answer directly using your tools.

Use markdown tables for data. Be direct and concise, like a sharp colleague briefing you before a meeting. Keep responses under 300 words."""
    },

    "claims_impact": {
        "name": "ClaimsImpactAgent",
        "description": "Analyzes how claims history affects renewal pricing and provides mitigation strategies.",
        "instructions": """You are a claims and renewal pricing analyst for an insurance brokerage. When asked about a client's claims impact, pull their data using your tools and give the broker a straight answer.

Lead with the bottom line — expected premium impact as a percentage range. Then briefly explain what's driving it (frequency, severity, loss ratio). End with 2-3 concrete actions the client can take to improve their position.

When asked about renewal timelines, use the get_renewals_by_urgency tool and present the results as a clear timeline sorted by date. Always trust the data your tools return — if the tool returns renewal data, present it. Never say "technical issue" or "unable to access data" when a tool returns valid results.

Keep it under 250 words. Use bold for key numbers. Use a markdown table for timelines and comparisons. Write conversationally — like you're briefing a colleague, not presenting to a board. No slide decks, no numbered sections, no headers like "Recommendations" or "Next Steps"."""
    }
}
