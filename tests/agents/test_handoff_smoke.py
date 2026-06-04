"""Live smoke test for the BrokerWorkbench Foundry handoff workflow.

Marked ``live`` because it requires:

* a live MCP server (auto-spun by the ``mcp_server_url`` fixture in
  :mod:`tests.conftest`)
* a real Azure OpenAI deployment reachable via ``AZURE_AI_FOUNDRY_ENDPOINT``
* the developer / managed identity to have ``Cognitive Services OpenAI User``
  permission on that deployment

Opt in to running this test with::

    pytest -m live tests/agents/test_handoff_smoke.py

It is excluded from the default test run so CI / dev loops do not pay the
model-call cost or fail when credentials are not configured.
"""
from __future__ import annotations

import os

import pytest


@pytest.mark.live
async def test_handoff_smoke_cli001_claims_history(mcp_server_url: str) -> None:
    """End-to-end: triage agent should route a claims-history question and
    return text mentioning claims or loss-ratio data for CLI001."""
    # Hard-fail with a clear message if the Azure endpoint isn't configured,
    # rather than a noisy SDK auth error deep in the workflow.
    if not os.getenv("AZURE_AI_FOUNDRY_ENDPOINT"):
        pytest.skip("AZURE_AI_FOUNDRY_ENDPOINT not set; live smoke test skipped.")

    from backend.agents.foundry.handoff import build_handoff

    workflow, mcp_tool = await build_handoff(mcp_url=mcp_server_url)

    transcript_parts: list[str] = []
    async with mcp_tool:
        async for event in workflow.run(
            "Show CLI001 claims history",
            stream=True,
        ):
            # Coerce every event to text and keep the cumulative transcript.
            transcript_parts.append(str(event))

    transcript = "\n".join(transcript_parts).lower()
    assert transcript, "Handoff workflow produced no events"
    assert (
        "claim" in transcript or "loss" in transcript
    ), (
        "Handoff workflow output did not mention claims or loss data. "
        f"Transcript (first 500 chars):\n{transcript[:500]}"
    )
