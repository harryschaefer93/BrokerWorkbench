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
import os
import uuid
from typing import Any

from fastapi import APIRouter, Header
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from enum import Enum


class AgentType(str, Enum):
    QUOTE = "quote"
    CROSSSELL = "crosssell"
    CLAIMS = "claims"
    TRIAGE = "triage"


class ChatRequest(BaseModel):
    """Request schema for the handoff chat endpoint."""
    message: str = Field(..., description="User's message to the agent")
    agent: AgentType = Field(..., description="Entry agent (always triage in handoff mode)")
    client_id: str | None = Field(None, description="Optional client ID for context")
    conversation_id: str | None = Field(None, description="Continue existing conversation")
    history: list[dict] | None = Field(None, description="Conversation history for context")

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
    """Stream the handoff workflow as SSE matching the legacy contract.

    Routing mode is selected by ``AGENT_BACKEND_MODE`` env var:
        ``hosted`` (PROD) — proxy to the Foundry hosted agent ``/responses``
            endpoint via :func:`_stream_hosted`. Requires
            ``HOSTED_AGENT_ENDPOINT`` to be set. This is what all three
            surfaces (M365 Copilot, Teams, Web) hit in production — the
            backend is a thin SSE translator; the agent itself lives inside
            the Foundry project (``broker-hosted-agent`` container).
        ``fastapi`` (LEGACY / local dev) — run the workflow in-process via
            :func:`_stream_handoff`. Uses the orchestration code in
            ``backend/agents/foundry/handoff.py`` directly. NOT a prod path.

    See ``docs/architecture.md`` for the full 3-surface topology.
    """
    conversation_id = x_conversation_id or f"conv-{uuid.uuid4().hex[:12]}"
    mode = os.getenv("AGENT_BACKEND_MODE", "fastapi").strip().lower()
    if mode == "hosted":
        stream = _stream_hosted(request, conversation_id)
    else:
        stream = _stream_handoff(request, conversation_id)
    return StreamingResponse(
        stream,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "X-Conversation-Id": conversation_id,
            "X-Agent-Backend-Mode": mode,
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

# ── Hosted-agent proxy mode ─────────────────────────────────────────────
# Translates a Foundry Hosted-agent /responses SSE stream into the
# 5+2-frame contract the React panel and Teams bot already consume.
# Triggered when ``AGENT_BACKEND_MODE=hosted``.


_HOSTED_TIMEOUT_SECONDS = 120
_HOSTED_RETRY_DELAY_SECONDS = 6.0


async def _stream_hosted(request: ChatRequest, conversation_id: str):
    """Public hosted-agent stream with a single retry on early failure.

    Foundry hosted-agent responses occasionally fail with ``server_error``
    when the gpt-5 deployment hits its TPM ceiling. The failure surfaces
    within a few seconds, before any tokens are emitted. We retry once
    after a short backoff so a transient rate-limit hit doesn't poison the
    user-visible turn. If the second attempt also fails (or fails after
    we've already emitted output), the error propagates.
    """
    last_error: dict[str, Any] | None = None
    for attempt in range(2):
        emitted_any = False
        had_error = False
        async for event in _stream_hosted_attempt(
            request, conversation_id, attempt=attempt
        ):
            etype = event.get("type")
            if etype == "error":
                last_error = event
                had_error = True
                if not emitted_any and attempt == 0:
                    # Swallow the error and retry the whole turn.
                    break
                yield _frame(event)
                return
            yield _frame(event)
            if etype in {"token", "tool_call", "tool_result", "routing"}:
                emitted_any = True
        if not had_error:
            return
        await asyncio.sleep(_HOSTED_RETRY_DELAY_SECONDS)
    if last_error is not None:
        yield _frame(last_error)


async def _stream_hosted_attempt(
    request: ChatRequest,
    conversation_id: str,
    attempt: int = 0,
):
    """Proxy a single turn to the Hosted-agent Responses endpoint.

    Yields raw dict payloads (no SSE framing). Callers wrap with
    :func:`_frame`. Maps the Foundry OpenAI Responses event vocabulary to
    our 5+2-frame contract. Verified event types from sc-v5 hosted agent:
        response.created / .in_progress / .completed
        response.output_item.added / .done  (reasoning | function_call | message)
        response.output_text.delta / .done
        response.function_call_arguments.delta / .done
        response.reasoning_summary_* (ignored)
        response.content_part.added / .done

    Routing surfaces as ``function_call`` items whose name starts with
    ``handoff_to_`` (Agent Framework convention). Regular tool calls are
    function_call items with their MCP tool name. Foundry does NOT emit
    public tool RESULT events \u2014 we synthesize an ``ok`` ``tool_result``
    frame when the call's status transitions to ``completed`` (function
    succeeded; on error the platform raises out of the stream instead).
    """
    import httpx
    from azure.identity.aio import (
        AzureCliCredential,
        ChainedTokenCredential,
        EnvironmentCredential,
        ManagedIdentityCredential,
    )

    log = logging.LoggerAdapter(
        logger, {"conversation_id": conversation_id, "attempt": attempt}
    )
    endpoint = os.getenv("HOSTED_AGENT_ENDPOINT")
    if not endpoint:
        yield {
            "type": "error",
            "content": (
                "AGENT_BACKEND_MODE=hosted but HOSTED_AGENT_ENDPOINT is not set."
            ),
        }
        return

    client_id = os.getenv("AZURE_CLIENT_ID")
    credential = ChainedTokenCredential(
        EnvironmentCredential(),
        ManagedIdentityCredential(client_id=client_id),
        AzureCliCredential(),
    )
    token = await credential.get_token("https://ai.azure.com/.default")

    last_speaker = "Triage"
    final_text: list[str] = []
    # call_id -> {name, arguments_chunks: list[str], is_handoff: bool}
    pending_calls: dict[str, dict[str, Any]] = {}
    body = {
        "input": _build_prompt(request.message, request.history),
        "stream": True,
        # Platform manages history; we replayed it already in the prompt.
        "store": False,
    }

    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(_HOSTED_TIMEOUT_SECONDS, read=_HOSTED_TIMEOUT_SECONDS)
        ) as client:
            async with client.stream(
                "POST",
                endpoint,
                json=body,
                headers={
                    "Authorization": f"Bearer {token.token}",
                    "Content-Type": "application/json",
                    "Accept": "text/event-stream",
                },
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line or not line.startswith("data: "):
                        continue
                    raw = line[6:].strip()
                    if raw == "[DONE]":
                        break
                    try:
                        event = json.loads(raw)
                    except json.JSONDecodeError:
                        continue
                    etype = event.get("type", "")

                    # 1. Token deltas \u2014 the visible answer.
                    if etype == "response.output_text.delta":
                        delta = event.get("delta") or ""
                        if delta:
                            final_text.append(delta)
                            yield {"type": "token", "content": delta}
                        continue

                    # 2. New output item arrives \u2014 detect function_call.
                    if etype == "response.output_item.added":
                        item = event.get("item") or {}
                        if item.get("type") != "function_call":
                            continue
                        call_id = item.get("call_id") or item.get("id") or ""
                        name = item.get("name") or ""
                        is_handoff = name.startswith("handoff_to_")
                        pending_calls[call_id] = {
                            "name": name,
                            "args_chunks": [],
                            "is_handoff": is_handoff,
                        }
                        if is_handoff:
                            target = name[len("handoff_to_"):]
                            last_speaker = target
                            mapped = _AGENT_NAME_MAP.get(target, target)
                            log.info("hosted routing to=%s", target)
                            yield {
                                "type": "routing",
                                "agent": mapped,
                                "content": f"Routing to {target}\u2026",
                            }
                        else:
                            # Real MCP tool call \u2014 emit start frame.
                            yield {
                                "type": "tool_call",
                                "name": name,
                                "arguments": {},  # filled progressively
                                "call_id": call_id,
                            }
                        continue

                    # 3. Accumulate function_call argument chunks.
                    if etype == "response.function_call_arguments.delta":
                        call_id = event.get("item_id") or event.get("call_id") or ""
                        delta = event.get("delta") or ""
                        if call_id in pending_calls and delta:
                            pending_calls[call_id]["args_chunks"].append(delta)
                        continue

                    # 4. function_call complete \u2014 synthesize tool_result.
                    if etype == "response.output_item.done":
                        item = event.get("item") or {}
                        if item.get("type") != "function_call":
                            continue
                        call_id = item.get("call_id") or item.get("id") or ""
                        info = pending_calls.pop(call_id, None)
                        if not info or info["is_handoff"]:
                            # Handoffs don't get tool_result frames in our contract.
                            continue
                        # Foundry tells us the final arguments string on the
                        # .done item; prefer that over our chunked accumulation
                        # for accuracy.
                        args_str = (
                            item.get("arguments")
                            or "".join(info["args_chunks"])
                            or "{}"
                        )
                        try:
                            args_parsed = json.loads(args_str) if args_str else {}
                        except json.JSONDecodeError:
                            args_parsed = {"_raw": args_str}
                        status = item.get("status", "completed")
                        ok = status == "completed"
                        yield {
                            "type": "tool_result",
                            "call_id": call_id,
                            "ok": ok,
                            "summary": json.dumps(args_parsed)[:160],
                        }
                        continue

                    # 5. Terminal events \u2014 capture final text if we missed
                    # streaming (e.g. background mode buffered everything).
                    if etype == "response.completed":
                        if not final_text:
                            try:
                                outputs = (
                                    event.get("response", {}).get("output", [])
                                )
                                for o in outputs:
                                    for c in o.get("content", []) or []:
                                        if c.get("type") == "output_text":
                                            final_text.append(c.get("text", ""))
                            except Exception:  # noqa: BLE001
                                pass
                        break

                    # 6. Errors.
                    if etype == "error" or etype.endswith(".failed"):
                        err_payload = event.get("error") or event
                        log.warning("hosted upstream error: %s", err_payload)
                        yield {
                            "type": "error",
                            "content": _humanize_hosted_error(err_payload),
                        }
                        return
    except httpx.HTTPError as exc:
        log.exception("hosted-agent proxy http error")
        yield {"type": "error", "content": f"hosted proxy: {exc}"}
        return
    except Exception as exc:  # noqa: BLE001
        log.exception("hosted-agent proxy error")
        yield {"type": "error", "content": str(exc)}
        return
    finally:
        try:
            await credential.close()
        except Exception:  # noqa: BLE001
            pass

    final_agent = _AGENT_NAME_MAP.get(last_speaker, "BrokerAgent")
    log.info("hosted proxy done final_agent=%s", final_agent)
    yield {"type": "done", "agent": final_agent, "suggestions": []}


def _humanize_hosted_error(err: Any) -> str:
    """Turn a Foundry error payload into a short, demo-safe message."""
    try:
        if isinstance(err, dict):
            code = str(err.get("code") or err.get("error", {}).get("code") or "").lower()
            msg = (
                err.get("message")
                or err.get("error", {}).get("message")
                or ""
            )
            if code in {"server_error", "rate_limit_exceeded", "429"}:
                return (
                    "The model is briefly throttled (gpt-5 TPM). "
                    "Please send the question again."
                )
            if msg:
                return f"Agent error: {msg}"
    except Exception:  # noqa: BLE001
        pass
    return f"Agent error: {err}"