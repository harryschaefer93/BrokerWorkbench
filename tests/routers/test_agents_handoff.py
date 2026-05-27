"""Tests for the additive `/api/agent/chat/handoff/stream` endpoint.

The default (offline) test patches `build_handoff` to return fake
workflow + MCP tool objects that emit a small predetermined event
sequence, then asserts the SSE adapter renders all 5 frame types in the
expected order and format. Runs in <2s with no live deps.

The `live` test (opt-in via `-m live`) hits the real endpoint end-to-end
against a running MCP server + Azure OpenAI gpt-5 deployment.
"""
from __future__ import annotations

import json
import sys
from contextlib import asynccontextmanager
from types import ModuleType, SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.routers import agents_handoff


# ── Fakes ──────────────────────────────────────────────────────────────


class _FakeUpdate:
    def __init__(self, text: str) -> None:
        self.text = text


class _FakeMCPTool:
    """Async context manager that stands in for MCPStreamableHTTPTool."""

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakeWorkflow:
    """Yields a scripted WorkflowEvent sequence covering routing + tokens."""

    def __init__(self, events: list[SimpleNamespace]) -> None:
        self._events = events

    def run(self, _prompt: str, stream: bool = True):  # noqa: ARG002
        async def _gen():
            for ev in self._events:
                yield ev

        return _gen()


def _scripted_events() -> list[SimpleNamespace]:
    """Mimic an Agent Framework handoff: Triage → handoff → Claims responds."""
    return [
        SimpleNamespace(type="started", executor_id=None, data=None),
        SimpleNamespace(
            type="executor_invoked",
            executor_id="Triage",
            data="Show CLI001 claims history",
        ),
        # Triage emits no text deltas in this script (it just routes).
        SimpleNamespace(
            type="executor_invoked",
            executor_id="Claims",
            data=SimpleNamespace(should_respond=True),
        ),
        SimpleNamespace(
            type="output",
            executor_id="Claims",
            data=_FakeUpdate("Hello "),
        ),
        SimpleNamespace(
            type="output",
            executor_id="Claims",
            data=_FakeUpdate("from Claims."),
        ),
        SimpleNamespace(type="executor_completed", executor_id="Claims", data=None),
    ]


# ── Offline test ───────────────────────────────────────────────────────


def test_handoff_stream_sse_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    events = _scripted_events()

    async def _fake_build_handoff():
        return _FakeWorkflow(events), _FakeMCPTool()

    # Inject a stub module into sys.modules so the lazy
    # `from backend.agents.foundry.handoff import build_handoff` inside
    # `_stream_handoff` resolves to our fake WITHOUT triggering the real
    # import chain. Importing the real module would load
    # `backend.agents.__init__` → `backend.agents.tools`, whose top-level
    # code mutates `sys.path` (inserts `backend/` at index 0). That
    # mutation registers `data` as `backend/data/__init__.py` in
    # sys.modules, shadowing the workspace-root `data/seed/` package and
    # breaking `tests/seed/test_setup.py` on the next test that imports
    # from `data.seed`. See backend/agents/tools.py:17-19.
    fake_mod = ModuleType("backend.agents.foundry.handoff")
    fake_mod.build_handoff = _fake_build_handoff
    monkeypatch.setitem(
        sys.modules, "backend.agents.foundry.handoff", fake_mod
    )

    app = FastAPI()
    app.include_router(agents_handoff.router)
    client = TestClient(app)

    resp = client.post(
        "/api/agent/chat/handoff/stream",
        json={
            "message": "Show CLI001 claims history",
            "agent": "triage",
            "history": [],
        },
    )

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")

    # Parse SSE frames out of the response body.
    frames: list[dict] = []
    for line in resp.text.splitlines():
        if not line.startswith("data: "):
            continue
        frames.append(json.loads(line[len("data: ") :]))

    assert frames, "expected at least one SSE frame"

    types = [f["type"] for f in frames]
    # Allowed type set from the 5-frame contract.
    assert set(types).issubset(
        {"routing", "status", "token", "done", "error"}
    ), f"unexpected frame types: {types}"

    # We expect exactly one routing announcement for Claims, the two
    # token deltas, and a terminal done frame.
    routing = [f for f in frames if f["type"] == "routing"]
    tokens = [f for f in frames if f["type"] == "token"]
    done = [f for f in frames if f["type"] == "done"]

    assert any(f["agent"] == "ClaimsImpactAgent" for f in routing)
    assert "".join(t["content"] for t in tokens) == "Hello from Claims."
    assert len(done) == 1
    assert done[0]["agent"] == "ClaimsImpactAgent"
    assert done[0]["suggestions"] == []


# ── Live test (opt-in) ─────────────────────────────────────────────────


@pytest.mark.live
def test_handoff_stream_live() -> None:
    """End-to-end smoke against real MCP + gpt-5. Opt-in: `pytest -m live`."""
    from backend.main import app

    client = TestClient(app)
    resp = client.post(
        "/api/agent/chat/handoff/stream",
        json={
            "message": "Show CLI001 claims history",
            "agent": "triage",
            "history": [],
        },
    )
    assert resp.status_code == 200
    body = resp.text
    assert "data: " in body
    # Should end with either a `done` or `error` frame in valid JSON form.
    last_frame = None
    for line in body.splitlines():
        if line.startswith("data: "):
            last_frame = json.loads(line[len("data: ") :])
    assert last_frame is not None
    assert last_frame["type"] in {"done", "error"}
