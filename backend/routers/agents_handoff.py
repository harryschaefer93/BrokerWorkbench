"""Agent Framework handoff endpoint — additive sibling of `agents.py`.

Exposes ``POST /api/agent/chat/handoff/stream`` which runs the Microsoft
Agent Framework :class:`HandoffBuilder` workflow built in
``backend/agents/foundry/handoff.py`` and adapts its ``WorkflowEvent``
stream to the existing 5-frame SSE contract consumed by the React chat
panel (``routing`` / ``status`` / ``token`` / ``done`` / ``error``), plus
two additional Phase B3 frames (``tool_call`` / ``tool_result``) for the
"What just happened" trace pill UI.

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
    * Per-tool ``status`` frames are still emitted as a coarse "agent X is
      thinking" signal. Granular MCP tool calls flow through the new
      ``tool_call`` / ``tool_result`` frames sourced from the
      InstrumentedMCPTool queue (Phase B B3).
"""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Any

from fastapi import APIRouter, Header
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
async def agent_handoff_stream(
    request: ChatRequest,
    x_conversation_id: str | None = Header(default=None, alias="X-Conversation-Id"),
):
    """Stream the handoff workflow as SSE matching the legacy contract."""
    # Generate a server-side conversation id if the client hasn't yet
    # persisted one. The frontend (Phase B B4) will echo this back on
    # subsequent turns via the X-Conversation-Id header.
    conversation_id = x_conversation_id or f"conv-{uuid.uuid4().hex[:12]}"
    return StreamingResponse(
        _stream_handoff(request, conversation_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "X-Conversation-Id": conversation_id,
        },
    )


async def _drain_tool_queue(
    queue: asyncio.Queue[dict[str, Any]],
    sink: asyncio.Queue[str],
    stop_event: asyncio.Event,
    log: logging.LoggerAdapter,
) -> None:
    """Convert tool-event dicts into SSE frame strings and push to sink.

    Runs concurrently with the workflow event loop until ``stop_event`` is
    set, then drains any remaining events before returning so a tool_result
    that arrived just before the workflow finished still reaches the wire.
    """
    while True:
        try:
            evt = await asyncio.wait_for(queue.get(), timeout=0.1)
        except asyncio.TimeoutError:
            if stop_event.is_set() and queue.empty():
                return
            continue
        try:
            if evt.get("kind") == "call":
                log.info(
                    "tool_call name=%s call_id=%s",
                    evt.get("name"),
                    evt.get("call_id"),
                )
                await sink.put(
                    _frame(
                        {
                            "type": "tool_call",
                            "name": evt.get("name"),
                            "arguments": evt.get("arguments", {}),
                            "call_id": evt.get("call_id"),
                        }
                    )
                )
            elif evt.get("kind") == "result":
                log.info(
                    "tool_result call_id=%s ok=%s",
                    evt.get("call_id"),
                    evt.get("ok"),
                )
                await sink.put(
                    _frame(
                        {
                            "type": "tool_result",
                            "call_id": evt.get("call_id"),
                            "ok": bool(evt.get("ok")),
                            "summary": evt.get("summary", ""),
                        }
                    )
                )
        except Exception:  # noqa: BLE001 — never let the drainer kill the stream
            log.exception("tool_queue drain error")


async def _run_workflow_events(
    workflow,
    prompt: str,
    sink: asyncio.Queue[str],
    state: dict[str, Any],
    log: logging.LoggerAdapter,
) -> None:
    """Drive the workflow event stream → push SSE frame strings to sink.

    ``state["last_speaker"]`` is updated so the outer caller can compute the
    final ``agent`` for the ``done`` frame after this coroutine returns.
    """
    last_speaker: str | None = state.get("last_speaker")
    async for event in workflow.run(prompt, stream=True):
        ev_type = getattr(event, "type", None)
        executor_id = getattr(event, "executor_id", None)
        data = getattr(event, "data", None)

        # Agent transition — first time we see a new executor_id on an
        # output frame, announce it.
        if ev_type == "output" and executor_id:
            if executor_id != last_speaker:
                last_speaker = executor_id
                state["last_speaker"] = last_speaker
                mapped = _AGENT_NAME_MAP.get(executor_id, executor_id)
                log.info("routing to=%s", executor_id)
                await sink.put(
                    _frame(
                        {
                            "type": "routing",
                            "agent": mapped,
                            "content": f"Routing to {executor_id}…",
                        }
                    )
                )

            # Token delta — AgentResponseUpdate.text holds the streamed
            # chunk text.
            delta = getattr(data, "text", None)
            if delta:
                await sink.put(_frame({"type": "token", "content": delta}))
            continue

        # Coarse progress signal when a specialist is invoked to actually
        # respond (not just routed).
        if ev_type == "executor_invoked" and executor_id:
            should_respond = getattr(data, "should_respond", None)
            if should_respond and executor_id != last_speaker:
                await sink.put(
                    _frame(
                        {
                            "type": "status",
                            "content": f"{executor_id} is thinking…",
                        }
                    )
                )
            continue

        # request_info = HandoffAgentUserRequest = the workflow is pausing
        # for user input. From the user's POV this turn is done.
        if ev_type == "request_info":
            break


