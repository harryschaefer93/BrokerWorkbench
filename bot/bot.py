"""
BrokerBot — Teams activity handler.

Receives messages from Teams, forwards them to the BrokerWorkbench backend,
and returns polished Adaptive Cards.
"""

from collections import defaultdict
from typing import Any

import httpx
from botbuilder.core import CardFactory, MessageFactory, TurnContext
from botbuilder.core.teams import TeamsActivityHandler
from botbuilder.schema import Attachment, ChannelAccount

from card_formatter import CardFormatter
from config import Settings

# Max conversation turns to keep in memory per conversation
_MAX_HISTORY = 10


class BrokerBot(TeamsActivityHandler):
    """Teams bot that proxies to the BrokerWorkbench backend."""

    def __init__(self, settings: Settings):
        super().__init__()
        self.backend_url = settings.backend_url.rstrip("/")
        self.formatter = CardFormatter()
        # In-memory conversation history: {conversation_id: [{"role":..., "content":...}]}
        self._history: dict[str, list[dict[str, str]]] = defaultdict(list)

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
        history = self._history[conv_id]

        try:
            agent_name, response_text = await self._call_backend(text, history)

            # Update history
            history.append({"role": "user", "content": text})
            history.append({"role": "assistant", "content": response_text})
            # Trim to max turns (each turn = 2 entries)
            if len(history) > _MAX_HISTORY * 2:
                self._history[conv_id] = history[-_MAX_HISTORY * 2:]

            # Build and send Adaptive Card
            suggestions = self._pick_suggestions(text, agent_name)
            card_payload = self.formatter.format_response(
                response_text, agent_name, suggestions=suggestions
            )
            attachment = self._make_attachment(card_payload)
            await turn_context.send_activity(MessageFactory.attachment(attachment))

        except Exception as exc:
            card_payload = self.formatter.format_error_card(str(exc))
            attachment = self._make_attachment(card_payload)
            await turn_context.send_activity(MessageFactory.attachment(attachment))

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

    async def _call_backend(
        self, message: str, history: list[dict[str, str]]
    ) -> tuple[str, str]:
        """POST to the BrokerWorkbench backend and return (agent_name, response_text)."""
        payload: dict[str, Any] = {
            "message": message,
            "agent": "triage",
            "history": history,
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{self.backend_url}/api/agent/chat",
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()

        agent_name = data.get("agent", "BrokerAgent")
        response_text = data.get("response", "No response from backend.")
        return agent_name, response_text

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
