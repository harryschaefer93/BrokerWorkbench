"""Behaviour tests for the inline streaming turn handler (``bot/bot.py``).

Drives ``BrokerBot._stream_turn`` with a scripted backend event generator and a
fake turn context, asserting the surface gets an immediate ack, interim status,
a correct final answer, heartbeat keep-alives, and graceful error handling.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

import bot as bot_module
from bot import BrokerBot


class _Resp:
    def __init__(self, id: str) -> None:
        self.id = id


class FakeCtx:
    def __init__(self) -> None:
        self.activities: list = []
        self._n = 0

    async def send_activity(self, activity):
        self.activities.append(activity)
        self._n += 1
        return _Resp(f"s-{self._n}")


def _make_bot() -> BrokerBot:
    settings = SimpleNamespace(backend_url="http://backend", microsoft_app_id="app-id")
    return BrokerBot(settings, adapter=None)


def _texts(ctx: FakeCtx) -> list[str]:
    return [a.text for a in ctx.activities]


async def _gen(events, delay: float = 0.0):
    for ev in events:
        if delay:
            await asyncio.sleep(delay)
        yield ev


async def test_stream_turn_routes_streams_and_finalizes(monkeypatch):
    bot = _make_bot()
    events = [
        {"type": "routing", "agent": "ClaimsImpactAgent", "content": "Routing…"},
        {"type": "token", "content": "Hello "},
        {"type": "token", "content": "from Claims."},
        {"type": "done", "agent": "ClaimsImpactAgent", "suggestions": []},
    ]
    monkeypatch.setattr(
        bot, "_iter_backend_events", lambda message, history: _gen(events)
    )

    ctx = FakeCtx()
    await bot._stream_turn(ctx, "Show CLI001 claims history", "conv-1")

    # Immediate acknowledgement first.
    assert ctx.activities[0].text == "Looking into that…"
    # A specialist status line was surfaced.
    assert any("claims" in t.lower() for t in _texts(ctx))
    # Final message carries the aggregated answer + an Adaptive Card.
    final = ctx.activities[-1]
    assert final.type == "message"
    assert final.text == "Hello from Claims."
    assert final.attachments and len(final.attachments) == 1
    # History was recorded.
    assert bot._history["conv-1"][-1] == {
        "role": "assistant",
        "content": "Hello from Claims.",
    }


async def test_stream_turn_uses_done_content_when_no_tokens(monkeypatch):
    bot = _make_bot()
    events = [
        {"type": "done", "agent": "BrokerAgent", "content": "Final answer.", "suggestions": []},
    ]
    monkeypatch.setattr(
        bot, "_iter_backend_events", lambda message, history: _gen(events)
    )

    ctx = FakeCtx()
    await bot._stream_turn(ctx, "hi", "conv-2")
    assert ctx.activities[-1].text == "Final answer."


async def test_stream_turn_emits_heartbeat_on_silence(monkeypatch):
    bot = _make_bot()
    monkeypatch.setattr(bot_module, "_HEARTBEAT_SECONDS", 0.05)
    events = [
        {"type": "token", "content": "done thinking"},
        {"type": "done", "agent": "BrokerAgent", "suggestions": []},
    ]
    # 0.2s delay per event > 0.05s heartbeat window -> at least one keep-alive.
    monkeypatch.setattr(
        bot, "_iter_backend_events", lambda message, history: _gen(events, delay=0.2)
    )

    ctx = FakeCtx()
    await bot._stream_turn(ctx, "slow one", "conv-3")
    assert any("still working" in t.lower() for t in _texts(ctx))
    assert ctx.activities[-1].text == "done thinking"


async def test_stream_turn_handles_error_frame(monkeypatch):
    bot = _make_bot()
    events = [{"type": "error", "content": "upstream boom"}]
    monkeypatch.setattr(
        bot, "_iter_backend_events", lambda message, history: _gen(events)
    )

    ctx = FakeCtx()
    await bot._stream_turn(ctx, "bad", "conv-4")
    final = ctx.activities[-1]
    assert final.type == "message"
    # Error path still delivers a final message with an (error) card attachment.
    assert final.attachments and len(final.attachments) == 1
    # The failed turn is NOT written to history.
    assert "conv-4" not in bot._history or not bot._history["conv-4"]
