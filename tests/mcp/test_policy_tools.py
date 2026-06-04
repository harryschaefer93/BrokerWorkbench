"""Policy-tool tests: get_policy_details, get_renewals_by_urgency."""

from __future__ import annotations

import pytest

from tests.conftest import tool_result


@pytest.mark.parametrize("policy_id", ["POL001", "POL005", "POL010"])
async def test_get_policy_details_happy_path(mcp_session, policy_id):
    async with mcp_session() as client:
        res = await client.call_tool("get_policy_details", {"policy_id": policy_id})
    data = tool_result(res)
    assert data["policy_id"] == policy_id
    assert data["carrier_id"].startswith("CAR")
    assert data["client_id"].startswith("CLI")
    assert "premium" in data
    assert data.get("urgency") in {"critical", "high", "medium", "low", "expired", "unknown"}


async def test_get_policy_details_unknown_returns_error(mcp_session):
    async with mcp_session() as client:
        res = await client.call_tool("get_policy_details", {"policy_id": "POL9999"})
    data = tool_result(res)
    assert "error" in data


async def test_get_renewals_by_urgency_no_filter(mcp_session):
    async with mcp_session() as client:
        res = await client.call_tool("get_renewals_by_urgency", {})
    data = tool_result(res)
    assert isinstance(data, dict)
    assert "renewals" in data
    assert isinstance(data["total_renewals"], int)
    assert data["total_renewals"] >= 1
    # Buckets sum to total (when no filter applied) — the seeder always
    # produces some critical + high + medium policies in the 0-90 window.
    bucket_sum = sum(data[k] for k in ("critical_count", "high_count", "medium_count", "low_count"))
    assert bucket_sum == data["total_renewals"]


async def test_get_renewals_by_urgency_critical_only(mcp_session):
    async with mcp_session() as client:
        res = await client.call_tool(
            "get_renewals_by_urgency", {"urgency": "critical", "days_ahead": 30}
        )
    data = tool_result(res)
    assert isinstance(data, dict)
    for r in data["renewals"]:
        assert r["urgency"] == "critical"
        assert r["days_until_renewal"] is None or r["days_until_renewal"] <= 30


async def test_get_renewals_by_urgency_invalid(mcp_session):
    async with mcp_session() as client:
        res = await client.call_tool(
            "get_renewals_by_urgency", {"urgency": "extreme"}
        )
    data = tool_result(res)
    assert "error" in data
