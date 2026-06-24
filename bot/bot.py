"""
BrokerBot — Teams activity handler.

Receives messages from Teams, forwards them to the BrokerWorkbench backend,
and returns polished Adaptive Cards.
"""

import asyncio
from collections import defaultdict
from typing import Any, AsyncIterator
import json

import httpx
from botbuilder.core import BotAdapter, CardFactory, MessageFactory, TurnContext
from botbuilder.core.teams import TeamsActivityHandler
from botbuilder.schema import Attachment, ChannelAccount

from card_formatter import CardFormatter
from config import Settings
from streaming import BotStreamer

# Max conversation turns to keep in memory per conversation
_MAX_HISTORY = 10

# Send a "still working" heartbeat if the backend goes this long without an
# event, so the M365 Copilot / Teams streaming session never stalls silently.
_HEARTBEAT_SECONDS = 12.0

# Overall bot-side cap for a single turn. Kept below the platform streaming
# lifetime (~2 min) so we always emit a final message before it expires.
_TURN_DEADLINE_SECONDS = 110.0

# Friendly status lines shown while a specialist works. Keyed by the mapped
# agent name the backend emits in `routing` frames.
_AGENT_STATUS: dict[str, str] = {
    "ClaimsImpactAgent": "Analyzing claims history…",
    "QuoteComparisonAgent": "Comparing carrier quotes…",
    "CrossSellAgent": "Scanning for coverage gaps…",
    "BrokerAgent": "Working through your book of business…",
}


