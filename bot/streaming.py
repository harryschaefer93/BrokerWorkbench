"""Bot Framework streaming-activity helper for M365 Copilot / Teams.

Implements the documented custom-engine-agent streaming contract so the bot
acknowledges quickly and keeps the user informed during long Foundry turns
instead of buffering the whole answer and replying once (which causes the
"spinner then nothing" / connector-timeout failures in M365 Copilot).

Contract (per Microsoft streaming docs):
    * Interim updates are ``typing`` activities carrying a ``streaminfo``
      entity with ``streamType`` ``informative`` (status) or ``streaming``
      (partial answer content). Each carries a monotonically increasing
      ``streamSequence`` starting at 1.
    * The first activity has no ``streamId``; the channel returns one in the
      ``ResourceResponse.id`` which is echoed on every subsequent activity.
    * The final answer is a ``message`` activity with ``streamType`` ``final``
      and NO ``streamSequence``. Text is canonical; an Adaptive Card may ride
      along as an attachment for rich rendering.

Every send is best-effort: if a channel rejects streaming entities the helper
disables itself so the caller's ``final()`` still delivers the answer.
"""
from __future__ import annotations

import time
from typing import Any, Optional

from botbuilder.core import TurnContext
from botbuilder.schema import Activity, ActivityTypes, Attachment


class BotStreamer:
    """Drives a single streaming response on one turn context."""

    def __init__(self, turn_context: TurnContext, *, min_interval: float = 1.0):
        self._ctx = turn_context
        self._min_interval = min_interval  # throttle interim updates (~1/sec)
        self._stream_id: Optional[str] = None
        self._sequence = 0
        self._enabled = True
        self._last_send = 0.0

    @property
    def enabled(self) -> bool:
        return self._enabled

    def _entity(self, stream_type: str, *, include_sequence: bool = True) -> dict:
        ent: dict[str, Any] = {"type": "streaminfo", "streamType": stream_type}
        if self._stream_id:
            ent["streamId"] = self._stream_id
        if include_sequence:
            ent["streamSequence"] = self._sequence
        return ent

    async def update(
        self, text: str, *, stream_type: str = "informative", force: bool = False
    ) -> None:
        """Send an interim streaming update (throttled unless ``force``).

        ``stream_type`` is ``informative`` for status lines or ``streaming``
        for partial answer content. No-ops once streaming has been disabled by
        a prior send failure.
        """
        if not self._enabled or not text:
            return
        now = time.monotonic()
        if not force and (now - self._last_send) < self._min_interval:
            return
        self._sequence += 1
        activity = Activity(
            type=ActivityTypes.typing,
            text=text,
            entities=[self._entity(stream_type)],
        )
        try:
            resp = await self._ctx.send_activity(activity)
            if self._stream_id is None and resp is not None:
                self._stream_id = getattr(resp, "id", None)
            self._last_send = now
        except Exception:
            # Channel doesn't support streaming entities — stop trying so the
            # final message still goes out cleanly.
            self._enabled = False

    async def final(
        self, text: str, attachment: Optional[Attachment] = None
    ) -> None:
        """Send the terminal message (text canonical, optional card attachment)."""
        activity = Activity(type=ActivityTypes.message, text=text or "")
        if attachment is not None:
            activity.attachments = [attachment]
        # Only tag as a streaming "final" if we actually established a stream.
        if self._enabled and self._stream_id:
            activity.entities = [self._entity("final", include_sequence=False)]
        try:
            await self._ctx.send_activity(activity)
        except Exception:
            # Last-ditch: plain message with no streaming entities.
            fallback = Activity(type=ActivityTypes.message, text=text or "")
            if attachment is not None:
                fallback.attachments = [attachment]
            await self._ctx.send_activity(fallback)
