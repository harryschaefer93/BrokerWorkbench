"""
Database setup / initial data loader for the Broker Workbench demo.

CLI:
    python -m data.seed.setup              # load if empty; skip otherwise
    python -m data.seed.setup --reseed     # truncate target tables and reload
    python -m data.seed.setup --verify     # print row counts and exit

Targets the existing async SQLAlchemy session in backend.db.connection and
uses the bulk_create helpers added in Commit 1. Deterministic (random.seed=42)
except for GPT-generated claim descriptions which are cached on disk.
"""
from __future__ import annotations

# ── Bootstrap ────────────────────────────────────────────────────────────────
import asyncio
import argparse
import logging
import math
import os
import random
import sys
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Tuple

# Make backend importable when invoked from project root
_REPO_ROOT = Path(__file__).resolve().parents[2]
_BACKEND = _REPO_ROOT / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# When using local SQLite for DATABASE_URL, keep MASTER on the same writable
# location (the broker_db volume in docker, or data/db/ locally) so both halves
# of the schema live together for seeding. Set only if the user hasn't pinned it.
_db_url = os.getenv("DATABASE_URL", "")
if not _db_url.startswith("mssql") and not os.getenv("MASTER_DATABASE_URL"):
    if _db_url.startswith("sqlite"):
        os.environ["MASTER_DATABASE_URL"] = _db_url

from sqlalchemy import select, func, text  # noqa: E402

from db.connection import (  # noqa: E402
    AsyncSessionLocal,
    MasterAsyncSessionLocal,
    IS_AZURE_SQL,
    check_db_connection,
)
from db.models import (  # noqa: E402
    Base, MASTER_SCHEMA, TXN_SCHEMA,
    Carrier, Client, Policy, Claim, MarketRate,
)
from db.repository import (  # noqa: E402
    CarrierRepository, ClientRepository, PolicyRepository,
    ClaimRepository, MarketRateRepository,
)

from data.seed.taxonomy import (  # noqa: E402
    INDUSTRIES,
    PRODUCT_TYPES,
    INDUSTRY_CLAIM_FREQUENCY,
    INDUSTRY_CLAIM_SEVERITY,
    INDUSTRY_RECOMMENDED_PRODUCTS,
    PRODUCT_BASE_RATE_PER_M,
    PRODUCT_CLAIM_TYPES,
)
from data.seed.descriptions import get_claim_descriptions, cache_path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("seed")

RNG_SEED = 42

# ── Static demo vocabulary ───────────────────────────────────────────────────

CARRIERS: List[Dict[str, Any]] = [
    {"carrier_name": "The Hartford", "carrier_code": "HART", "api_status": "active",    "rating": "A+",  "specialty_lines": "commercial_property,general_liability,workers_comp", "market_share": Decimal("8.5")},
    {"carrier_name": "Travelers",    "carrier_code": "TRAV", "api_status": "active",    "rating": "A++", "specialty_lines": "commercial_property,commercial_auto,umbrella",        "market_share": Decimal("10.2")},
    {"carrier_name": "Chubb",        "carrier_code": "CHUB", "api_status": "active",    "rating": "A++", "specialty_lines": "professional_liability,cyber_liability,umbrella",     "market_share": Decimal("7.8")},
    {"carrier_name": "Liberty Mutual","carrier_code": "LIBM","api_status": "active",    "rating": "A",   "specialty_lines": "workers_comp,commercial_auto,general_liability",     "market_share": Decimal("9.1")},
    {"carrier_name": "AIG",          "carrier_code": "AIG",  "api_status": "active",    "rating": "A",   "specialty_lines": "cyber_liability,professional_liability,umbrella",     "market_share": Decimal("6.4")},
    {"carrier_name": "Zurich",       "carrier_code": "ZUR",  "api_status": "connected", "rating": "A+",  "specialty_lines": "commercial_property,commercial_auto,workers_comp",    "market_share": Decimal("5.6")},
    {"carrier_name": "CNA",          "carrier_code": "CNA",  "api_status": "slow",      "rating": "A-",  "specialty_lines": "general_liability,professional_liability",            "market_share": Decimal("4.3")},
]

