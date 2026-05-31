"""Foundry Hosted-agent entry point.

Wraps the existing :func:`backend.agents.foundry.handoff.build_handoff`
workflow with the Foundry ``ResponsesHostServer`` so it can be deployed
as a Hosted agent and reached via the OpenAI Responses protocol.

The Foundry hosting platform manages conversation history, streaming
lifecycle, and SSE serialization \u2014 our workflow just needs to be wrapped
with ``.as_agent()`` and handed to ``ResponsesHostServer.run()``.

Workaround applied:
    ``_ResilientResponsesHostServer`` defensively wraps ``context.get_history``
    so a transient platform error degrades to "no prior turns" instead of
    failing the whole request. Matches the pattern used by the upstream
    foundry-samples (``04-foundry-toolbox``, ``07-teams-activity``).

Runtime env (injected by Foundry unless noted):
    FOUNDRY_PROJECT_ENDPOINT
    AZURE_AI_MODEL_DEPLOYMENT_NAME
    AZURE_CLIENT_ID
    APPLICATIONINSIGHTS_CONNECTION_STRING
    MCP_SERVER_URL                  set via agent.manifest.yaml
    AZURE_AI_FOUNDRY_ENDPOINT       set via agent.manifest.yaml (Cognitive
                                    Services account endpoint our chat
                                    client targets via OpenAIChatCompletionClient)
"""
from __future__ import annotations

import asyncio
import logging
import os

logger = logging.getLogger(__name__)


def _build_chat_client():
    """Construct the Azure OpenAI chat client the workflow's specialists share."""
    # Re-use the existing factory so local and hosted both go through the
    # same code path (one less drift surface). PYTHONPATH includes both
    # /app and /app/backend so `agents.foundry.chat_client` resolves.
    from agents.foundry.chat_client import build_chat_client

    return build_chat_client()


async def _build_workflow_agent():
    """Build the handoff workflow and wrap it as an Agent Framework agent."""
    from agents.foundry.handoff import build_handoff

    chat_client = _build_chat_client()
    workflow, mcp_tool, _tool_queue = await build_handoff(chat_client=chat_client)
    # Enter the MCP context so the workflow can call tools throughout the
    # server's lifetime. The container process owns the lifecycle \u2014 we
    # never tear it down.
    await mcp_tool.__aenter__()
    return workflow.as_agent(
        name="brokerworkbench",
        description=(
            "Broker workbench multi-agent (Triage \u2192 Claims | Quote | CrossSell) "
            "backed by the BrokerWorkbench MCP toolbox."
        ),
    )


def main() -> None:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s :: %(message)s",
    )
    # Import here so the binary fails fast with a clear message if the
    # hosting package wasn't installed.
    from agent_framework_foundry_hosting import ResponsesHostServer

    class _ResilientResponsesHostServer(ResponsesHostServer):
        async def _handle_inner_agent(self, request, context):  # type: ignore[override]
            original_get_history = context.get_history

            async def safe_get_history():
                try:
                    return await original_get_history()
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "context.get_history() failed (%s); proceeding with no prior history.",
                        exc,
                    )
                    return []

            context.get_history = safe_get_history  # type: ignore[method-assign]
            async for item in super()._handle_inner_agent(request, context):
                yield item

    agent = asyncio.run(_build_workflow_agent())
    server = _ResilientResponsesHostServer(agent)
    server.run()


if __name__ == "__main__":
    main()
