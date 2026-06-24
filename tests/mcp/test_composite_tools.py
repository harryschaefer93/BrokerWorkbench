"""Composite-tool tests: get_client_brief, get_renewal_brief,
get_quote_workup, get_claims_workup.

These tools collapse common multi-call broker workflows into a single MCP
round trip. They reuse the granular tool functions internally, so the
assertions focus on (a) the consolidated shape and (b) parity with the
granular tools they replace.
"""

from __future__ import annotations

import pytest

from tests.conftest import tool_result


# ── get_client_brief ──────────────────────────────────────────────────


@pytest.mark.parametrize("client_id", ["CLI001", "CLI010", "CLI020"])
async def test_get_client_brief_happy_path(mcp_session, client_id):
    async with mcp_session() as client:
        res = await client.call_tool("get_client_brief", {"client_id": client_id})
    data = tool_result(res)
    assert data["client"]["client_id"] == client_id
    assert isinstance(data["policies"], list)
    assert data["policy_count"] == len(data["policies"])
    assert isinstance(data["upcoming_renewals"], list)
    assert len(data["upcoming_renewals"]) <= 5
    # upcoming renewals are sorted soonest-first
    days = [r["days_until_renewal"] for r in data["upcoming_renewals"]]
    assert days == sorted(days)
    assert "coverage_gaps" in data
    assert "claims_summary" in data


async def test_get_client_brief_unknown_returns_error(mcp_session):
    async with mcp_session() as client:
        res = await client.call_tool("get_client_brief", {"client_id": "CLI9999"})
    data = tool_result(res)
    assert "error" in data


async def test_client_brief_matches_granular(mcp_session):
    """The brief's policy list equals get_client_policies output."""
    async with mcp_session() as client:
        brief = tool_result(
            await client.call_tool("get_client_brief", {"client_id": "CLI001"})
        )
        policies = tool_result(
            await client.call_tool("get_client_policies", {"client_id": "CLI001"})
        )
    assert {p["policy_id"] for p in brief["policies"]} == {
        p["policy_id"] for p in policies
    }


# ── get_renewal_brief ─────────────────────────────────────────────────


async def test_renewal_brief_book_wide_delegates(mcp_session):
    """Without a client_id the brief mirrors get_renewals_by_urgency."""
    async with mcp_session() as client:
        brief = tool_result(
            await client.call_tool("get_renewal_brief", {"days_ahead": 90})
        )
        urg = tool_result(
            await client.call_tool(
                "get_renewals_by_urgency", {"days_ahead": 90}
            )
        )
    assert brief["total_renewals"] == urg["total_renewals"]
    assert brief["total_premium_at_risk"] == urg["total_premium_at_risk"]


@pytest.mark.parametrize("client_id", ["CLI001", "CLI007"])
async def test_renewal_brief_client_scoped(mcp_session, client_id):
    async with mcp_session() as client:
        data = tool_result(
            await client.call_tool(
                "get_renewal_brief", {"client_id": client_id, "days_ahead": 365}
            )
        )
    assert data["client_id"] == client_id
    assert isinstance(data["renewals"], list)
    for r in data["renewals"]:
        assert r["client_name"] == data["client_name"]
        assert r["carrier_name"]
        assert "priority_score" in r
        assert r["days_until_renewal"] <= 365
    # renewals sorted by priority score, highest first
    scores = [r["priority_score"] for r in data["renewals"]]
    assert scores == sorted(scores, reverse=True)


async def test_renewal_brief_invalid_urgency(mcp_session):
    async with mcp_session() as client:
        data = tool_result(
            await client.call_tool(
                "get_renewal_brief", {"client_id": "CLI001", "urgency": "bogus"}
            )
        )
    assert "error" in data


# ── get_quote_workup ──────────────────────────────────────────────────


async def test_quote_workup_all_lines(mcp_session):
    async with mcp_session() as client:
        data = tool_result(
            await client.call_tool("get_quote_workup", {"client_id": "CLI001"})
        )
    assert data["client"]["client_id"] == "CLI001"
    assert isinstance(data["quoted_policy_types"], list)
    assert isinstance(data["carrier_comparisons"], dict)
    # every quoted type carries a comparison entry
    assert set(data["carrier_comparisons"].keys()) == set(
        data["quoted_policy_types"]
    )


async def test_quote_workup_specific_line(mcp_session):
    async with mcp_session() as client:
        data = tool_result(
            await client.call_tool(
                "get_quote_workup",
                {"client_id": "CLI001", "policy_type": "cyber_liability"},
            )
        )
    assert data["quoted_policy_types"] == ["cyber_liability"]
    assert "cyber_liability" in data["carrier_comparisons"]


async def test_quote_workup_invalid_type(mcp_session):
    async with mcp_session() as client:
        data = tool_result(
            await client.call_tool(
                "get_quote_workup",
                {"client_id": "CLI001", "policy_type": "spaceship"},
            )
        )
    assert "error" in data


async def test_quote_workup_unknown_client(mcp_session):
    async with mcp_session() as client:
        data = tool_result(
            await client.call_tool("get_quote_workup", {"client_id": "CLI9999"})
        )
    assert "error" in data


# ── get_claims_workup ─────────────────────────────────────────────────


@pytest.mark.parametrize("client_id", ["CLI001", "CLI010"])
async def test_claims_workup_happy_path(mcp_session, client_id):
    async with mcp_session() as client:
        data = tool_result(
            await client.call_tool("get_claims_workup", {"client_id": client_id})
        )
    assert data["client_id"] == client_id
    assert "summary" in data
    assert "renewal_impact" in data
    assert isinstance(data["claims_history"], list)
    assert isinstance(data["recommendations"], list)
    assert "loss_ratio_trend" in data


async def test_claims_workup_matches_granular(mcp_session):
    async with mcp_session() as client:
        workup = tool_result(
            await client.call_tool("get_claims_workup", {"client_id": "CLI001"})
        )
        history = tool_result(
            await client.call_tool("get_claims_history", {"client_id": "CLI001"})
        )
    assert workup["summary"] == history["summary"]
    assert workup["renewal_impact"] == history["renewal_impact"]


async def test_claims_workup_unknown_client(mcp_session):
    async with mcp_session() as client:
        data = tool_result(
            await client.call_tool("get_claims_workup", {"client_id": "CLI9999"})
        )
    assert "error" in data
