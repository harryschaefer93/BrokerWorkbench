"""Coverage-tool tests: get_coverage_gaps."""

from __future__ import annotations

import pytest

from tests.conftest import tool_result


@pytest.mark.parametrize("client_id", ["CLI001", "CLI010", "CLI025"])
async def test_get_coverage_gaps_happy_path(mcp_session, client_id):
    async with mcp_session() as client:
        res = await client.call_tool("get_coverage_gaps", {"client_id": client_id})
    data = tool_result(res)
    assert data["client_id"] == client_id
    assert isinstance(data["coverage_gaps"], list)
    assert isinstance(data["current_coverage_types"], list)
    assert isinstance(data["current_policies"], int)
    assert data["current_policies"] >= 1


async def test_get_coverage_gaps_invalid_id(mcp_session):
    async with mcp_session() as client:
        res = await client.call_tool("get_coverage_gaps", {"client_id": "CLI9999"})
    data = tool_result(res)
    assert "error" in data


async def test_coverage_gap_shape_is_consistent(mcp_session):
    """Every gap entry must carry the same minimal contract."""
    async with mcp_session() as client:
        res = await client.call_tool("get_coverage_gaps", {"client_id": "CLI001"})
    data = tool_result(res)
    for gap in data["coverage_gaps"]:
        assert {"policy_type", "priority", "reason", "available_carriers"}.issubset(gap.keys())
        assert gap["priority"] in {"high", "medium", "low"}