class BrokerBot(TeamsActivityHandler):
    """Teams bot that proxies to the BrokerWorkbench backend."""

    def __init__(self, settings: Settings, adapter: BotAdapter | None = None):
        super().__init__()
        self.backend_url = settings.backend_url.rstrip("/")
        self.formatter = CardFormatter()
        self.adapter = adapter
        self.bot_app_id = settings.microsoft_app_id
        # In-memory conversation history: {conversation_id: [{"role":..., "content":...}]}
        self._history: dict[str, list[dict[str, str]]] = defaultdict(list)
        # One lock per conversation so a second prompt can't corrupt an
        # in-flight streaming response (Teams allows one active stream per chat).
        self._locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    # ------------------------------------------------------------------
    # Message handling
    # ------------------------------------------------------------------

    async def on_message_activity(self, turn_context: TurnContext) -> None:
        """Handle incoming messages and Action.Submit button presses."""
        # Action.Submit sends the value in activity.value, not activity.text
        text = None
        if turn_context.activity.value:
            value = turn_context.activity.value
            if isinstance(value, dict):
                text = value.get("message") or value.get("text")
            elif isinstance(value, str):
                text = value
        if not text:
            text = (turn_context.activity.text or "").strip()
        if not text:
            return

        conv_id = turn_context.activity.conversation.id

        # Reset/clear command
        if text.lower().strip() in ("clear", "/reset", "new conversation", "/clear", "reset"):
            self._history.pop(conv_id, None)
            card_payload = self.formatter.format_reset_card()
            attachment = self._make_attachment(card_payload)
            await turn_context.send_activity(MessageFactory.attachment(attachment))
            return

        # Serialize turns per conversation. If a stream is already running for
        # this chat, tell the user instead of racing two streams.
        lock = self._locks[conv_id]
        if lock.locked():
            await turn_context.send_activity(
                MessageFactory.text(
                    "I'm still working on your previous question — one moment…"
                )
            )
            return

        async with lock:
            await self._stream_turn(turn_context, text, conv_id)

    async def _stream_turn(
        self, turn_context: TurnContext, text: str, conv_id: str
    ) -> None:
        """Process one turn inline, streaming progress to the surface.

        Replaces the former fire-and-forget ``continue_conversation`` path
        (which silently dropped replies on worker recycle). All three surfaces
        — M365 Copilot, Teams, Web-via-bot — expect the reply on the same
        invoke turn, with streaming updates so the connector never times out.
        """
        history = self._history[conv_id]
        streamer = BotStreamer(turn_context)
        # Acknowledge immediately (<2s) so the surface shows life.
        await streamer.update("Looking into that…", force=True)

        agent_name = "BrokerAgent"
        full_text = ""
        announced: set[str] = set()
        deadline = asyncio.get_event_loop().time() + _TURN_DEADLINE_SECONDS

        try:
            events = self._iter_backend_events(text, history)
            # Drive __anext__ via a persistent task so a heartbeat timeout never
            # cancels an in-flight backend read (which would corrupt the async
            # generator and silently drop the event it was awaiting).
            pending: asyncio.Task = asyncio.ensure_future(events.__anext__())
            try:
                while True:
                    remaining = deadline - asyncio.get_event_loop().time()
                    if remaining <= 0:
                        raise TimeoutError("turn exceeded bot-side deadline")
                    done, _ = await asyncio.wait(
                        {pending}, timeout=min(_HEARTBEAT_SECONDS, remaining)
                    )
                    if not done:
                        # No backend event recently — keep the stream alive.
                        await streamer.update("Still working on it…", force=True)
                        continue
                    try:
                        event = pending.result()
                    except StopAsyncIteration:
                        break
                    # Schedule the next read before processing this event.
                    pending = asyncio.ensure_future(events.__anext__())

                    etype = event.get("type")
                    if etype == "token":
                        full_text += event.get("content", "")
                        # Grow the streamed answer bubble (throttled internally).
                        await streamer.update(full_text, stream_type="streaming")
                    elif etype == "routing":
                        if event.get("agent"):
                            agent_name = event["agent"]
                            if agent_name not in announced:
                                announced.add(agent_name)
                                await streamer.update(
                                    _AGENT_STATUS.get(agent_name, "Working on it…"),
                                    force=True,
                                )
                    elif etype == "status":
                        if event.get("content"):
                            await streamer.update(event["content"])
                    elif etype == "tool_call":
                        await streamer.update("Looking up insurance data…")
                    elif etype == "done":
                        if event.get("agent"):
                            agent_name = event["agent"]
                        if not full_text and event.get("content"):
                            full_text = event["content"]
                    elif etype == "error":
                        raise RuntimeError(event.get("content") or "Agent error")
            finally:
                if not pending.done():
                    pending.cancel()
                await events.aclose()

            if not full_text:
                full_text = "No response from backend."
            self._append_history(conv_id, text, full_text)
            suggestions = self._pick_suggestions(text, agent_name)
            card_payload = self.formatter.format_response(
                full_text, agent_name, suggestions=suggestions
            )
            await streamer.final(
                full_text, attachment=self._make_attachment(card_payload)
            )
        except Exception as exc:  # noqa: BLE001 — always surface a final to the user
            err_card = self.formatter.format_error_card(str(exc))
            await streamer.final(
                "Sorry, something went wrong handling that request.",
                attachment=self._make_attachment(err_card),
            )

    def _append_history(self, conv_id: str, user_text: str, assistant_text: str) -> None:
        history = self._history[conv_id]
        history.append({"role": "user", "content": user_text})
        history.append({"role": "assistant", "content": assistant_text})
        if len(history) > _MAX_HISTORY * 2:
            self._history[conv_id] = history[-_MAX_HISTORY * 2:]

    async def on_members_added_activity(
        self, members_added: list[ChannelAccount], turn_context: TurnContext
    ) -> None:
        """Send a welcome card when the bot is added to a conversation."""
        for member in members_added:
            if member.id != turn_context.activity.recipient.id:
                card_payload = self.formatter.format_welcome_card()
                attachment = self._make_attachment(card_payload)
                await turn_context.send_activity(MessageFactory.attachment(attachment))

    # ------------------------------------------------------------------
    # Backend integration
    # ------------------------------------------------------------------

    async def _iter_backend_events(
        self, message: str, history: list[dict[str, str]]
    ) -> AsyncIterator[dict[str, Any]]:
        """Yield parsed SSE events from the handoff endpoint as they arrive.

        Streams from ``/api/agent/chat/handoff/stream`` and yields each decoded
        event dict (``token`` / ``routing`` / ``status`` / ``tool_call`` /
        ``tool_result`` / ``done`` / ``error``) so the caller can forward
        progress to the surface in real time instead of buffering the whole
        answer. The caller owns timeouts/heartbeats.
        """
        payload: dict[str, Any] = {
            "message": message,
            "agent": "triage",
            "history": history,
        }

        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream(
                "POST",
                f"{self.backend_url}/api/agent/chat/handoff/stream",
                json=payload,
                headers={"Accept": "text/event-stream"},
            ) as resp:
                resp.raise_for_status()
                async for raw_line in resp.aiter_lines():
                    if not raw_line or not raw_line.startswith("data: "):
                        continue
                    try:
                        event = json.loads(raw_line[6:].strip())
                    except (json.JSONDecodeError, ValueError):
                        continue
                    if isinstance(event, dict) and event.get("type"):
                        yield event

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _make_attachment(card_payload: dict) -> Attachment:
        return CardFactory.adaptive_card(card_payload)

    @staticmethod
    def _pick_suggestions(message: str, agent_name: str) -> list[str]:
        """Return contextual follow-up suggestions based on the agent."""
        msg = message.lower()
        if "claim" in msg or "loss" in msg:
            return [
                "Show upcoming renewals",
                "Compare carrier quotes for commercial property",
                "Find cross-sell opportunities for CLI003",
            ]
        if "quote" in msg or "carrier" in msg or "rate" in msg:
            return [
                "Analyze claims impact for CLI001",
                "Show upcoming renewals",
                "Find cross-sell opportunities for CLI003",
            ]
        if "cross" in msg or "gap" in msg or "opportunity" in msg:
            return [
                "Compare carrier quotes for commercial property",
                "Analyze claims impact for CLI001",
                "Show upcoming renewals",
            ]
        # Default / renewals / general
        return [
            "Analyze claims impact for CLI001",
            "Compare carrier quotes for commercial property",
            "Find cross-sell opportunities for CLI003",
        ]