# Realistic client names per industry (~7 each = 49, padded to 50 below)
CLIENT_NAMES: Dict[str, List[str]] = {
    "Technology":            ["Nimbus Cloud Systems", "OakTree Analytics", "Quanta Robotics", "Helix Software Labs", "Beacon AI", "Latitude Devices", "Northwind Code Co"],
    "Healthcare":            ["Memorial Medical Group", "Bright Pediatrics", "Cascade Surgery Center", "Riverbend Family Practice", "Summit Behavioral Health", "Lakeside Dental Partners", "Cornerstone Imaging"],
    "Manufacturing":         ["Ironforge Components", "Pacific Precision Tools", "Atlas Machining", "Granite State Plastics", "Redwood Industrial", "Birchwood Castings", "Continental Fabrication"],
    "Construction":          ["Cedar Ridge Builders", "Skyline Concrete", "Mountain View Contractors", "Foundation First LLC", "Anchor Bay Construction", "Stonebridge Roofing", "Heritage Carpentry"],
    "Transportation":        ["Pioneer Freight", "Crossroads Logistics", "Blue Heron Trucking", "Cascade Couriers", "Liberty Lines Transport", "Compass Cargo", "Sunset Hauling"],
    "Retail":                ["Maplewood Mercantile", "Cobblestone Outfitters", "Harborfront Goods", "Sage & Stone Gifts", "Riverstone Apparel", "Birchwood Boutique", "Greenway Grocers"],
    "Professional Services": ["Sterling Accounting Partners", "Wynfield Legal Group", "Brookside Consulting", "Harbor Point Architects", "Linden Strategy LLC", "Talbot Tax Advisors", "Verity Engineering"],
}

US_STATES = [
    ("New York", "NY"), ("California", "CA"), ("Texas", "TX"), ("Florida", "FL"),
    ("Illinois", "IL"), ("Pennsylvania", "PA"), ("Ohio", "OH"), ("Georgia", "GA"),
    ("North Carolina", "NC"), ("Michigan", "MI"), ("Washington", "WA"), ("Massachusetts", "MA"),
    ("Colorado", "CO"), ("Oregon", "OR"), ("Arizona", "AZ"),
]

CITIES_BY_STATE = {
    "NY": "New York", "CA": "Los Angeles", "TX": "Houston", "FL": "Miami",
    "IL": "Chicago", "PA": "Philadelphia", "OH": "Columbus", "GA": "Atlanta",
    "NC": "Charlotte", "MI": "Detroit", "WA": "Seattle", "MA": "Boston",
    "CO": "Denver", "OR": "Portland", "AZ": "Phoenix",
}

CONTACT_FIRSTS = ["Alex", "Jordan", "Taylor", "Morgan", "Riley", "Casey", "Avery", "Cameron", "Quinn", "Rowan"]
CONTACT_LASTS = ["Chen", "Patel", "Nguyen", "Garcia", "O'Brien", "Walker", "Bennett", "Hayes", "Singh", "Russo"]

# ── Helpers ──────────────────────────────────────────────────────────────────


def _severity_bucket(amount: float) -> str:
    if amount < 10_000:
        return "low"
    if amount <= 50_000:
        return "medium"
    return "high"


def _poisson(lam: float) -> int:
    """Knuth's algorithm — fine for small lambda used here (no numpy dep)."""
    if lam <= 0:
        return 0
    L = math.exp(-lam)
    k = 0
    p = 1.0
    while True:
        k += 1
        p *= random.random()
        if p <= L:
            return k - 1


def _build_carriers() -> List[Dict[str, Any]]:
    return [dict(c) for c in CARRIERS]


def _generate_clients() -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for industry in INDUSTRIES:
        for name in CLIENT_NAMES[industry]:
            state_name, state_code = random.choice(US_STATES)
            contact = f"{random.choice(CONTACT_FIRSTS)} {random.choice(CONTACT_LASTS)}"
            slug = name.lower().replace("&", "and").replace("'", "").replace(" ", "")[:18]
            rows.append({
                "client_name": name,
                "client_type": "business",
                "business_industry": industry,
                "primary_contact_name": contact,
                "email": f"{slug}@example.com",
                "phone": f"({random.randint(200, 999)}) {random.randint(200, 999)}-{random.randint(1000, 9999)}",
                "address_line1": f"{random.randint(100, 9999)} {random.choice(['Main', 'Oak', 'Maple', 'Park', 'Lake', 'River'])} {random.choice(['St', 'Ave', 'Blvd', 'Rd'])}",
                "city": CITIES_BY_STATE[state_code],
                "state": state_name,
                "zip_code": f"{random.randint(10000, 99999)}",
                "risk_score": random.randint(35, 85),
                "customer_since": date.today() - timedelta(days=random.randint(365, 365 * 8)),
                "total_premium_ytd": Decimal("0"),
            })
    # Pad to exactly 50
    while len(rows) < 50:
        rows.append(dict(rows[len(rows) % 7]))
    return rows[:50]


