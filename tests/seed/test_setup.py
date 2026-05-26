"""Seed setup tests: idempotence, --verify truth, taxonomy stability."""

from __future__ import annotations

import asyncio
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


async def _row_counts() -> dict[str, int]:
    """Read live row counts straight from the DB (same code path as --verify)."""
    from sqlalchemy import func, select

    from db.connection import AsyncSessionLocal, MasterAsyncSessionLocal
    from db.models import Carrier, Claim, Client, MarketRate, Policy

    async def _n(factory, model) -> int:
        async with factory() as db:
            return int((await db.execute(select(func.count()).select_from(model))).scalar() or 0)

    return {
        "carriers": await _n(MasterAsyncSessionLocal, Carrier),
        "clients": await _n(MasterAsyncSessionLocal, Client),
        "market_rates": await _n(MasterAsyncSessionLocal, MarketRate),
        "policies": await _n(AsyncSessionLocal, Policy),
        "claims": await _n(AsyncSessionLocal, Claim),
    }


def test_reseed_is_idempotent(seeded_db):
    """Running --reseed twice produces identical row counts on every table."""
    before = asyncio.run(_row_counts())
    subprocess.run(
        [sys.executable, "-m", "data.seed.setup", "--reseed"],
        cwd=str(REPO_ROOT),
        check=True,
        capture_output=True,
    )
    after = asyncio.run(_row_counts())
    assert before == after, f"Counts drifted on reseed: before={before} after={after}"


def test_verify_reflects_truth(seeded_db):
    """--verify output row counts must match a direct DB query."""
    counts = asyncio.run(_row_counts())
    # Seeded baseline: 7 carriers, 50 clients, 7 carriers * 7 products = 49 market_rates.
    assert counts["carriers"] == 7
    assert counts["clients"] == 50
    assert counts["market_rates"] == 49
    assert counts["policies"] >= 100, f"Expected >=100 policies, got {counts['policies']}"
    # Claims are Poisson-sampled and may be zero in rare cases; require at least 1.
    assert counts["claims"] >= 1


def test_taxonomy_constants_are_stable():
    from data.seed.taxonomy import (
        INDUSTRIES,
        INDUSTRY_CLAIM_FREQUENCY,
        INDUSTRY_CLAIM_SEVERITY,
        INDUSTRY_RECOMMENDED_PRODUCTS,
        PRODUCT_BASE_RATE_PER_M,
        PRODUCT_CLAIM_TYPES,
        PRODUCT_TYPES,
    )

    assert len(INDUSTRIES) == 7
    assert len(PRODUCT_TYPES) == 7
    assert set(INDUSTRY_CLAIM_FREQUENCY) == set(INDUSTRIES)
    assert set(INDUSTRY_CLAIM_SEVERITY) == set(INDUSTRIES)
    assert set(INDUSTRY_RECOMMENDED_PRODUCTS) == set(INDUSTRIES)
    assert set(PRODUCT_BASE_RATE_PER_M) == set(PRODUCT_TYPES)
    assert set(PRODUCT_CLAIM_TYPES) == set(PRODUCT_TYPES)
