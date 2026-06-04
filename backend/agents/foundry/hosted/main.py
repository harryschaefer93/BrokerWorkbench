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

# gpt-5 is a reasoning model; with no cap it defaults to "medium" effort which
# adds multi-second hidden reasoning to EVERY model call in the tool-calling
# loop. Capping the effort is the single biggest interactive-latency lever for
# the M365 Copilot / Teams / Web surfaces. "low" keeps enough reasoning for the
# agent to make sound MCP tool-call decisions while cutting reasoning tokens
# ~3x vs medium and ~10x vs high (measured on the SC gpt-5 deployment).
_VALID_REASONING_EFFORTS = {"minimal", "low", "medium", "high"}


def _reasoning_options() -> dict:
    """Return Agent ``default_options`` for the configured reasoning effort.

    Controlled by ``AGENT_REASONING_EFFORT`` (default ``low``). Set to
    ``default`` (or any unrecognized value) to omit the option entirely and
    fall back to the model/SDK default.
    """
    effort = os.getenv("AGENT_REASONING_EFFORT", "low").strip().lower()
    if effort not in _VALID_REASONING_EFFORTS:
        logger.info("AGENT_REASONING_EFFORT=%s -> using model default", effort)
        return {}
    logger.info("Hosted agent reasoning effort capped at '%s'", effort)
    return {"reasoning": {"effort": effort}}


def _build_chat_client():
    """Construct the chat client used by all specialists.

    In Foundry-hosted mode we use ``FoundryChatClient`` so the platform's
    own gateway handles token audience + model routing (it reads
    ``FOUNDRY_PROJECT_ENDPOINT`` + ``AZURE_AI_MODEL_DEPLOYMENT_NAME``
    auto-injected by the host). This matches the pattern in every
    foundry-samples hosted-agent sample.
    """
    project_endpoint = os.environ.get("FOUNDRY_PROJECT_ENDPOINT")
    model = (
        os.environ.get("AZURE_AI_MODEL_DEPLOYMENT_NAME")  # platform-injected
        or os.environ.get("AZURE_AI_MODEL_DEPLOYMENT")     # our manifest var
        or "gpt-5"
    )
    if not project_endpoint:
        # Local dev fallback: use the existing OpenAIChatCompletionClient path.
        from agents.foundry.chat_client import build_chat_client
        return build_chat_client()

    # Map FOUNDRY_AGENT_INSTANCE_CLIENT_ID -> AZURE_CLIENT_ID for any
    # downstream code that reads AZURE_CLIENT_ID.
    inst = os.environ.get("FOUNDRY_AGENT_INSTANCE_CLIENT_ID")
    if inst and not os.environ.get("AZURE_CLIENT_ID"):
        os.environ["AZURE_CLIENT_ID"] = inst

    from agent_framework.foundry import FoundryChatClient
    from azure.identity import DefaultAzureCredential

    logger.info(
        "Hosted FoundryChatClient: project=%s model=%s", project_endpoint, model
    )
    return FoundryChatClient(
        project_endpoint=project_endpoint,
        model=model,
        credential=DefaultAzureCredential(),
    )


async def _build_workflow_agent():
    """Build the hosted-mode agent.

    HOSTED MODE — single-agent (triage only).
    The previous multi-agent HandoffBuilder workflow emits internal
    ``request_info`` events on turn completion, which the hosted Foundry
    Responses server serializes as ``mcp_approval_request`` output items.
    M365 Copilot's V2 ``ResponseObject`` deserializer rejects those with
    HTTP 500 ("JSON value could not be converted"). To keep all three
    surfaces (M365, Teams, Web) on a clean event stream we expose the
    triage agent directly. The triage prompt already calls MCP tools for
    renewals / clients / policies, and our handoff-discipline prompt
    instructs it NOT to invoke handoff tools after answering. Specialists
    remain in the codebase for legacy ``AGENT_BACKEND_MODE=fastapi`` use
    only.

    NOTE: we do NOT enter the MCP context here — the platform's readiness
    probe must succeed before any I/O work. The agent_framework opens
    MCP lazily per-request via the tool's ``__aenter__``.
    """
    from agents.config import AGENT_CONFIGS
    from agents.foundry.handoff import InstrumentedMCPTool, DEFAULT_MCP_URL
    from agent_framework import Agent
    import os

    chat_client = _build_chat_client()
    resolved_url = os.getenv("MCP_SERVER_URL", DEFAULT_MCP_URL)
    logger.info("Hosted single-agent: MCP server URL=%s", resolved_url)

    mcp_tool = InstrumentedMCPTool(
        name="brokerworkbench",
        url=resolved_url,
        description=(
            "BrokerWorkbench insurance data (clients, policies, claims, carriers)."
        ),
        approval_mode="never_require",
        additional_properties={"require_approval": "never"},
    )

    cfg = AGENT_CONFIGS["triage"]
    # Build the Agent inline (NOT via build_triage_agent) to avoid:
    #   - require_per_service_call_history_persistence=True, which is a
    #     HandoffBuilder-only flag and double-persists with Foundry's
    #     own storage provider in hosted mode (intermittent HTTP 500s)
    #   - post-construction `agent.name = ...` mutation which can
    #     desync conversation-state keys
    return Agent(
        chat_client,
        cfg["instructions"],
        name="brokerworkbench",
        description=cfg["description"],
        tools=mcp_tool,
        default_options=_reasoning_options() or None,
    )



def main() -> None:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s :: %(message)s",
        force=True,
    )
    # Emit a clear startup banner to stdout so even raw container logs show
    # *something* if telemetry never wires up.
    import sys
    sys.stderr.write(
        "BROKERWORKBENCH HOSTED-AGENT BOOTING\n"
        f"  FOUNDRY_PROJECT_ENDPOINT={os.environ.get('FOUNDRY_PROJECT_ENDPOINT','<unset>')}\n"
        f"  AZURE_AI_FOUNDRY_ENDPOINT={os.environ.get('AZURE_AI_FOUNDRY_ENDPOINT','<unset>')}\n"
        f"  AZURE_AI_MODEL_DEPLOYMENT={os.environ.get('AZURE_AI_MODEL_DEPLOYMENT','<unset>')}\n"
        f"  MCP_SERVER_URL={os.environ.get('MCP_SERVER_URL','<unset>')}\n"
        f"  AZURE_CLIENT_ID={os.environ.get('AZURE_CLIENT_ID','<unset>')}\n"
        f"  FOUNDRY_AGENT_INSTANCE_CLIENT_ID={os.environ.get('FOUNDRY_AGENT_INSTANCE_CLIENT_ID','<unset>')}\n"
    )
    sys.stderr.flush()

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
            try:
                async for item in super()._handle_inner_agent(request, context):
                    yield item
            except Exception as exc:  # noqa: BLE001
                logger.exception("inner agent failed")
                sys.stderr.write(f"HOSTED AGENT REQUEST FAILED: {exc!r}\n")
                sys.stderr.flush()
                raise

    try:
        agent = asyncio.run(_build_workflow_agent())
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(f"BUILD WORKFLOW AGENT FAILED: {exc!r}\n")
        sys.stderr.flush()
        raise

    server = _ResilientResponsesHostServer(agent)
    server.run()


if __name__ == "__main__":
    main()
