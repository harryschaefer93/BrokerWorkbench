"""Agent Framework handoff endpoint — additive sibling of `agents.py`.

Exposes ``POST /api/agent/chat/handoff/stream`` which runs the Microsoft
Agent Framework :class:`HandoffBuilder` workflow built in
``backend/agents/foundry/handoff.py`` and adapts its ``WorkflowEvent``
stream to the existing 5-frame SSE contract consumed by the React chat
panel (``routing`` / ``status`` / ``token`` / ``done`` / ``error``).

This file is intentionally additive — it does not import from or modify
``agents.py`` beyond reusing the ``ChatRequest`` model so the request
schema stays in lockstep with the legacy endpoint.

v1 limitations (intentional, documented for the demo):
    * Workflow is rebuilt per request — no per-conversation state. History
      is replayed by concatenating the last 10 turns into a single prompt
      string. A future iteration should bind a conversation_id to a
      persisted workflow / thread.
    * No ``_get_contextual_suggestions`` (the legacy router's heuristics).
      ``done`` frames carry ``suggestions: []``; the React side already
      falls back to ``extractSuggestions`` from the rendered text.
    * Per-tool ``status`` frames are not emitted — Agent Framework's
      WorkflowEvent stream surfaces agent activity (``executor_invoked``,
      ``output``) but routes MCP tool calls through the chat client
      layer below the event bus. A coarse ``status`` is emitted on
      handoff so the UI shows progress.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

# Reuse the legacy request schema verbatim — no duplication, no edits to
# agents.py. ChatRequest is a public symbol in that module. Relative import
# avoids the routers/backend.routers dual-name trap (both are on sys.path).
from .agents import ChatRequest

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/agent/chat/handoff", tags=["AI Agents (Handoff)"])


# Map Agent Framework executor_id (the `name=` we set in
# backend/agents/foundry/specialists/*.py) to the PascalCase class names the
# React `agentNameMap` in useApi.ts resolves to UI agent types.
_AGENT_NAME_MAP: dict[str, str] = {
    "Triage": "BrokerAgent",
    "Claims": "ClaimsImpactAgent",
    "Quote": "QuoteComparisonAgent",
    "CrossSell": "CrossSellAgent",
}

_HANDOFF_TIMEOUT_SECONDS = 120


def _build_prompt(message: str, history: list[dict] | None) -> str:
    """Concatenate the last 10 turns into a single prompt string.

    Trade-off: the legacy `/agent/chat/stream` endpoint replays history as
    structured chat messages. The handoff workflow takes a single string
    input per run, so we flatten it. This loses per-turn role fidelity
    but preserves enough context for the demo.
    """
    if not history:
        return message
    lines: list[str] = []
    for h in history[-10:]:
        role = h.get("role")
        content = h.get("content")
        if role in ("user", "assistant") and content:
            lines.append(f"{role}: {content}")
    lines.append(f"user: {message}")
    return "\n".join(lines)


def _frame(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload)}\n\n"


@router.post("/stream")
async def agent_handoff_stream(request: ChatRequest):
    """Stream the handoff workflow as SSE matching the legacy contract."""
    return StreamingResponse(
        _stream_handoff(request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


async def _stream_handoff(request: ChatRequest):
    """Adapt Agent Framework WorkflowEvent stream → 5-frame SSE."""
    # Import lazily so the legacy endpoint and test collection don't pay
    # the agent-framework import cost when this endpoint isn't called.
    from agents.foundry.handoff import build_handoff

    prompt = _build_prompt(request.message, request.history)
    last_speaker: str | None = None

    try:
        workflow, mcp_tool = await build_handoff()

        async with mcp_tool:
            try:
                async with asyncio.timeout(_HANDOFF_TIMEOUT_SECONDS):
                    async for event in workflow.run(prompt, stream=True):
                        ev_type = getattr(event, "type", None)
                        executor_id = getattr(event, "executor_id", None)
                        data = getattr(event, "data", None)

                        # Agent transition — first time we see a new
                        # executor_id on an output frame, announce it.
                        if ev_type == "output" and executor_id:
                            if executor_id != last_speaker:
                                last_speaker = executor_id
                                mapped = _AGENT_NAME_MAP.get(
                                    executor_id, executor_id
                                )
                                yield _frame(
                                    {
                                        "type": "routing",
                                        "agent": mapped,
                                        "content": f"Routing to {executor_id}…",
                                    }
                                )

                            # Token delta — AgentResponseUpdate.text holds
                            # the streamed chunk text.
                            delta = getattr(data, "text", None)
                            if delta:
                                yield _frame(
                                    {"type": "token", "content": delta}
                                )
                            continue

                        # Coarse progress signal when a specialist is
                        # invoked to actually respond (not just routed).
                        if ev_type == "executor_invoked" and executor_id:
                            should_respond = getattr(
                                data, "should_respond", None
                            )
                            if should_respond and executor_id != last_speaker:
                                yield _frame(
                                    {
                                        "type": "status",
                                        "content": f"{executor_id} is thinking…",
                                    }
                                )
                            continue

                        # request_info = HandoffAgentUserRequest = the
                        # workflow is pausing for user input. From the
                        # user's POV this turn is done.
                        if ev_type == "request_info":
                            break

            except TimeoutError:
                yield _frame(
                    {
                        "type": "error",
                        "content": (
                            f"Handoff workflow timed out after "
                            f"{_HANDOFF_TIMEOUT_SECONDS}s."
                        ),
                    }
                )
                return

        final_agent = _AGENT_NAME_MAP.get(
            last_speaker or "Triage", "BrokerAgent"
        )
        yield _frame(
            {"type": "done", "agent": final_agent, "suggestions": []}
        )

    except Exception as exc:  # noqa: BLE001 — surface anything to the UI
        logger.exception("Handoff streaming error")
        yield _frame({"type": "error", "content": str(exc)})
