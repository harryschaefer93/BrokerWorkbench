"""Unit tests for the hosted-agent interactive-latency knobs.

Covers:
- ``_build_prompt`` history-window tuning (``CHAT_HISTORY_TURNS``) in the
  backend SSE proxy.
- ``_default_options`` reasoning + output-token policy in the hosted
  agent entry point.

These are pure config/helper functions — no live Azure or MCP needed.
"""

from __future__ import annotations

import importlib

import pytest

from backend.routers import agents_handoff


def _history(n: int) -> list[dict]:
    out: list[dict] = []
    for i in range(n):
        out.append({"role": "user", "content": f"u{i}"})
        out.append({"role": "assistant", "content": f"a{i}"})
    return out


def test_build_prompt_no_history_returns_message():
    assert agents_handoff._build_prompt("hi", None) == "hi"
    assert agents_handoff._build_prompt("hi", []) == "hi"


def test_build_prompt_default_window_is_six_turns(monkeypatch):
    monkeypatch.delenv("CHAT_HISTORY_TURNS", raising=False)
    prompt = agents_handoff._build_prompt("now", _history(10))
    # 6-turn window => the 6 most recent history lines + the new user line.
    lines = prompt.split("\n")
    assert lines[-1] == "user: now"
    assert len(lines) == 7
    # Oldest replayed turn should be from the tail, not turn 0.
    assert "u0" not in prompt and "a0" not in prompt


def test_build_prompt_window_is_configurable(monkeypatch):
    monkeypatch.setenv("CHAT_HISTORY_TURNS", "2")
    prompt = agents_handoff._build_prompt("now", _history(10))
    lines = prompt.split("\n")
    assert len(lines) == 3  # 2 history + new message


def test_build_prompt_zero_window_disables_replay(monkeypatch):
    monkeypatch.setenv("CHAT_HISTORY_TURNS", "0")
    assert agents_handoff._build_prompt("now", _history(5)) == "now"


def test_build_prompt_invalid_window_falls_back(monkeypatch):
    monkeypatch.setenv("CHAT_HISTORY_TURNS", "not-a-number")
    prompt = agents_handoff._build_prompt("now", _history(10))
    assert len(prompt.split("\n")) == 7  # default 6 + message


# ── Hosted agent default-options policy ───────────────────────────────


@pytest.fixture()
def hosted_main():
    return importlib.import_module("agents.foundry.hosted.main")


def test_default_options_defaults(monkeypatch, hosted_main):
    monkeypatch.delenv("REASONING_EFFORT", raising=False)
    monkeypatch.delenv("CHAT_MAX_OUTPUT_TOKENS", raising=False)
    opts = hosted_main._default_options()
    assert opts["reasoning"] == {"effort": "low"}
    assert opts["max_tokens"] == 700


def test_default_options_custom_values(monkeypatch, hosted_main):
    monkeypatch.setenv("REASONING_EFFORT", "minimal")
    monkeypatch.setenv("CHAT_MAX_OUTPUT_TOKENS", "300")
    opts = hosted_main._default_options()
    assert opts["reasoning"] == {"effort": "minimal"}
    assert opts["max_tokens"] == 300


def test_default_options_disable_token_cap(monkeypatch, hosted_main):
    monkeypatch.setenv("CHAT_MAX_OUTPUT_TOKENS", "0")
    opts = hosted_main._default_options()
    assert "max_tokens" not in opts


def test_default_options_disable_reasoning(monkeypatch, hosted_main):
    monkeypatch.setenv("REASONING_EFFORT", "default")
    monkeypatch.setenv("CHAT_MAX_OUTPUT_TOKENS", "default")
    assert hosted_main._default_options() == {}
