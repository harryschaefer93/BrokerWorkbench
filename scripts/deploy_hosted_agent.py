"""Deploy the BrokerWorkbench hosted agent to Foundry (Sweden Central).

Pre-reqs (all done):
  - broker-hosted-agent:sc-v1 image pushed to acrbrokerworkbenchdevwnwtqzj2xcdts
  - Foundry project + account MIs granted AcrPull on the ACR
  - User running this has Foundry Project Manager / az login active

Run:
  python scripts/deploy_hosted_agent.py
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

PROJECT_ENDPOINT = (
    "https://ai-brokerworkbench-dev-wnwtqz.cognitiveservices.azure.com"
    "/api/projects/brokerworkbench-agents"
)
FOUNDRY_ACCOUNT_ENDPOINT = (
    "https://ai-brokerworkbench-dev-wnwtqz.cognitiveservices.azure.com"
)
ACR_IMAGE = os.environ.get(
    "HOSTED_AGENT_IMAGE",
    "acrbrokerworkbenchdevwnwtqzj2xcdts.azurecr.io/broker-hosted-agent:sc-v5",
)
AGENT_NAME = "brokerworkbench"
# MCP server now has external ingress (Foundry-managed compute is outside our
# VNet, so internal-only didn't work). Synthetic data only \u2014 see deployment
# notes for the prod hardening checklist (Entra auth in front of MCP).
MCP_URL = (
    "https://ca-mcp-brokerworkbench-dev."
    "kinddune-112ddddc.swedencentral.azurecontainerapps.io/mcp"
)


def main() -> int:
    from azure.ai.projects import AIProjectClient
    from azure.ai.projects.models import (
        AgentProtocol,
        HostedAgentDefinition,
        ProtocolVersionRecord,
    )
    from azure.identity import DefaultAzureCredential

    # Pull our App Insights connection string from env so hosted-agent
    # telemetry lands in OUR resource (not the Foundry-platform default
    # we can't read). Caller is expected to export APPINSIGHTS_CONN before
    # running, e.g.:
    #   $env:APPINSIGHTS_CONN = az monitor app-insights component show \
    #       -g rg-bwbench-sc -a appi-brokerworkbench-dev \
    #       --query connectionString -o tsv
    ai_conn = os.environ.get("APPINSIGHTS_CONN", "")

    credential = DefaultAzureCredential()
    project = AIProjectClient(
        endpoint=PROJECT_ENDPOINT,
        credential=credential,
        allow_preview=True,
    )

    print(f"Creating hosted agent '{AGENT_NAME}' from image {ACR_IMAGE} ...")
    agent = project.agents.create_version(
        agent_name=AGENT_NAME,
        definition=HostedAgentDefinition(
            container_protocol_versions=[
                ProtocolVersionRecord(
                    protocol=AgentProtocol.RESPONSES, version="1.0.0"
                )
            ],
            cpu="1",
            memory="2Gi",
            image=ACR_IMAGE,
            environment_variables={
                "AZURE_AI_FOUNDRY_ENDPOINT": FOUNDRY_ACCOUNT_ENDPOINT,
                "AZURE_AI_MODEL_DEPLOYMENT": "gpt-5",
                "AZURE_AI_API_VERSION": "2025-03-01-preview",
                "MCP_SERVER_URL": MCP_URL,
                "LOG_LEVEL": "INFO",
            },
        ),
    )
    print(f"Created. version={agent.version}, polling for active...")

    deadline = time.time() + 600
    last_status = ""
    while time.time() < deadline:
        info = project.agents.get_version(
            agent_name=AGENT_NAME, agent_version=agent.version
        )
        status = info.get("status") if isinstance(info, dict) else getattr(info, "status", None)
        if status != last_status:
            print(f"  status: {status}")
            last_status = status or ""
        if status == "active":
            print(f"\n[OK] Agent '{AGENT_NAME}' v{agent.version} is active.")
            print(
                f"Endpoint: {PROJECT_ENDPOINT}/agents/{AGENT_NAME}/endpoint"
                "/protocols/openai/responses"
            )
            return 0
        if status == "failed":
            err = info.get("error") if isinstance(info, dict) else getattr(info, "error", None)
            print(f"\n[FAILED] {err}")
            return 1
        time.sleep(5)

    print("[TIMEOUT] waited 10 minutes")
    return 2


if __name__ == "__main__":
    sys.exit(main())
