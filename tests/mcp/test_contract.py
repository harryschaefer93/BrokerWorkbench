"""MCP contract: verify all 10 tools are registered with valid JSON schemas."""

from __future__ import annotations

import pytest

EXPECTED_TOOLS = {
    "get_client_info",
    "get_all_clients",
    "get_client_policies",
    "get_policy_details",
    "get_renewals_by_urgency",
    "get_carriers_for_policy_type",
    "compare_carrier_rates",
    "get_coverage_gaps",
    "get_claims_history",
    "get_loss_ratio_trend",
}


async def test_all_10_tools_registered(mcp_session):
    async with mcp_session() as client:
        listed = await client.list_tools()
    names = {t.name for t in listed.tools}
    assert names == EXPECTED_TOOLS, (
        f"Missing: {EXPECTED_TOOLS - names}; unexpected: {names - EXPECTED_TOOLS}"
    )


async def test_every_tool_has_description_and_input_schema(mcp_session):
    async with mcp_session() as client:
        listed = await client.list_tools()
    for tool in listed.tools:
        assert tool.description and tool.description.strip(), f"{tool.name} missing description"
        schema = tool.inputSchema
        assert isinstance(schema, dict), f"{tool.name} inputSchema not a dict"
        assert schema.get("type") == "object", f"{tool.name} schema.type != 'object'"
        assert "properties" in schema, f"{tool.name} schema missing 'properties'"


@pytest.mark.parametrize(
    "tool_name,required_args",
    [
        ("get_client_info", {"client_id"}),
        ("get_client_policies", {"client_id"}),
        ("get_policy_details", {"policy_id"}),
        ("get_carriers_for_policy_type", {"policy_type"}),
        ("get_coverage_gaps", {"client_id"}),
        ("get_claims_history", {"client_id"}),
        ("get_loss_ratio_trend", {"client_id"}),
    ],
)
async def test_tool_required_args(mcp_session, tool_name, required_args):
    async with mcp_session() as client:
        listed = await client.list_tools()
    tool = next((t for t in listed.tools if t.name == tool_name), None)
    assert tool is not None, f"{tool_name} not registered"
    props = set(tool.inputSchema.get("properties", {}).keys())
    assert required_args.issubset(props), (
        f"{tool_name} missing args {required_args - props}; has {props}"
    )
