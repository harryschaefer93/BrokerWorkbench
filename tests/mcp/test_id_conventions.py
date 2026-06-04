"""ID convention tests: CLI001/POL001/CAR001 round-trip + graceful CLI999 error."""

from __future__ import annotations

import pytest

from tests.conftest import tool_result


async def test_cli001_roundtrip(mcp_session):
    async with mcp_session() as client:
        res = await client.call_tool("get_client_info", {"client_id": "CLI001"})
    data = tool_result(res)
    assert isinstance(data, dict)
    assert data.get("client_id") == "CLI001", f"Expected CLI001, got {data!r}"
    assert "name" in data


async def test_pol001_roundtrip(mcp_session):
    async with mcp_session() as client:
        res = await client.call_tool("get_policy_details", {"policy_id": "POL001"})
    data = tool_result(res)
    assert isinstance(data, dict)
    assert data.get("policy_id") == "POL001"
    assert data.get("carrier_id", "").startswith("CAR")
    assert data.get("client_id", "").startswith("CLI")


async def test_car001_appears_in_carrier_list(mcp_session):
    async with mcp_session() as client:
        res = await client.call_tool(
            "get_carriers_for_policy_type", {"policy_type": "general_liability"}
        )
    carriers = tool_result(res)
    assert isinstance(carriers, list) and carriers, "No carriers returned"
    for c in carriers:
        assert c["carrier_id"].startswith("CAR"), f"Bad id: {c['carrier_id']}"


@pytest.mark.parametrize("bad_id", ["CLI999", "CLI9999", "XYZ001"])
async def test_invalid_client_id_is_graceful(mcp_session, bad_id):
    async with mcp_session() as client:
        res = await client.call_tool("get_client_info", {"client_id": bad_id})
    data = tool_result(res)
    assert isinstance(data, dict)
    assert "error" in data, f"Expected error key for {bad_id}, got {data!r}"
