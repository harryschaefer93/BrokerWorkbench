"""Microsoft Agent Framework HandoffBuilder orchestration for BrokerWorkbench.

===========================================================================
DUAL-USE MODULE — read before editing.
===========================================================================

This module is consumed by TWO callers with different runtime characteristics:

1. **Foundry hosted agent image** (`backend/agents/foundry/hosted/main.py`).
   This is the PRODUCTION path for ALL THREE surfaces (M365 Copilot, Teams,
   Web). The workflow built here is wrapped via `workflow.as_agent(name=...)`
   and baked into the `broker-hosted-agent` container that runs inside the
   Foundry project. Changes here ship to prod via:
     az acr build ... -f backend/agents/foundry/hosted/Dockerfile .
     python scripts/deploy_hosted_agent.py    # publishes a new agent version

2. **Legacy local FastAPI mode** (`_stream_handoff` in
   `backend/routers/agents_handoff.py`, gated by `AGENT_BACKEND_MODE=local`).
   NOT used in prod — prod backend runs with `AGENT_BACKEND_MODE=hosted`,
   which makes the backend a thin SSE proxy to the Foundry hosted agent.
   Kept for local development and as a fallback only.

Topology: see `docs/architecture.md`.
===========================================================================

Builds a :class:`agent_framework_orchestrations.HandoffBuilder` workflow that
contains the four BrokerWorkbench specialist agents — Triage (start), Claims,
Quote, CrossSell — all sharing a single ``MCPStreamableHTTPTool`` pointed at
the existing local MCP server.

This module returns the :class:`Workflow` together with the MCP tool so the
caller can manage the ``async with mcp_tool: ...`` lifecycle.

API notes (Agent Framework 1.6.0):
    * ``HandoffBuilder`` ships in the separate ``agent-framework-orchestrations``
      package and is re-exported via ``agent_framework.orchestrations``.
    * The graph of allowed transitions is declared with
      :meth:`HandoffBuilder.add_handoff`; the ``participants=`` kwarg alone
      does not establish edges.
    * Triage runs in autonomous mode so it routes without waiting for a
      synthetic user turn.

Tool instrumentation (Phase B B3):
    Workflow events surface agent transitions but NOT individual MCP tool
    calls — those happen below the event bus, inside the chat client's
    function-calling loop. To expose them as ``tool_call`` / ``tool_result``
    SSE frames we subclass ``MCPStreamableHTTPTool`` and override
    :meth:`call_tool` to publish before/after frames on a per-build
    asyncio.Queue. Callers drain the queue concurrently with the workflow
    event stream.
"""
from __future__ import annotations

import asyncio
import logging
import os
import uuid
from typing import Any, Optional, Tuple

from agent_framework import MCPStreamableHTTPTool

logger = logging.getLogger(__name__)

DEFAULT_MCP_URL = "http://localhost:8001/mcp"
DEFAULT_WORKFLOW_NAME = "brokerworkbench_handoff"
AUTONOMOUS_PROMPT = "Continue with your best judgment as the user is unavailable."

# Cap the stringified tool result we forward over SSE so a giant JSON blob
# doesn't blow the chat panel's payload budget. UI only needs a preview.
_TOOL_SUMMARY_MAX_CHARS = 200


def _short_repr(value: Any, limit: int = _TOOL_SUMMARY_MAX_CHARS) -> str:
    """Return ``repr(value)`` truncated to ``limit`` chars."""
    try:
        r = repr(value)
    except Exception as exc:  # noqa: BLE001 — never let summary code throw
        r = f"<unreprable {type(value).__name__}: {exc}>"
    if len(r) > limit:
        r = r[: limit - 3] + "..."
    return r