def _renewal_window_for_index(i: int, total: int) -> Tuple[int, int]:
    """Return (min_days, max_days) until expiration based on stratified buckets."""
    # 30% critical (0-30), 30% upcoming (31-60), 30% planned (61-90), 10% later (91-365)
    pct = (i + 1) / total
    if pct <= 0.30:
        return (0, 30)
    if pct <= 0.60:
        return (31, 60)
    if pct <= 0.90:
        return (61, 90)
    return (91, 270)


def _generate_policies(
    clients: List[Client],
    carriers: List[Carrier],
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    # Order policies so each gets a deterministic renewal bucket
    plan: List[Tuple[Client, str]] = []  # (client, product)
    for client in clients:
        prods = INDUSTRY_RECOMMENDED_PRODUCTS[client.business_industry]
        n_policies = random.randint(2, 6)
        for _ in range(n_policies):
            plan.append((client, random.choice(prods)))
    random.shuffle(plan)

    total = len(plan)
    today = date.today()
    seq = 0
    year_now = today.year
    for i, (client, product) in enumerate(plan):
        seq += 1
        min_d, max_d = _renewal_window_for_index(i, total)
        days_until_exp = random.randint(min_d, max_d)
        expiration = today + timedelta(days=days_until_exp)
        effective = expiration - timedelta(days=365)

        # Carrier preference: prefer carriers whose specialty_lines mention the product
        matching = [c for c in carriers if c.specialty_lines and product in c.specialty_lines]
        carrier = random.choice(matching) if matching else random.choice(carriers)

        coverage_limit = Decimal(random.choice([500_000, 1_000_000, 2_000_000, 3_000_000, 5_000_000, 10_000_000]))
        base_rate = PRODUCT_BASE_RATE_PER_M[product]
        jitter = random.uniform(0.85, 1.15)
        premium = (coverage_limit / Decimal(1_000_000)) * Decimal(base_rate) * Decimal(str(round(jitter, 4)))
        premium = premium.quantize(Decimal("0.01"))

        status = "active"
        if days_until_exp <= 30:
            status = random.choices(["active", "renewal_due"], weights=[40, 60])[0]
        if i < int(total * 0.03):  # ~3% expired
            status = "expired"
            expiration = today - timedelta(days=random.randint(5, 60))
            effective = expiration - timedelta(days=365)

        commission_rate = Decimal(str(round(random.uniform(8.0, 15.0), 2)))
        commission_amount = (premium * commission_rate / Decimal(100)).quantize(Decimal("0.01"))

        rows.append({
            "policy_number": f"POL-{year_now}-{seq:05d}",
            "client_id": client.client_id,
            "carrier_id": carrier.carrier_id,
            "product_category": product,
            "policy_status": status,
            "premium_amount": premium,
            "deductible": Decimal(random.choice([1_000, 2_500, 5_000, 10_000])),
            "coverage_limit": coverage_limit,
            "effective_date": effective,
            "expiration_date": expiration,
            "renewal_date": expiration,
            "auto_renew": random.random() < 0.7,
            "commission_rate": commission_rate,
            "commission_amount": commission_amount,
            "last_review_date": today - timedelta(days=random.randint(30, 180)),
            "notes": None,
        })
    return rows


def _generate_claims(
    policies: List[Policy],
    clients_by_id: Dict[int, Client],
    descriptions: Dict[Tuple[str, str, str], str],
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    today = date.today()
    seq = 0
    for policy in policies:
        client = clients_by_id.get(policy.client_id)
        if not client:
            continue
        industry = client.business_industry or "Professional Services"
        lam = INDUSTRY_CLAIM_FREQUENCY.get(industry, 0.15) * 8.0
        n_claims = _poisson(lam)
        avg_severity = INDUSTRY_CLAIM_SEVERITY.get(industry, 20_000)
        product = policy.product_category
        claim_types = PRODUCT_CLAIM_TYPES.get(product, ["general"])

        for _ in range(n_claims):
            seq += 1
            claim_type = random.choice(claim_types)
            sev = random.gauss(avg_severity, avg_severity * 0.4)
            sev = max(500.0, min(500_000.0, sev))
            amount = Decimal(str(round(sev, 2)))
            bucket = _severity_bucket(sev)
            loss_date = today - timedelta(days=random.randint(1, 365 * 3))
            reported = loss_date + timedelta(days=random.randint(1, 7))
            if reported > today:
                reported = today
            status = random.choices(
                ["settled", "investigating", "reported"],
                weights=[60, 25, 15],
            )[0]
            settlement = amount if status == "settled" else None
            impact = "major" if sev > 100_000 else ("minor" if sev > 25_000 else "none")
            desc = descriptions.get((industry, claim_type, bucket)) or f"{industry} {claim_type} incident, {bucket} severity"

            rows.append({
                "policy_id": policy.policy_id,
                "claim_number": f"CLM-{loss_date.year}-{seq:05d}",
                "claim_type": claim_type,
                "claim_amount": amount,
                "claim_status": status,
                "date_of_loss": loss_date,
                "reported_date": reported,
                "description": desc,
                "adjuster_name": f"{random.choice(CONTACT_FIRSTS)} {random.choice(CONTACT_LASTS)}",
                "settlement_amount": settlement,
                "impact_on_renewal": impact,
            })
    return rows


def _generate_market_rates(carriers: List[Carrier]) -> List[Dict[str, Any]]:
    today = date.today()
    rows: List[Dict[str, Any]] = []
    for carrier in carriers:
        for product in PRODUCT_TYPES:
            base = PRODUCT_BASE_RATE_PER_M[product] * random.uniform(0.9, 1.1)
            rows.append({
                "carrier_id": carrier.carrier_id,
                "product_category": product,
                "risk_profile": "medium",
                "base_rate": Decimal(str(round(base, 2))),
                "rate_factor": Decimal("1.000"),
                "effective_date": today - timedelta(days=30),
                "expiration_date": today + timedelta(days=335),
                "market_region": "US",
            })
    return rows


# ── Truncate / verify / orchestrate ──────────────────────────────────────────


async def _truncate() -> None:
    """Delete rows from target tables in FK-safe order. Resets autoincrement for SQLite."""
    # FK-safe order: claims → policies → market_rates → carriers; clients independent.
    # In SQLite FKs are off by default so order is robustness, not correctness.
    txn_targets = ["claims", "policies"]
    master_targets = ["market_rates", "clients", "carriers"]

    async def _reset_seq(db, names):
        # sqlite_sequence only exists if any AUTOINCREMENT table has been written.
        # Models use plain INTEGER PK (no AUTOINCREMENT) so it may not exist.
        if IS_AZURE_SQL:
            return
        exists = (await db.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name='sqlite_sequence'")
        )).first()
        if exists:
            await db.execute(
                text(f"DELETE FROM sqlite_sequence WHERE name IN ({','.join(repr(t) for t in names)})")
            )

    async with AsyncSessionLocal() as db:
        for tbl in txn_targets:
            qualified = f"{TXN_SCHEMA}.{tbl}" if IS_AZURE_SQL else tbl
            await db.execute(text(f"DELETE FROM {qualified}"))
        await _reset_seq(db, txn_targets)
        await db.commit()

    async with MasterAsyncSessionLocal() as db:
        for tbl in master_targets:
            qualified = f"{MASTER_SCHEMA}.{tbl}" if IS_AZURE_SQL else tbl
            await db.execute(text(f"DELETE FROM {qualified}"))
        await _reset_seq(db, master_targets)
        await db.commit()
    logger.info("Truncated: claims, policies, market_rates, clients, carriers.")


async def _count_table(session_factory, model) -> int:
    async with session_factory() as db:
        result = await db.execute(select(func.count()).select_from(model))
        return int(result.scalar() or 0)


async def _ensure_schema() -> None:
    """Create any missing tables (idempotent). Helps first-run seeding on an empty volume."""
    from db.connection import engine, master_engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    if master_engine is not engine:
        async with master_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)


