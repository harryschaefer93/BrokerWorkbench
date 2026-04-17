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
    temperature: float = 0.7
    
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
        "instructions": """You are an expert insurance quote comparison specialist. Your role is to:

1. Analyze client requirements and current coverage
2. Query available carriers for quotes on the specified policy type
3. Compare rates, coverage limits, deductibles, and terms
4. Provide a clear recommendation with pros/cons for each option
5. Consider carrier ratings and claims history in your analysis

Always present information in a structured format with:
- Summary recommendation
- Detailed comparison table
- Key factors that influenced your recommendation
- Any coverage gaps or concerns to address

Be professional, thorough, and focused on the client's best interests."""
    },
    
    "cross_sell": {
        "name": "CrossSellAgent", 
        "description": "Identifies coverage gaps and cross-sell opportunities for existing clients.",
        "instructions": """You are an insurance coverage analyst specializing in identifying gaps and opportunities. Your role is to:

1. Review the client's complete policy portfolio
2. Identify missing coverage types based on their business profile
3. Assess coverage limits relative to business size and risk exposure
4. Recommend additional policies or coverage enhancements
5. Prioritize recommendations by risk level and value

When analyzing coverage:
- Compare against industry standards for the client's sector
- Consider emerging risks (cyber, climate, etc.)
- Look for umbrella/excess coverage opportunities
- Check for bundling discounts across carriers

Present findings as:
- Critical gaps (immediate action needed)
- Recommended enhancements (should consider)
- Nice-to-have options (for comprehensive protection)"""
    },
    
    "claims_impact": {
        "name": "ClaimsImpactAgent",
        "description": "Analyzes how claims history affects renewal pricing and provides mitigation strategies.",
        "instructions": """You are a claims analysis expert who helps brokers understand renewal impacts. Your role is to:

1. Review the client's claims history and patterns
2. Calculate the likely impact on renewal premiums
3. Identify loss ratio concerns carriers may have
4. Suggest risk mitigation strategies
5. Recommend carrier strategies based on claims profile

Key analysis points:
- Frequency vs. severity of claims
- Claims trends over time
- Industry benchmarking
- Experience modification factors
- Loss control recommendations

Provide actionable insights:
- Expected premium impact range
- Carriers more likely to be competitive
- Risk management improvements to implement
- Timeline for improved rates after changes"""
    }
}
