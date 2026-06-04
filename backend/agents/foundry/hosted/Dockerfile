# Foundry Hosted-agent container
# Wraps the existing Agent Framework HandoffBuilder workflow
# (backend/agents/foundry/handoff.py) and exposes it as a Foundry
# Hosted agent over the Responses protocol on port 8088.
#
# Deployed to: rg-bwbench-sc (swedencentral)
# Build via:   az acr build -r <acr> -t broker-hosted-agent:sc-v1 -f backend/agents/foundry/hosted/Dockerfile .
# Run via:     ResponsesHostServer(workflow.as_agent()).run()
#
# Reads at runtime (injected by Foundry):
#   FOUNDRY_PROJECT_ENDPOINT       -> not used directly; we use FoundryChatClient internally
#   AZURE_AI_MODEL_DEPLOYMENT_NAME -> Foundry-injected model name
#   APPLICATIONINSIGHTS_CONNECTION_STRING -> auto-wired telemetry
# And our own (set via agent.manifest.yaml or container env):
#   MCP_SERVER_URL                 -> internal http://ca-mcp.../mcp
#   AZURE_CLIENT_ID                -> agent identity (auto-injected by Foundry)

FROM mcr.microsoft.com/devcontainers/python:1-3.12-bookworm AS base
# linux/amd64 required by Foundry Hosted agents

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY backend/agents/foundry/hosted/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy the foundry workflow code (handoff + specialists + chat_client + config).
# We mount it under /app/backend/agents/ to preserve the existing
# `from agents.config import ...` and `from .specialists import ...` imports.
# A synthesized empty backend/__init__.py turns the tree into a real package.
COPY backend/agents /app/backend/agents
RUN touch /app/backend/__init__.py

ENV PYTHONPATH=/app:/app/backend

# Hosted agents serve on 8088.
EXPOSE 8088

CMD ["python", "/app/backend/agents/foundry/hosted/main.py"]