async def _verify_counts() -> Dict[str, int]:
    return {
        "carriers": await _count_table(MasterAsyncSessionLocal, Carrier),
        "clients": await _count_table(MasterAsyncSessionLocal, Client),
        "market_rates": await _count_table(MasterAsyncSessionLocal, MarketRate),
        "policies": await _count_table(AsyncSessionLocal, Policy),
        "claims": await _count_table(AsyncSessionLocal, Claim),
    }


async def _seed() -> Dict[str, int]:
    random.seed(RNG_SEED)

    # 1. Carriers
    carrier_rows = _build_carriers()
    async with MasterAsyncSessionLocal() as db:
        await CarrierRepository.bulk_create(db, carrier_rows)
        carriers = await CarrierRepository.get_all(db)
    logger.info("Inserted %d carriers.", len(carriers))

    # 2. Clients
    client_rows = _generate_clients()
    async with MasterAsyncSessionLocal() as db:
        await ClientRepository.bulk_create(db, client_rows)
        clients = await ClientRepository.get_all(db, limit=500)
    logger.info("Inserted %d clients.", len(clients))

    # 3. Policies
    policy_rows = _generate_policies(clients, carriers)
    async with AsyncSessionLocal() as db:
        await PolicyRepository.bulk_create(db, policy_rows)
        policies = list((await db.execute(select(Policy))).scalars().all())
    logger.info("Inserted %d policies.", len(policies))

    # 4. Backfill total_premium_ytd per client
    premiums_by_client: Dict[int, Decimal] = {}
    for p in policies:
        if p.premium_amount is not None:
            premiums_by_client[p.client_id] = (
                premiums_by_client.get(p.client_id, Decimal(0)) + p.premium_amount
            )
    async with MasterAsyncSessionLocal() as db:
        all_clients = (await db.execute(select(Client))).scalars().all()
        for c in all_clients:
            c.total_premium_ytd = premiums_by_client.get(c.client_id, Decimal(0))
        await db.commit()
    logger.info("Backfilled total_premium_ytd for %d clients.", len(all_clients))

    # 5. Claims (fetch descriptions in one batched call first)
    clients_by_id = {c.client_id: c for c in clients}
    claim_specs: List[Tuple[str, str, str]] = []
    for policy in policies:
        client = clients_by_id.get(policy.client_id)
        if not client:
            continue
        industry = client.business_industry or "Professional Services"
        for ct in PRODUCT_CLAIM_TYPES.get(policy.product_category, ["general"]):
            for bucket in ("low", "medium", "high"):
                claim_specs.append((industry, ct, bucket))
    descriptions = await get_claim_descriptions(claim_specs)
    sample_desc = next(iter(descriptions.values()), "<none>") if descriptions else "<none>"

    claim_rows = _generate_claims(policies, clients_by_id, descriptions)
    async with AsyncSessionLocal() as db:
        await ClaimRepository.bulk_create(db, claim_rows)
    logger.info("Inserted %d claims.", len(claim_rows))

    # 6. Market rates
    rate_rows = _generate_market_rates(carriers)
    async with MasterAsyncSessionLocal() as db:
        await MarketRateRepository.bulk_create(db, rate_rows)
    logger.info("Inserted %d market_rates.", len(rate_rows))

    counts = await _verify_counts()
    counts["_sample_description"] = sample_desc  # type: ignore[assignment]
    return counts


