"""Microsoft Agent Framework HandoffBuilder orchestration for BrokerWorkbench.

Builds a :class:`agent_framework_orchestrations.HandoffBuilder` workflow that
contains the four BrokerWorkbench specialist agents — Triage (start), Claims,
Quote, CrossSell — all sharing a single ``MCPStreamableHTTPTool`` pointed at
the existing local MCP server.

This module returns the :class:`Workflow` together with the MCP tool so the
caller can manage the ``async with mcp_tool: ...`` lifecycle. No FastAPI
router rewire, no container packaging, no Foundry deploy — orchestration
code ONLY (Phase A sub-step 2).

API notes (Agent Framework 1.6.0):
    * ``HandoffBuilder`` ships in the separate ``agent-framework-orchestrations``
      package and is re-exported via ``agent_framework.orchestrations``.
    * The graph of allowed transitions is declared with
      :meth:`HandoffBuilder.add_handoff`; the ``participants=`` kwarg alone
      does not establish edges.
    * Triage runs in autonomous mode so it routes without waiting for a
      synthetic user turn.
"""
from __future__ import annotations

import logging
import os
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

DEFAULT_MCP_URL = "http://localhost:8001/mcp"
DEFAULT_WORKFLOW_NAME = "brokerworkbench_handoff"
AUTONOMOUS_PROMPT = "Continue with your best judgment as the user is unavailable."


async def build_handoff(
    chat_client=None,
    mcp_url: Optional[str] = None,
) -> Tuple["object", "object"]:
    """Build the BrokerWorkbench handoff workflow.

    Args:
        chat_client: Optional pre-built Agent Framework chat client. When
            ``None``, one is constructed via :func:`build_chat_client`.
        mcp_url: Override for the MCP server URL. Defaults to
            ``MCP_SERVER_URL`` env var, then ``http://localhost:8001/mcp``.

    Returns:
        A ``(workflow, mcp_tool)`` tuple. The caller MUST drive
        ``async with mcp_tool: ...`` before running the workflow so the MCP
        connection is opened (and torn down) correctly.
    """
    from agent_framework import MCPStreamableHTTPTool
    from agent_framework.orchestrations import HandoffBuilder

    from .chat_client import build_chat_client
    from .specialists import (
        build_claims_agent,
        build_crosssell_agent,
        build_quote_agent,
        build_triage_agent,
    )

    if chat_client is None:
        chat_client = build_chat_client()

    resolved_url = mcp_url or os.getenv("MCP_SERVER_URL", DEFAULT_MCP_URL)
    logger.info("Foundry handoff: MCP server URL=%s", resolved_url)

    mcp_tool = MCPStreamableHTTPTool(
        name="brokerworkbench",
        url=resolved_url,
        description="BrokerWorkbench insurance data (clients, policies, claims, carriers).",
    )

    triage = build_triage_agent(chat_client, mcp_tool)
    claims = build_claims_agent(chat_client, mcp_tool)
    quote = build_quote_agent(chat_client, mcp_tool)
    crosssell = build_crosssell_agent(chat_client, mcp_tool)

    workflow = (
        HandoffBuilder(
            name=DEFAULT_WORKFLOW_NAME,
            participants=[triage, claims, quote, crosssell],
        )
        .with_start_agent(triage)
        .add_handoff(triage, [claims, quote, crosssell])
        .add_handoff(claims, [triage])
        .add_handoff(quote, [triage])
        .add_handoff(crosssell, [triage])
        .with_autonomous_mode(
            agents=[triage],
            prompts={triage.name: AUTONOMOUS_PROMPT},
        )
        .build()
    )

    return workflow, mcp_tool
