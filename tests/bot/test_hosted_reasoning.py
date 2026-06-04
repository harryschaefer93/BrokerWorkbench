"""Tests for the hosted-agent reasoning-effort cap (``hosted/main.py``).

The cap is the main interactive-latency lever for the M365 Copilot / Teams /
Web surfaces: it bounds gpt-5's hidden reasoning on every model call in the
tool loop. These tests assert the env-driven option logic and that the option
is wired into the hosted Agent's ``default_options``.
"""
from __future__ import annotations

import pytest

import agents.foundry.hosted.main as hosted_main


def test_default_effort_is_low(monkeypatch):
    monkeypatch.delenv("AGENT_REASONING_EFFORT", raising=False)
    assert hosted_main._reasoning_options() == {"reasoning": {"effort": "low"}}


@pytest.mark.parametrize("effort", ["minimal", "low", "medium", "high"])
def test_valid_efforts_are_passed_through(monkeypatch, effort):
    monkeypatch.setenv("AGENT_REASONING_EFFORT", effort)
    assert hosted_main._reasoning_options() == {"reasoning": {"effort": effort}}


@pytest.mark.parametrize("effort", ["default", "", "bogus", "LOWEST"])
def test_invalid_effort_falls_back_to_model_default(monkeypatch, effort):
    monkeypatch.setenv("AGENT_REASONING_EFFORT", effort)
    assert hosted_main._reasoning_options() == {}


def test_effort_is_case_insensitive(monkeypatch):
    monkeypatch.setenv("AGENT_REASONING_EFFORT", "LOW")
    assert hosted_main._reasoning_options() == {"reasoning": {"effort": "low"}}


async def test_build_workflow_agent_wires_reasoning(monkeypatch):
    """The constructed hosted Agent carries the reasoning option."""
    monkeypatch.setenv("AGENT_REASONING_EFFORT", "low")
    agent = await hosted_main._build_workflow_agent()
    assert agent.default_options.get("reasoning") == {"effort": "low"}


async def test_build_workflow_agent_omits_option_on_default(monkeypatch):
    monkeypatch.setenv("AGENT_REASONING_EFFORT", "default")
    agent = await hosted_main._build_workflow_agent()
    assert "reasoning" not in (agent.default_options or {})