async def _run(args: argparse.Namespace) -> int:
    health = await check_db_connection()
    if not (health.get("transactional") and health.get("master")):
        logger.error("Database connection failed: %s", health)
        return 2

    await _ensure_schema()

    if args.verify:
        counts = await _verify_counts()
        print("Row counts:")
        for k, v in counts.items():
            print(f"  {k:>14}: {v}")
        return 0

    existing = await _count_table(MasterAsyncSessionLocal, Client)
    if existing >= 10 and not args.reseed:
        logger.info("Broker database already initialized (clients=%d). Pass --reseed to wipe and reload.", existing)
        counts = await _verify_counts()
        print(f"Existing counts: {counts}")
        return 0

    if args.reseed:
        await _truncate()

    counts = await _seed()
    sample = counts.pop("_sample_description", "<none>")
    print("Initialized broker database:")
    print(f"  counts: {counts}")
    print(f"  description_cache: {cache_path()}")
    print(f"  sample_description: {sample}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Database setup loader for the Broker Workbench demo.")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--reseed", action="store_true", help="Wipe target tables and reload initial data.")
    group.add_argument("--verify", action="store_true", help="Print row counts and exit.")
    args = parser.parse_args()
    rc = asyncio.run(_run(args))
    sys.exit(rc)


if __name__ == "__main__":
    main()
