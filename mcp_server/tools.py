"""
MCP tool wrappers for the Broker Workbench.

These 10 tools form the agent-facing API consumed by the Foundry Agent
Service `MCPStreamableHTTPTool`. They mirror the shapes of the original
`backend/agents/tools.py` functions so the merged system prompt (added in
Phase A sub-step 2) keeps working unchanged.

Backed by the broker SQL database (carriers, clients, policies, claims,
market_rates) via the shared SQLAlchemy session factories.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional

from mcp.server.fastmcp import FastMCP
from sqlalchemy import select

from mcp_server.db import (
    carrier_to_int,
    cli_to_int,
    get_master_session,
    get_session,
    int_to_carrier,
    int_to_cli,
    int_to_pol,
    pol_to_int,
)

# Reuse backend models + repositories (PYTHONPATH includes backend/ via db.py)
from db.models import Carrier, Client, MarketRate, Policy  # noqa: E402
from db.repository import (  # noqa: E402
    CarrierRepository,
    ClaimRepository,
    ClientRepository,
    MarketRateRepository,
    PolicyRepository,
)


# ── Canonical vocabularies (mirrors data/seed/taxonomy.py) ────────────

VALID_PRODUCT_TYPES = {
    "commercial_property", "general_liability", "workers_comp",
    "commercial_auto", "professional_liability", "cyber_liability", "umbrella",
}

INDUSTRY_FACTORS: Dict[str, float] = {
    "Technology": 0.9,
    "Healthcare": 1.3,
    "Manufacturing": 1.1,
    "Construction": 1.4,
    "Transportation": 1.2,
    "Retail": 1.0,
    "Professional Services": 0.85,
}

RATING_FACTORS: Dict[str, float] = {
    "A++": 1.05, "A+": 1.02, "A": 1.0, "A-": 0.95,
    "B++": 0.92, "B+": 0.90, "B": 0.88,
}

INDUSTRY_RECOMMENDED_PRODUCTS: Dict[str, List[str]] = {
    "Technology": ["cyber_liability", "professional_liability", "general_liability", "commercial_property"],
    "Healthcare": ["professional_liability", "general_liability", "cyber_liability", "commercial_property", "workers_comp"],
    "Manufacturing": ["commercial_property", "general_liability", "workers_comp", "commercial_auto", "umbrella"],
    "Construction": ["general_liability", "workers_comp", "commercial_auto", "umbrella", "professional_liability"],
    "Transportation": ["commercial_auto", "general_liability", "workers_comp", "umbrella", "commercial_property"],
    "Retail": ["commercial_property", "general_liability", "workers_comp", "commercial_auto"],
    "Professional Services": ["professional_liability", "cyber_liability", "general_liability", "commercial_property"],
}

# Default expected quote-turnaround (hours) when carrier record has no value
QUOTE_TIME_BY_API_STATUS: Dict[str, float] = {
    "connected": 0.5, "active": 2.0, "slow": 8.0, "offline": 24.0,
}

INDUSTRY_LOSS_RECS: Dict[str, List[str]] = {
    "Technology": [
        "Implement regular security training for employees",
        "Review cyber incident response plan",
    ],
    "Healthcare": [
        "Conduct risk management training for clinical staff",
        "Review documentation and consent procedures",
    ],
    "Manufacturing": [
        "Update machine guarding and safety equipment",
        "Implement regular safety inspections",
    ],
    "Construction": [
        "Enhance job site safety programs",
        "Implement subcontractor qualification process",
    ],
    "Transportation": [
        "Install telematics for fleet monitoring",
        "Implement driver safety training program",
    ],
    "Retail": [
        "Strengthen loss-prevention controls and CCTV coverage",
        "Refresh slip-and-fall housekeeping protocols",
    ],
    "Professional Services": [
        "Review client engagement letters and scope-of-work language",
        "Refresh staff training on documentation discipline",
    ],
}


# ── Helpers ───────────────────────────────────────────────────────────

def _f(value) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    return float(value)


def _days_until(d: Optional[date]) -> Optional[int]:
    if d is None:
        return None
    return (d - date.today()).days


def _urgency(days: Optional[int]) -> str:
    if days is None:
        return "unknown"
    if days < 0:
        return "expired"
    if days <= 30:
        return "critical"
    if days <= 60:
        return "high"
    if days <= 90:
        return "medium"
    return "low"


def _priority_score(days: Optional[int], premium: Optional[float]) -> float:
    if days is None:
        return 0.0
    if days <= 0:
        time_score = 40
    elif days <= 30:
        time_score = 40 - days * 0.5
    elif days <= 60:
        time_score = 25 - (days - 30) * 0.5
    elif days <= 90:
        time_score = 10 - (days - 60) * 0.2
    else:
        time_score = max(0.0, 4 - (days - 90) * 0.02)
    p = premium or 0
    if p <= 10_000:
        prem_score = 5
    elif p <= 50_000:
        prem_score = 10
    elif p <= 100_000:
        prem_score = 20
    else:
        prem_score = 30
    return round(time_score + prem_score, 1)


def _loss_recs(industry: Optional[str], loss_ratio: float) -> List[str]:
    out: List[str] = []
    if loss_ratio > 0.5:
        out.append("Schedule loss control consultation with carrier")
        out.append("Review and update safety protocols")
    out.extend(INDUSTRY_LOSS_RECS.get(
        industry or "",
        ["Review general safety procedures", "Consider employee safety training"],
    ))
    return out


def _carrier_to_dict(c: Carrier) -> Dict[str, Any]:
    return {
        "carrier_id": int_to_carrier(c.carrier_id),
        "name": c.carrier_name,
        "carrier_code": c.carrier_code,
        "am_best_rating": c.rating or "Unknown",
        "api_status": c.api_status,
        "api_enabled": c.api_status in ("active", "connected"),
        "average_quote_time_hours": QUOTE_TIME_BY_API_STATUS.get(c.api_status, 4.0),
        "supported_lines": [
            s.strip() for s in (c.specialty_lines or "").split(",") if s.strip()
        ],
        "market_share": _f(c.market_share),
    }


# =====================================================================
# Tool implementations (pure async fns; FastMCP decorator added below)
# =====================================================================

async def get_client_info(client_id: str) -> Dict[str, Any]:
    """Get detailed information about a specific client including contact
    details, industry, and a summary of their policies."""
    try:
        cid = cli_to_int(client_id)
    except ValueError as e:
        return {"error": str(e)}

    async with get_master_session() as mdb:
        client = await ClientRepository.get_by_id(mdb, cid)
    if client is None:
        return {"error": f"Client not found: {client_id}"}

    async with get_session() as db:
        policies = await PolicyRepository.get_by_client(db, cid)

    return {
        "client_id": int_to_cli(client.client_id),
        "name": client.client_name,
        "industry": client.business_industry,
        "client_type": client.client_type,
        "contact_name": client.primary_contact_name,
        "email": client.email,
        "phone": client.phone,
        "city": client.city,
        "state": client.state,
        "risk_score": client.risk_score,
        "customer_since": str(client.customer_since) if client.customer_since else None,
        "total_premium_ytd": _f(client.total_premium_ytd),
        "total_policies": len(policies),
        "total_premium": float(sum((p.premium_amount or 0) for p in policies)),
    }


async def get_all_clients() -> List[Dict[str, Any]]:
    """Get a list of all clients with summary information including policy
    counts and total premiums."""
    async with get_master_session() as mdb:
        clients = await ClientRepository.get_all(mdb, limit=1000)
    async with get_session() as db:
        all_policies = await PolicyRepository.get_all(db, limit=10000)

    by_client: Dict[int, List[Policy]] = {}
    for p in all_policies:
        by_client.setdefault(p.client_id, []).append(p)

    out: List[Dict[str, Any]] = []
    for c in clients:
        pols = by_client.get(c.client_id, [])
        out.append({
            "client_id": int_to_cli(c.client_id),
            "name": c.client_name,
            "industry": c.business_industry,
            "contact_name": c.primary_contact_name,
            "total_policies": len(pols),
            "total_premium": float(sum((p.premium_amount or 0) for p in pols)),
            "risk_score": c.risk_score,
        })
    return out


async def get_client_policies(client_id: str) -> List[Dict[str, Any]]:
    """Get all insurance policies for a specific client with carrier info
    and renewal urgency."""
    try:
        cid = cli_to_int(client_id)
    except ValueError as e:
        return [{"error": str(e)}]

    async with get_session() as db:
        policies = await PolicyRepository.get_by_client(db, cid)
    if not policies:
        # Confirm whether the client exists at all
        async with get_master_session() as mdb:
            if await ClientRepository.get_by_id(mdb, cid) is None:
                return [{"error": f"Client not found: {client_id}"}]
        return []

    carrier_ids = sorted({p.carrier_id for p in policies})
    async with get_master_session() as mdb:
        carriers = {
            c.carrier_id: c
            for c in (await mdb.execute(
                select(Carrier).where(Carrier.carrier_id.in_(carrier_ids))
            )).scalars().all()
        }

    out: List[Dict[str, Any]] = []
    for p in policies:
        c = carriers.get(p.carrier_id)
        days = _days_until(p.expiration_date)
        out.append({
            "policy_id": int_to_pol(p.policy_id),
            "policy_number": p.policy_number,
            "policy_type": p.product_category,
            "carrier_id": int_to_carrier(p.carrier_id),
            "carrier_name": c.carrier_name if c else "Unknown",
            "carrier_rating": (c.rating if c else None) or "Unknown",
            "premium": _f(p.premium_amount),
            "coverage_limit": _f(p.coverage_limit),
            "deductible": _f(p.deductible),
            "effective_date": str(p.effective_date) if p.effective_date else None,
            "expiration_date": str(p.expiration_date) if p.expiration_date else None,
            "days_until_renewal": days,
            "urgency": _urgency(days),
            "status": p.policy_status,
            "notes": p.notes or "",
        })
    out.sort(key=lambda x: x["days_until_renewal"] if x["days_until_renewal"] is not None else 10**6)
    return out


async def get_policy_details(policy_id: str) -> Dict[str, Any]:
    """Get complete details about a specific policy including client info,
    carrier info, and renewal analysis."""
    try:
        pid = pol_to_int(policy_id)
    except ValueError as e:
        return {"error": str(e)}

    async with get_session() as db:
        policy = await PolicyRepository.get_by_id(db, pid)
    if policy is None:
        return {"error": f"Policy not found: {policy_id}"}

    async with get_master_session() as mdb:
        client = await ClientRepository.get_by_id(mdb, policy.client_id)
        carrier = await CarrierRepository.get_by_id(mdb, policy.carrier_id)

    days = _days_until(policy.expiration_date)
    premium = _f(policy.premium_amount)

    return {
        "policy_id": int_to_pol(policy.policy_id),
        "policy_number": policy.policy_number,
        "policy_type": policy.product_category,
        "client_id": int_to_cli(policy.client_id),
        "client_name": client.client_name if client else "Unknown",
        "client_industry": (client.business_industry if client else None),
        "carrier_id": int_to_carrier(policy.carrier_id),
        "carrier_name": carrier.carrier_name if carrier else "Unknown",
        "carrier_rating": (carrier.rating if carrier else None) or "Unknown",
        "carrier_api_enabled": (carrier.api_status in ("active", "connected")) if carrier else False,
        "premium": premium,
        "coverage_limit": _f(policy.coverage_limit),
        "deductible": _f(policy.deductible),
        "effective_date": str(policy.effective_date) if policy.effective_date else None,
        "expiration_date": str(policy.expiration_date) if policy.expiration_date else None,
        "status": policy.policy_status,
        "days_until_renewal": days,
        "urgency": _urgency(days),
        "priority_score": _priority_score(days, premium),
        "notes": policy.notes or "",
    }


async def get_renewals_by_urgency(
    urgency: Optional[str] = None, days_ahead: int = 90
) -> Dict[str, Any]:
    """Get upcoming policy renewals with priority scores, optionally
    filtered by urgency level (critical, high, medium, low)."""
    try:
        days_ahead = int(days_ahead)
    except (TypeError, ValueError):
        days_ahead = 90

    urgency_norm: Optional[str] = None
    if urgency and str(urgency).lower() not in ("none", "null", ""):
        u = str(urgency).lower()
        if u not in {"critical", "high", "medium", "low"}:
            return {"error": f"Invalid urgency level: {urgency}. Use critical, high, medium, or low."}
        urgency_norm = u

    async with get_session() as db:
        policies = await PolicyRepository.get_expiring_soon(db, days=days_ahead)

    client_ids = sorted({p.client_id for p in policies})
    carrier_ids = sorted({p.carrier_id for p in policies})

    async with get_master_session() as mdb:
        clients = {
            c.client_id: c for c in (await mdb.execute(
                select(Client).where(Client.client_id.in_(client_ids))
            )).scalars().all()
        } if client_ids else {}
        carriers = {
            c.carrier_id: c for c in (await mdb.execute(
                select(Carrier).where(Carrier.carrier_id.in_(carrier_ids))
            )).scalars().all()
        } if carrier_ids else {}

    renewals: List[Dict[str, Any]] = []
    counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    premium_at_risk = 0.0

    for p in policies:
        days = _days_until(p.expiration_date)
        u = _urgency(days)
        if urgency_norm and u != urgency_norm:
            continue
        if u in counts:
            counts[u] += 1
        prem = _f(p.premium_amount) or 0.0
        premium_at_risk += prem
        client = clients.get(p.client_id)
        carrier = carriers.get(p.carrier_id)
        renewals.append({
            "policy_id": int_to_pol(p.policy_id),
            "policy_number": p.policy_number,
            "policy_type": p.product_category,
            "client_id": int_to_cli(p.client_id),
            "client_name": client.client_name if client else "Unknown",
            "carrier_name": carrier.carrier_name if carrier else "Unknown",
            "expiration_date": str(p.expiration_date) if p.expiration_date else None,
            "days_until_renewal": days,
            "premium": prem,
            "urgency": u,
            "priority_score": _priority_score(days, prem),
        })

    renewals.sort(key=lambda x: x["priority_score"], reverse=True)
    return {
        "total_renewals": len(renewals),
        "critical_count": counts["critical"],
        "high_count": counts["high"],
        "medium_count": counts["medium"],
        "low_count": counts["low"],
        "total_premium_at_risk": round(premium_at_risk, 2),
        "renewals": renewals,
    }


async def get_carriers_for_policy_type(policy_type: str) -> List[Dict[str, Any]]:
    """Get all insurance carriers that offer a specific type of policy
    coverage."""
    pt = (policy_type or "").lower().strip()
    if pt not in VALID_PRODUCT_TYPES:
        return [{
            "error": f"Invalid policy type: {policy_type}. Valid types: {sorted(VALID_PRODUCT_TYPES)}"
        }]

    async with get_master_session() as mdb:
        carriers = await CarrierRepository.get_by_specialty(mdb, pt)

    out = [_carrier_to_dict(c) for c in carriers]
    rating_order = {"A++": 0, "A+": 1, "A": 2, "A-": 3, "B++": 4, "B+": 5, "B": 6}
    out.sort(key=lambda x: rating_order.get(x["am_best_rating"], 99))
    return out


async def compare_carrier_rates(
    policy_type: str,
    coverage_limit: float,
    industry: str,
    annual_revenue: Optional[float] = None,
) -> List[Dict[str, Any]]:
    """Compare estimated insurance rates from different carriers for a
    specific policy type and coverage amount. Pulls from the market_rates
    table and applies industry / rating / digital-discount factors."""
    pt = (policy_type or "").lower().strip()
    if pt not in VALID_PRODUCT_TYPES:
        return [{
            "error": f"Invalid policy type: {policy_type}. Valid types: {sorted(VALID_PRODUCT_TYPES)}"
        }]

    industry_factor = INDUSTRY_FACTORS.get(industry, 1.0)
    try:
        units = float(coverage_limit) / 1_000_000.0
    except (TypeError, ValueError):
        return [{"error": f"Invalid coverage_limit: {coverage_limit!r}"}]

    async with get_master_session() as mdb:
        carriers = await CarrierRepository.get_by_specialty(mdb, pt)
        if not carriers:
            return []

        quotes: List[Dict[str, Any]] = []
        for c in carriers:
            rate = await MarketRateRepository.get_by_carrier_and_category(
                mdb, c.carrier_id, pt
            )
            if rate is None or rate.base_rate is None:
                continue
            base = float(rate.base_rate)
            rate_factor = float(rate.rate_factor) if rate.rate_factor is not None else 1.0
            rating_factor = RATING_FACTORS.get(c.rating or "", 1.0)
            estimated = base * max(units, 0.1) * industry_factor * rating_factor * rate_factor
            if c.api_status == "connected":
                estimated *= 0.95  # 5% digital discount for fully-integrated carriers
            quotes.append({
                "carrier_id": int_to_carrier(c.carrier_id),
                "carrier_name": c.carrier_name,
                "am_best_rating": c.rating or "Unknown",
                "api_status": c.api_status,
                "api_enabled": c.api_status in ("active", "connected"),
                "quote_time_hours": QUOTE_TIME_BY_API_STATUS.get(c.api_status, 4.0),
                "estimated_annual_premium": round(estimated, 2),
                "coverage_limit": float(coverage_limit),
                "base_rate_per_million": base,
                "quote_valid_days": 30,
                "disclaimer": "Estimated rate from market_rates table; actual quote may vary based on underwriting",
            })

    quotes.sort(key=lambda x: x["estimated_annual_premium"])
    return quotes


async def get_coverage_gaps(client_id: str) -> Dict[str, Any]:
    """Analyze a client's current coverage portfolio and identify gaps or
    cross-sell opportunities based on their industry."""
    try:
        cid = cli_to_int(client_id)
    except ValueError as e:
        return {"error": str(e)}

    async with get_master_session() as mdb:
        client = await ClientRepository.get_by_id(mdb, cid)
    if client is None:
        return {"error": f"Client not found: {client_id}"}

    async with get_session() as db:
        policies = await PolicyRepository.get_by_client(db, cid)

    current_coverage = {p.product_category for p in policies}
    industry = client.business_industry or ""
    recommended = INDUSTRY_RECOMMENDED_PRODUCTS.get(
        industry, ["general_liability", "commercial_property"]
    )

    # Count carriers per product for the gap row
    async with get_master_session() as mdb:
        carrier_counts: Dict[str, int] = {}
        for product in recommended:
            cs = await CarrierRepository.get_by_specialty(mdb, product)
            carrier_counts[product] = len(cs)

    gaps: List[Dict[str, Any]] = []
    for i, rec in enumerate(recommended):
        if rec not in current_coverage:
            gaps.append({
                "policy_type": rec,
                "priority": "high" if i < 2 else "medium",
                "reason": f"Recommended for {industry} industry",
                "available_carriers": carrier_counts.get(rec, 0),
            })

    total_premium = float(sum((p.premium_amount or 0) for p in policies))
    if len(policies) >= 2 and "umbrella" not in current_coverage and total_premium > 50_000:
        async with get_master_session() as mdb:
            umb_count = len(await CarrierRepository.get_by_specialty(mdb, "umbrella"))
        gaps.append({
            "policy_type": "umbrella",
            "priority": "high",
            "reason": f"Multiple underlying policies totaling ${total_premium:,.2f} in premium",
            "available_carriers": umb_count,
        })

    return {
        "client_id": int_to_cli(client.client_id),
        "client_name": client.client_name,
        "industry": industry,
        "current_policies": len(policies),
        "current_coverage_types": sorted(current_coverage),
        "total_current_premium": total_premium,
        "coverage_gaps": gaps,
        "limit_concerns": [],  # no annual_revenue field on client records
        "cross_sell_opportunities": len(gaps),
    }


async def get_claims_history(client_id: str) -> Dict[str, Any]:
    """Returns the client's 3-year claims history from the broker database,
    including yearly buckets, 3-year loss ratio, renewal impact assessment,
    and loss control recommendations."""
    try:
        cid = cli_to_int(client_id)
    except ValueError as e:
        return {"error": str(e)}

    async with get_master_session() as mdb:
        client = await ClientRepository.get_by_id(mdb, cid)
    if client is None:
        return {"error": f"Client not found: {client_id}"}

    async with get_session() as db:
        yearly = await ClaimRepository.get_aggregated_by_year(db, cid, years=3)
        claim_rows = await ClaimRepository.get_by_client(db, cid)

    claims_history = [
        {
            "year": y["year"],
            "claim_count": y["claim_count"],
            "total_incurred": round(y["total_incurred"], 2),
            "loss_ratio": round(y["loss_ratio"], 3),
        }
        for y in yearly
    ]
    total_claims = sum(y["claim_count"] for y in yearly)
    total_incurred = sum(y["total_incurred"] for y in yearly)
    weighted_premium = sum(
        (y["total_incurred"] / y["loss_ratio"]) if y["loss_ratio"] > 0 else 0
        for y in yearly
    )
    three_year_loss_ratio = total_incurred / weighted_premium if weighted_premium > 0 else 0.0

    if three_year_loss_ratio < 0.4:
        impact, rate_change, msg = "favorable", -2.0, \
            "Claims experience is favorable. Expect flat to modest renewal increase."
    elif three_year_loss_ratio < 0.6:
        impact, rate_change, msg = "neutral", 5.0, \
            "Claims experience is average. Expect standard market renewal increase."
    elif three_year_loss_ratio < 0.8:
        impact, rate_change, msg = "unfavorable", 15.0, \
            "Elevated claims activity. Expect above-market renewal increase."
    else:
        impact, rate_change, msg = "adverse", 25.0, \
            "Poor loss experience. Significant renewal increase likely. Consider loss control measures."

    claim_details = [
        {
            "claim_id": c.claim_id,
            "claim_number": c.claim_number,
            "policy_id": int_to_pol(c.policy_id),
            "claim_type": c.claim_type,
            "claim_status": c.claim_status,
            "claim_amount": _f(c.claim_amount),
            "date_of_loss": str(c.date_of_loss) if c.date_of_loss else None,
            "impact_on_renewal": c.impact_on_renewal,
        }
        for c in claim_rows
    ]

    return {
        "client_id": int_to_cli(client.client_id),
        "client_name": client.client_name,
        "industry": client.business_industry,
        "analysis_period": "3 years",
        "claims_history": claims_history,
        "claim_details": claim_details,
        "summary": {
            "total_claims": total_claims,
            "total_incurred": round(total_incurred, 2),
            "average_claim_size": round(total_incurred / total_claims, 2) if total_claims else 0.0,
            "three_year_loss_ratio": round(three_year_loss_ratio, 3),
        },
        "renewal_impact": {
            "assessment": impact,
            "expected_rate_change_percent": rate_change,
            "message": msg,
        },
        "recommendations": _loss_recs(client.business_industry, three_year_loss_ratio),
        "source": "broker_db",
    }


async def get_loss_ratio_trend(client_id: str) -> Dict[str, Any]:
    """Returns the year-over-year loss ratio trend for a client's policies
    from the broker database, using the same per-year aggregation as
    get_claims_history."""
    try:
        cid = cli_to_int(client_id)
    except ValueError as e:
        return {"error": str(e)}

    async with get_master_session() as mdb:
        client = await ClientRepository.get_by_id(mdb, cid)
    if client is None:
        return {"error": f"Client {client_id} not found"}

    async with get_session() as db:
        yearly = await ClaimRepository.get_aggregated_by_year(db, cid, years=3)
        policies = await PolicyRepository.get_by_client(db, cid)

    if not policies:
        return {"error": f"No policies found for {client_id}"}

    trend_data: List[Dict[str, Any]] = []
    for y in yearly:
        year = y["year"]
        year_start = date(year, 1, 1)
        year_end = date(year, 12, 31)
        premium = 0.0
        for p in policies:
            if (
                p.effective_date is not None
                and p.effective_date <= year_end
                and (p.expiration_date is None or p.expiration_date >= year_start)
            ):
                premium += float(p.premium_amount or 0)
        loss_ratio_pct = round((y["total_incurred"] / premium * 100), 1) if premium > 0 else 0.0
        trend_data.append({
            "year": year,
            "claims_count": y["claim_count"],
            "total_incurred": round(y["total_incurred"], 2),
            "total_premium": round(premium, 2),
            "loss_ratio_pct": loss_ratio_pct,
        })

    if len(trend_data) >= 2:
        first, last = trend_data[0]["loss_ratio_pct"], trend_data[-1]["loss_ratio_pct"]
        if last < first - 1:
            trend_direction = "improving"
        elif last > first + 1:
            trend_direction = "worsening"
        else:
            trend_direction = "stable"
    else:
        trend_direction = "insufficient_data"

    return {
        "client_id": int_to_cli(client.client_id),
        "client_name": client.client_name,
        "trend_direction": trend_direction,
        "yearly_data": trend_data,
        "analysis": f"Loss ratio trend for {client.client_name} over {len(trend_data)} years",
        "source": "broker_db",
    }


# =====================================================================
# FastMCP registration
# =====================================================================

_ALL_TOOLS = [
    get_client_info,
    get_all_clients,
    get_client_policies,
    get_policy_details,
    get_renewals_by_urgency,
    get_carriers_for_policy_type,
    compare_carrier_rates,
    get_coverage_gaps,
    get_claims_history,
    get_loss_ratio_trend,
]


def register_tools(mcp: FastMCP) -> None:
    """Decorate every tool function with @mcp.tool() on the given FastMCP."""
    for fn in _ALL_TOOLS:
        mcp.tool()(fn)