async def _stream_handoff(request: ChatRequest, conversation_id: str):
    """Adapt Agent Framework WorkflowEvent stream → 5+2 frame SSE.

    Runs the workflow event loop and a tool-queue drainer concurrently,
    funneling both into a shared sink queue so frame ordering on the wire
    matches the actual call timeline (a ``tool_call`` always precedes its
    matching ``tool_result``).
    """
    # Bind conversation_id into every log line for this request so we can
    # trace a single turn end-to-end in App Insights.
    log = logging.LoggerAdapter(logger, {"conversation_id": conversation_id})

    # Import lazily so the legacy endpoint and test collection don't pay
    # the agent-framework import cost when this endpoint isn't called.
    from agents.foundry.handoff import build_handoff

    prompt = _build_prompt(request.message, request.history)
    state: dict[str, Any] = {"last_speaker": None}

    try:
        workflow, mcp_tool, tool_queue = await build_handoff()

        async with mcp_tool:
            # Shared sink so workflow-event frames and tool-event frames
            # interleave in true arrival order on the wire.
            sink: asyncio.Queue[str] = asyncio.Queue()
            stop_event = asyncio.Event()

            workflow_task = asyncio.create_task(
                _run_workflow_events(workflow, prompt, sink, state, log)
            )
            drain_task = asyncio.create_task(
                _drain_tool_queue(tool_queue, sink, stop_event, log)
            )

            try:
                async with asyncio.timeout(_HANDOFF_TIMEOUT_SECONDS):
                    # Pump frames from the sink while the workflow is still
                    # running. We stop pumping once the workflow finishes
                    # AND the sink is empty.
                    while True:
                        # Tight join: workflow_task may complete while
                        # frames are still queued; we want to drain them.
                        if workflow_task.done() and sink.empty():
                            break
                        try:
                            frame = await asyncio.wait_for(
                                sink.get(), timeout=0.1
                            )
                            yield frame
                        except asyncio.TimeoutError:
                            continue
            except TimeoutError:
                log.warning(
                    "handoff workflow timed out after %ss",
                    _HANDOFF_TIMEOUT_SECONDS,
                )
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
            finally:
                stop_event.set()
                # Give the workflow task a moment to surface any final
                # exception, then cancel both helpers cleanly.
                if not workflow_task.done():
                    workflow_task.cancel()
                try:
                    await workflow_task
                except (asyncio.CancelledError, Exception):  # noqa: BLE001
                    pass
                # Drain any straggler tool-result frames the drainer
                # captured after workflow completion (it loops until both
                # stop_event is set AND the queue is empty).
                try:
                    await asyncio.wait_for(drain_task, timeout=1.0)
                except asyncio.TimeoutError:
                    drain_task.cancel()
                    try:
                        await drain_task
                    except (asyncio.CancelledError, Exception):  # noqa: BLE001
                        pass
                # Flush any final frames pushed during drain.
                while not sink.empty():
                    try:
                        yield sink.get_nowait()
                    except asyncio.QueueEmpty:
                        break

        final_agent = _AGENT_NAME_MAP.get(
            state.get("last_speaker") or "Triage", "BrokerAgent"
        )
        log.info("handoff done final_agent=%s", final_agent)
        yield _frame(
            {"type": "done", "agent": final_agent, "suggestions": []}
        )

    except Exception as exc:  # noqa: BLE001 — surface anything to the UI
        log.exception("Handoff streaming error")
        yield _frame({"type": "error", "content": str(exc)})
