"""Client-tool tests: get_client_info, get_all_clients, get_client_policies."""

from __future__ import annotations

import pytest

from tests.conftest import tool_result


@pytest.mark.parametrize("client_id", ["CLI001", "CLI005", "CLI010"])
async def test_get_client_info_happy_path(mcp_session, client_id):
    async with mcp_session() as client:
        res = await client.call_tool("get_client_info", {"client_id": client_id})
    data = tool_result(res)
    assert data["client_id"] == client_id
    assert data.get("name")
    assert data.get("industry")
    assert isinstance(data.get("total_policies"), int)


async def test_get_client_info_unknown_returns_error(mcp_session):
    async with mcp_session() as client:
        res = await client.call_tool("get_client_info", {"client_id": "CLI9999"})
    data = tool_result(res)
    assert "error" in data


async def test_get_all_clients_returns_seeded_set(mcp_session):
    async with mcp_session() as client:
        res = await client.call_tool("get_all_clients", {})
    data = tool_result(res)
    assert isinstance(data, list)
    assert len(data) >= 40, f"Expected ~50 seeded clients, got {len(data)}"
    sample = data[0]
    for key in ("client_id", "name", "industry", "total_policies", "total_premium"):
        assert key in sample, f"Missing key {key} in {sample}"
    assert sample["client_id"].startswith("CLI")


@pytest.mark.parametrize("client_id", ["CLI001", "CLI007", "CLI020"])
async def test_get_client_policies_happy_path(mcp_session, client_id):
    async with mcp_session() as client:
        res = await client.call_tool("get_client_policies", {"client_id": client_id})
    data = tool_result(res)
    assert isinstance(data, list)
    # Seeded clients all get 2–6 policies.
    assert len(data) >= 1, f"{client_id} returned no policies"
    for p in data:
        assert p["policy_id"].startswith("POL")
        assert p["carrier_id"].startswith("CAR")
        assert "urgency" in p


async def test_get_client_policies_invalid_id_returns_error(mcp_session):
    async with mcp_session() as client:
        res = await client.call_tool("get_client_policies", {"client_id": "CLI9999"})
    data = tool_result(res)
    assert isinstance(data, list)
    assert data and "error" in data[0]
