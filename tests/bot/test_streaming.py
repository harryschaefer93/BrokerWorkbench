"""Unit tests for the Bot Framework streaming helper (``bot/streaming.py``).

Verifies the M365 Copilot / Teams streaming contract: monotonic
``streamSequence`` starting at 1, ``streamId`` echoed from the first
``ResourceResponse`` id, a ``final`` message with no sequence, throttling, and
graceful degradation when a channel rejects streaming entities.
"""
from __future__ import annotations

import pytest

from streaming import BotStreamer


class _Resp:
    def __init__(self, id: str) -> None:
        self.id = id


class FakeCtx:
    """Records sent activities; optionally rejects streaming-tagged ones."""

    def __init__(self, reject_streaming: bool = False) -> None:
        self.activities: list = []
        self._reject = reject_streaming
        self._n = 0

    @staticmethod
    def _streaminfo(activity):
        for ent in activity.entities or []:
            if isinstance(ent, dict) and ent.get("type") == "streaminfo":
                return ent
        return None

    async def send_activity(self, activity):
        if self._reject and self._streaminfo(activity) is not None:
            raise RuntimeError("channel does not support streaming")
        self.activities.append(activity)
        self._n += 1
        return _Resp(f"stream-{self._n}")


def _info(activity):
    for ent in activity.entities or []:
        if isinstance(ent, dict) and ent.get("type") == "streaminfo":
            return ent
    return None


async def test_first_update_seq1_no_streamid_and_captures_id():
    ctx = FakeCtx()
    s = BotStreamer(ctx, min_interval=0.0)
    await s.update("Looking…", force=True)

    assert len(ctx.activities) == 1
    ent = _info(ctx.activities[0])
    assert ent["streamType"] == "informative"
    assert ent["streamSequence"] == 1
    assert "streamId" not in ent  # first activity has no id yet
    assert s._stream_id == "stream-1"


async def test_subsequent_updates_carry_streamid_and_increment():
    ctx = FakeCtx()
    s = BotStreamer(ctx, min_interval=0.0)
    await s.update("a", force=True)
    await s.update("ab", stream_type="streaming", force=True)

    ent2 = _info(ctx.activities[1])
    assert ent2["streamType"] == "streaming"
    assert ent2["streamSequence"] == 2
    assert ent2["streamId"] == "stream-1"


async def test_final_has_final_type_no_sequence_and_attachment():
    ctx = FakeCtx()
    s = BotStreamer(ctx, min_interval=0.0)
    await s.update("working", force=True)
    await s.final("the answer", attachment={"contentType": "card", "content": {}})

    final = ctx.activities[-1]
    assert final.type == "message"
    assert final.text == "the answer"
    assert final.attachments and len(final.attachments) == 1
    ent = _info(final)
    assert ent["streamType"] == "final"
    assert ent["streamId"] == "stream-1"
    assert "streamSequence" not in ent


async def test_update_is_throttled():
    ctx = FakeCtx()
    s = BotStreamer(ctx, min_interval=100.0)
    await s.update("first", force=True)  # establishes stream, resets last_send
    await s.update("second")  # within interval, not forced -> dropped
    assert len(ctx.activities) == 1


async def test_graceful_degradation_when_streaming_rejected():
    ctx = FakeCtx(reject_streaming=True)
    s = BotStreamer(ctx, min_interval=0.0)

    await s.update("status", force=True)  # raises internally -> disables
    assert s.enabled is False
    assert ctx.activities == []  # nothing recorded yet

    await s.final("plain answer", attachment={"contentType": "card", "content": {}})
    # Final has no streaminfo entity (no stream established) so it goes through.
    assert len(ctx.activities) == 1
    assert ctx.activities[0].text == "plain answer"
    assert _info(ctx.activities[0]) is None
