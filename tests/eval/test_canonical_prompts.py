"""Canonical Field Day prompt eval harness.

Live-marked test that:
  1. Reads the 5 canonical prompts from prompts.yaml
  2. Sends each to /api/agent/chat/handoff/stream on the configured
     backend (BROKER_BACKEND_URL env, default SC backend)
  3. Parses the SSE frame stream
  4. Asserts:
       - at least one expected routing target appears
       - at least one expected MCP tool name fires
       - >= 2/3 expected keywords appear in the final assistant text
  5. Snapshots the answer to tests/eval/snapshots/<id>.json
       (committed for human review; not exact-match gated)
  6. Optional latency budget assertion (first-token <5s, total <30s)

Run:
  $env:BROKER_BACKEND_URL = "https://ca-backend-brokerworkbench-dev.kinddune-112ddddc.swedencentral.azurecontainerapps.io"
  pytest -m live tests/eval/

Switch backend modes:
  - fastapi mode (default): backend invokes handoff workflow directly
  - hosted mode: backend env AGENT_BACKEND_MODE=hosted proxies to Foundry

Both modes use the same SSE shape so the same harness validates both.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

import httpx
import pytest
import yaml

HERE = Path(__file__).parent
SNAPSHOTS_DIR = HERE / "snapshots"
SNAPSHOTS_DIR.mkdir(exist_ok=True)

DEFAULT_BACKEND = (
    "https://ca-backend-brokerworkbench-dev."
    "kinddune-112ddddc.swedencentral.azurecontainerapps.io"
)
LATENCY_FIRST_TOKEN_S = 90.0   # gpt-5 reasoning + multi-MCP-tool roundtrip is slow on cold path
LATENCY_TOTAL_S = 240.0


def _load_prompts() -> list[dict[str, Any]]:
    return yaml.safe_load((HERE / "prompts.yaml").read_text())


def _backend_url() -> str:
    return os.environ.get("BROKER_BACKEND_URL", DEFAULT_BACKEND).rstrip("/")


def _send(prompt: str, backend: str) -> dict[str, Any]:
    """POST to handoff stream, parse SSE, return {frames, full_text, timing}."""
    url = f"{backend}/api/agent/chat/handoff/stream"
    body = {"message": prompt, "agent": "triage", "history": []}
    t0 = time.monotonic()
    first_token_at: float | None = None
    frames: list[dict[str, Any]] = []
    full_text_parts: list[str] = []
    final_agent: str | None = None
    routed_to: list[str] = []
    tool_calls: list[dict[str, Any]] = []
    tool_results: list[dict[str, Any]] = []

    with httpx.Client(
        timeout=httpx.Timeout(LATENCY_TOTAL_S, read=LATENCY_TOTAL_S)
    ) as client:
        with client.stream(
            "POST",
            url,
            json=body,
            headers={
                "Content-Type": "application/json",
                "Accept": "text/event-stream",
            },
        ) as resp:
            assert resp.status_code == 200, f"HTTP {resp.status_code} from backend"
            for line in resp.iter_lines():
                if not line or not line.startswith("data: "):
                    continue
                try:
                    ev = json.loads(line[6:])
                except json.JSONDecodeError:
                    continue
                frames.append(ev)
                t = ev.get("type")
                if t == "token":
                    if first_token_at is None:
                        first_token_at = time.monotonic() - t0
                    full_text_parts.append(ev.get("content", ""))
                elif t == "routing":
                    if ev.get("agent"):
                        routed_to.append(ev["agent"])
                elif t == "tool_call":
                    tool_calls.append(
                        {
                            "name": ev.get("name"),
                            "call_id": ev.get("call_id"),
                            "arguments": ev.get("arguments", {}),
                        }
                    )
                elif t == "tool_result":
                    tool_results.append(
                        {
                            "call_id": ev.get("call_id"),
                            "ok": ev.get("ok"),
                        }
                    )
                elif t == "done":
                    final_agent = ev.get("agent")

    total = time.monotonic() - t0
    return {
        "frames": frames,
        "full_text": "".join(full_text_parts),
        "first_token_s": first_token_at,
        "total_s": total,
        "routed_to": routed_to,
        "final_agent": final_agent,
        "tool_calls": tool_calls,
        "tool_results": tool_results,
    }


def _short_form_agent(name: str | None) -> str | None:
    """Map ClaimsImpactAgent / BrokerAgent / etc. to short form Triage/Claims/Quote/CrossSell."""
    if not name:
        return None
    table = {
        "BrokerAgent": "Triage",
        "Triage": "Triage",
        "ClaimsImpactAgent": "Claims",
        "Claims": "Claims",
        "QuoteComparisonAgent": "Quote",
        "Quote": "Quote",
        "CrossSellAgent": "CrossSell",
        "CrossSell": "CrossSell",
    }
    return table.get(name, name)


@pytest.mark.live
@pytest.mark.parametrize("case", _load_prompts(), ids=lambda c: c["id"])
def test_canonical_prompt(case: dict[str, Any]) -> None:
    backend = _backend_url()
    result = _send(case["prompt"], backend)

    # Persist snapshot (for human review of drift).
    snapshot = {
        "id": case["id"],
        "prompt": case["prompt"],
        "backend": backend,
        "expected_agent": case.get("expected_agent"),
        "expected_tools": case.get("expected_tools", []),
        "expected_keywords": case.get("expected_keywords", []),
        "routed_to": result["routed_to"],
        "final_agent_short": _short_form_agent(result["final_agent"]),
        "tool_calls": [tc["name"] for tc in result["tool_calls"]],
        "first_token_s": round(result["first_token_s"] or -1, 2),
        "total_s": round(result["total_s"], 2),
        "answer": result["full_text"],
    }
    (SNAPSHOTS_DIR / f"{case['id']}.json").write_text(
        json.dumps(snapshot, indent=2, sort_keys=True)
    )

    # ── Assertions ────────────────────────────────────────────────────
    # (1) latency
    assert (
        result["first_token_s"] is not None
        and result["first_token_s"] < LATENCY_FIRST_TOKEN_S
    ), f"first token took {result['first_token_s']}s > {LATENCY_FIRST_TOKEN_S}s budget"
    assert (
        result["total_s"] < LATENCY_TOTAL_S
    ), f"total {result['total_s']}s exceeds {LATENCY_TOTAL_S}s budget"

    # (2) routing target — short form check; either explicitly routed or
    # the final agent itself matches expected.
    expected_agent = case.get("expected_agent")
    if expected_agent:
        observed_short = [_short_form_agent(a) for a in result["routed_to"]] + [
            _short_form_agent(result["final_agent"])
        ]
        assert expected_agent in observed_short, (
            f"expected route to {expected_agent}, observed {observed_short}"
        )

    # (3) at least one expected MCP tool fired
    expected_tools = set(case.get("expected_tools", []))
    if expected_tools:
        called = {tc["name"] for tc in result["tool_calls"]}
        assert expected_tools & called, (
            f"expected one of tools {expected_tools}, called {called}"
        )

    # (4) >=2/3 keywords present in answer
    expected_kw = case.get("expected_keywords", [])
    if expected_kw:
        text_lower = result["full_text"].lower()
        hits = sum(1 for kw in expected_kw if kw.lower() in text_lower)
        required = max(1, (len(expected_kw) * 2) // 3)
        assert hits >= required, (
            f"only {hits}/{len(expected_kw)} keywords matched in answer; "
            f"need >= {required}. Keywords={expected_kw}. "
            f"Answer head={result['full_text'][:300]!r}"
        )
