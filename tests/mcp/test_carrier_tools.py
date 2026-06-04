"""Carrier-tool tests: get_carriers_for_policy_type, compare_carrier_rates."""

from __future__ import annotations

import pytest

from tests.conftest import tool_result


@pytest.mark.parametrize(
    "policy_type", ["general_liability", "cyber_liability", "workers_comp"]
)
async def test_get_carriers_for_policy_type_happy(mcp_session, policy_type):
    async with mcp_session() as client:
        res = await client.call_tool(
            "get_carriers_for_policy_type", {"policy_type": policy_type}
        )
    data = tool_result(res)
    assert isinstance(data, list) and data, f"No carriers for {policy_type}"
    for c in data:
        assert c["carrier_id"].startswith("CAR")
        assert policy_type in c.get("supported_lines", []), (
            f"{c['name']} doesn't list {policy_type}"
        )


async def test_get_carriers_for_invalid_policy_type(mcp_session):
    async with mcp_session() as client:
        res = await client.call_tool(
            "get_carriers_for_policy_type", {"policy_type": "not_a_product"}
        )
    data = tool_result(res)
    assert isinstance(data, list) and data and "error" in data[0]


async def test_compare_carrier_rates_happy(mcp_session):
    async with mcp_session() as client:
        res = await client.call_tool(
            "compare_carrier_rates",
            {
                "policy_type": "general_liability",
                "coverage_limit": 1_000_000,
                "industry": "Technology",
            },
        )
    data = tool_result(res)
    assert isinstance(data, list) and data, "No rate quotes returned"
    premiums = [q["estimated_annual_premium"] for q in data]
    assert premiums == sorted(premiums), "Quotes are not sorted ascending by premium"
    for q in data:
        assert q["carrier_id"].startswith("CAR")
        assert q["estimated_annual_premium"] > 0
        assert q["coverage_limit"] == 1_000_000


async def test_compare_carrier_rates_invalid_policy_type(mcp_session):
    async with mcp_session() as client:
        res = await client.call_tool(
            "compare_carrier_rates",
            {"policy_type": "bogus", "coverage_limit": 1_000_000, "industry": "Retail"},
        )
    data = tool_result(res)
    assert isinstance(data, list) and data and "error" in data[0]


async def test_compare_carrier_rates_invalid_coverage_limit(mcp_session):
    async with mcp_session() as client:
        res = await client.call_tool(
            "compare_carrier_rates",
            {
                "policy_type": "general_liability",
                "coverage_limit": "not a number",
                "industry": "Retail",
            },
        )
    # FastMCP wraps pydantic validation errors as a plain text error block.
    # The tool result will either be a list with an "error" key or the raw
    # error string. Either way, no quotes should be produced.
    data = tool_result(res)
    if isinstance(data, list):
        assert data and "error" in data[0]
    else:
        assert isinstance(data, str) and "error" in data.lower()