class InstrumentedMCPTool(MCPStreamableHTTPTool):
    """``MCPStreamableHTTPTool`` that emits call/result frames to a queue.

    Every invocation of :meth:`call_tool` pushes two events:

    * ``{"kind": "call", "name": ..., "arguments": ..., "call_id": ...}``
    * ``{"kind": "result", "call_id": ..., "ok": bool, "summary": ...}``

    The queue is set via :meth:`bind_queue` after construction so the build
    function can hand the same queue to both the tool and the router.
    Errors still produce a ``result`` frame with ``ok=False``.
    """

    def bind_queue(self, queue: "asyncio.Queue[dict[str, Any]]") -> None:
        # Stored on instance dict (not as a class attr) so each build gets
        # its own queue — important because tools persist across requests
        # only via the build_handoff per-request pattern.
        self._tool_event_queue = queue

    async def call_tool(self, tool_name: str, **kwargs: Any):  # type: ignore[override]
        queue: asyncio.Queue[dict[str, Any]] | None = getattr(
            self, "_tool_event_queue", None
        )
        call_id = uuid.uuid4().hex
        if queue is not None:
            try:
                queue.put_nowait(
                    {
                        "kind": "call",
                        "name": tool_name,
                        "arguments": {
                            k: v
                            for k, v in kwargs.items()
                            # Drop framework-internal kwargs from the wire
                            # payload — matches the parent's own filter.
                            if k
                            not in {
                                "chat_options",
                                "tools",
                                "tool_choice",
                                "session",
                                "thread",
                                "conversation_id",
                                "options",
                                "response_format",
                            }
                        },
                        "call_id": call_id,
                    }
                )
            except Exception:  # noqa: BLE001 — queue.full / serialization
                logger.exception("tool_event queue.put_nowait (call) failed")

        try:
            result = await super().call_tool(tool_name, **kwargs)
            if queue is not None:
                try:
                    queue.put_nowait(
                        {
                            "kind": "result",
                            "call_id": call_id,
                            "ok": True,
                            "summary": _short_repr(result),
                        }
                    )
                except Exception:  # noqa: BLE001
                    logger.exception(
                        "tool_event queue.put_nowait (result) failed"
                    )
            return result
        except Exception as exc:  # noqa: BLE001 — must re-raise to caller
            if queue is not None:
                try:
                    queue.put_nowait(
                        {
                            "kind": "result",
                            "call_id": call_id,
                            "ok": False,
                            "summary": str(exc)[:_TOOL_SUMMARY_MAX_CHARS],
                        }
                    )
                except Exception:  # noqa: BLE001
                    logger.exception(
                        "tool_event queue.put_nowait (error) failed"
                    )
            raise


async def build_handoff(
    chat_client=None,
    mcp_url: Optional[str] = None,
) -> Tuple["object", "InstrumentedMCPTool", "asyncio.Queue[dict[str, Any]]"]:
    """Build the BrokerWorkbench handoff workflow.

    Args:
        chat_client: Optional pre-built Agent Framework chat client. When
            ``None``, one is constructed via :func:`build_chat_client`.
        mcp_url: Override for the MCP server URL. Defaults to
            ``MCP_SERVER_URL`` env var, then ``http://localhost:8001/mcp``.

    Returns:
        A ``(workflow, mcp_tool, tool_queue)`` tuple. The caller MUST drive
        ``async with mcp_tool: ...`` before running the workflow so the MCP
        connection is opened (and torn down) correctly. ``tool_queue`` is an
        ``asyncio.Queue`` that receives ``call`` / ``result`` dicts whenever
        the agents invoke an MCP tool (see :class:`InstrumentedMCPTool`).
    """
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

    tool_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
    mcp_tool = InstrumentedMCPTool(
        name="brokerworkbench",
        url=resolved_url,
        description="BrokerWorkbench insurance data (clients, policies, claims, carriers).",
        approval_mode="never_require",
        # Hosted Foundry treats MCP tools as Responses-API server-side
        # "hosted MCP" — approval is governed by the tool spec's
        # require_approval field, not our client-side approval_mode kwarg.
        # M365 Copilot's V2 ResponseObject deserializer rejects
        # mcp_approval_request items with a 500.
        additional_properties={"require_approval": "never"},
    )
    mcp_tool.bind_queue(tool_queue)

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
        .build()
    )

    return workflow, mcp_tool, tool_queue
