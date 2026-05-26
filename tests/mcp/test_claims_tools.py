"""Claims-tool tests: get_claims_history, get_loss_ratio_trend.

Includes a direct-SQL cross-check that proves get_claims_history reads
real DB rows (not fabricated values).
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from tests.conftest import tool_result


def _find_client_with_claims():
    """Synchronous helper: returns a client_id (int) with claims. Spawns a
    fresh asyncio loop — do NOT call from inside an async test."""
    import asyncio

    return asyncio.run(_find_client_with_claims_async())


async def _find_client_with_claims_async() -> int | None:
    from db.connection import AsyncSessionLocal
    from db.models import Claim, Policy

    async with AsyncSessionLocal() as db:
        rows = (
            await db.execute(
                select(Policy.client_id).join(Claim, Claim.policy_id == Policy.policy_id)
            )
        ).all()
    if not rows:
        return None
    from collections import Counter
    counts = Counter(r[0] for r in rows)
    for cid, n in counts.most_common():
        if n >= 2:
            return cid
    return rows[0][0]


@pytest.mark.parametrize("client_id", ["CLI001", "CLI005", "CLI015"])
async def test_get_claims_history_happy_path(mcp_session, client_id):
    async with mcp_session() as client:
        res = await client.call_tool("get_claims_history", {"client_id": client_id})
    data = tool_result(res)
    assert data["client_id"] == client_id
    assert data["source"] == "broker_db"
    assert data["analysis_period"] == "3 years"
    assert "claims_history" in data
    assert "summary" in data
    assert "renewal_impact" in data


async def test_get_claims_history_unknown_client(mcp_session):
    async with mcp_session() as client:
        res = await client.call_tool("get_claims_history", {"client_id": "CLI9999"})
    data = tool_result(res)
    assert "error" in data


async def test_claims_history_cross_check_against_sql(mcp_session):
    """The tool's claim_details sum must equal a direct SQL sum of claim_amount."""
    cid_int = await _find_client_with_claims_async()
    if cid_int is None:
        pytest.skip("Seeded DB has no claims to cross-check.")
    client_id = f"CLI{cid_int:03d}"

    async with mcp_session() as client:
        res = await client.call_tool("get_claims_history", {"client_id": client_id})
    data = tool_result(res)
    tool_sum = sum(c["claim_amount"] or 0 for c in data["claim_details"])
    tool_count = len(data["claim_details"])

    from db.connection import AsyncSessionLocal
    from db.models import Claim, Policy
    from sqlalchemy import func

    async with AsyncSessionLocal() as db:
        sql_count, sql_sum = (
            await db.execute(
                select(
                    func.count(Claim.claim_id),
                    func.coalesce(func.sum(Claim.claim_amount), 0),
                )
                .join(Policy, Policy.policy_id == Claim.policy_id)
                .where(Policy.client_id == cid_int)
            )
        ).one()

    assert tool_count == sql_count, f"count mismatch: tool={tool_count} sql={sql_count}"
    assert abs(float(tool_sum) - float(sql_sum)) < 0.01, (
        f"sum mismatch: tool={tool_sum} sql={sql_sum}"
    )


@pytest.mark.parametrize("client_id", ["CLI001", "CLI008"])
async def test_get_loss_ratio_trend_happy_path(mcp_session, client_id):
    async with mcp_session() as client:
        res = await client.call_tool("get_loss_ratio_trend", {"client_id": client_id})
    data = tool_result(res)
    assert data["client_id"] == client_id
    assert data["source"] == "broker_db"
    assert data["trend_direction"] in {
        "improving", "worsening", "stable", "insufficient_data",
    }
    assert isinstance(data["yearly_data"], list)


async def test_get_loss_ratio_trend_unknown_client(mcp_session):
    async with mcp_session() as client:
        res = await client.call_tool("get_loss_ratio_trend", {"client_id": "CLI9999"})
    data = tool_result(res)
    assert "error" in data
