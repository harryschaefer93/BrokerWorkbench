"""
Renewals Router v2 - Using SQLite/SQLAlchemy database
Enhanced renewal tracking with real database queries.
"""
from typing import List, Optional, Dict, Any
from datetime import date, timedelta
from fastapi import APIRouter, HTTPException, Query, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_

from db.connection import get_db, get_master_db
from db.models import Policy, Client, Carrier
from db.repository import PolicyRepository

router = APIRouter(prefix="/api/v2/renewals", tags=["Renewals v2"])


# ============ Response Models ============
from pydantic import BaseModel
from enum import Enum


class RenewalUrgency(str, Enum):
    CRITICAL = "critical"   # Within 30 days
    HIGH = "high"           # 31-60 days
    MEDIUM = "medium"       # 61-90 days
    LOW = "low"             # 90+ days


class RenewalItem(BaseModel):
    """Individual renewal item with enriched data."""
    policy_id: int
    policy_number: str
    client_id: int
    client_name: Optional[str] = None
    carrier_id: int
    carrier_name: Optional[str] = None
    product_category: str
    premium_amount: Optional[float] = None
    expiration_date: date
    days_until_expiration: int
    urgency: RenewalUrgency
    priority_score: float
    auto_renew: bool
    last_review_date: Optional[date] = None


class RenewalSummary(BaseModel):
    """Summary of upcoming renewals."""
    total_renewals: int
    critical_count: int
    high_count: int
    medium_count: int
    low_count: int
    total_premium_at_risk: float
    renewals: List[RenewalItem]


class RenewalDashboard(BaseModel):
    """Dashboard view of renewals."""
    summary: Dict[str, Any]
    by_timeframe: Dict[str, int]
    top_priority: List[RenewalItem]


# ============ Helper Functions ============

def calculate_urgency(days_until: int) -> RenewalUrgency:
    """Determine urgency based on days until expiration."""
    if days_until <= 30:
        return RenewalUrgency.CRITICAL
    elif days_until <= 60:
        return RenewalUrgency.HIGH
    elif days_until <= 90:
        return RenewalUrgency.MEDIUM
    else:
        return RenewalUrgency.LOW


def calculate_priority_score(
    days_until: int,
    premium: float,
    risk_score: int = 50
) -> float:
    """
    Calculate priority score (0-100) based on multiple factors:
    - Time urgency (40%): Closer = higher
    - Premium size (40%): Larger = higher
    - Risk score (20%): Higher risk = higher priority
    """
    # Time urgency: 0-40 points (max at 0 days, 0 at 90+ days)
    time_score = max(0, 40 - (days_until * 40 / 90))
    
    # Premium: 0-40 points (assuming max premium ~50k for scaling)
    premium_score = min(40, (premium or 0) / 50000 * 40)
    
    # Risk: 0-20 points
    risk_score_normalized = (risk_score or 50) / 100 * 20
    
    return round(time_score + premium_score + risk_score_normalized, 1)


# ============ Endpoints ============

async def _get_renewals(
    db: AsyncSession,
    master_db: AsyncSession,
    days_ahead: int = 90,
    urgency_filter: Optional[RenewalUrgency] = None,
    client_id_filter: Optional[int] = None
) -> RenewalSummary:
    """Internal function to get renewals - shared by multiple endpoints."""
    today = date.today()
    cutoff = today + timedelta(days=days_ahead)
    
    # Build query conditions
    conditions = [
        Policy.expiration_date >= today,
        Policy.expiration_date <= cutoff,
        Policy.policy_status.in_(["active", "renewal_due"])
    ]
    
    if client_id_filter is not None:
        conditions.append(Policy.client_id == client_id_filter)
    
    # Get policies
    result = await db.execute(
        select(Policy).where(and_(*conditions)).order_by(Policy.expiration_date)
    )
    policies = result.scalars().all()
    
    # Get client and carrier data for enrichment
    client_ids = list(set(p.client_id for p in policies))
    carrier_ids = list(set(p.carrier_id for p in policies))
    
    # Fetch clients (handle empty list)
    clients = {}
    if client_ids:
        client_result = await master_db.execute(
            select(Client).where(Client.client_id.in_(client_ids))
        )
        clients = {c.client_id: c for c in client_result.scalars().all()}
    
    # Fetch carriers (handle empty list)
    carriers = {}
    if carrier_ids:
        carrier_result = await master_db.execute(
            select(Carrier).where(Carrier.carrier_id.in_(carrier_ids))
        )
        carriers = {c.carrier_id: c for c in carrier_result.scalars().all()}
    
    # Build renewal items
    renewals = []
    counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    total_premium = 0
    
    for policy in policies:
        days_until = (policy.expiration_date - today).days
        policy_urgency = calculate_urgency(days_until)
        
        # Apply urgency filter if specified
        if urgency_filter and policy_urgency != urgency_filter:
            continue
        
        client = clients.get(policy.client_id)
        carrier = carriers.get(policy.carrier_id)
        
        priority = calculate_priority_score(
            days_until,
            float(policy.premium_amount or 0),
            client.risk_score if client else 50
        )
        
        renewal = RenewalItem(
            policy_id=policy.policy_id,
            policy_number=policy.policy_number,
            client_id=policy.client_id,
            client_name=client.client_name if client else None,
            carrier_id=policy.carrier_id,
            carrier_name=carrier.carrier_name if carrier else None,
            product_category=policy.product_category,
            premium_amount=float(policy.premium_amount) if policy.premium_amount else None,
            expiration_date=policy.expiration_date,
            days_until_expiration=days_until,
            urgency=policy_urgency,
            priority_score=priority,
            auto_renew=policy.auto_renew,
            last_review_date=policy.last_review_date
        )
        
        renewals.append(renewal)
        counts[policy_urgency.value] += 1
        total_premium += float(policy.premium_amount or 0)
    
    # Sort by priority score (highest first)
    renewals.sort(key=lambda r: r.priority_score, reverse=True)
    
    return RenewalSummary(
        total_renewals=len(renewals),
        critical_count=counts["critical"],
        high_count=counts["high"],
        medium_count=counts["medium"],
        low_count=counts["low"],
        total_premium_at_risk=round(total_premium, 2),
        renewals=renewals
    )


@router.get("/", response_model=RenewalSummary)
async def list_upcoming_renewals(
    days_ahead: int = Query(90, ge=1, le=365, description="Look ahead window in days"),
    urgency: Optional[RenewalUrgency] = Query(None, description="Filter by urgency level"),
    client_id: Optional[int] = Query(None, description="Filter by client ID"),
    db: AsyncSession = Depends(get_db),
    master_db: AsyncSession = Depends(get_master_db)
):
    """
    Get all policies with upcoming renewals within the specified timeframe.
    Returns renewals sorted by priority score (highest first).
    """
    return await _get_renewals(
        db=db,
        master_db=master_db,
        days_ahead=days_ahead,
        urgency_filter=urgency,
        client_id_filter=client_id
    )


@router.get("/critical", response_model=RenewalSummary)
async def get_critical_renewals(
    db: AsyncSession = Depends(get_db),
    master_db: AsyncSession = Depends(get_master_db)
):
    """
    Get all CRITICAL renewals (expiring within 30 days).
    These require immediate action.
    """
    return await _get_renewals(
        db=db,
        master_db=master_db,
        days_ahead=30,
        urgency_filter=RenewalUrgency.CRITICAL
    )


@router.get("/dashboard", response_model=RenewalDashboard)
async def get_renewal_dashboard(
    db: AsyncSession = Depends(get_db),
    master_db: AsyncSession = Depends(get_master_db)
):
    """
    Get a dashboard summary of all upcoming renewals for the next 90 days.
    Optimized for the main workbench UI.
    """
    summary = await _get_renewals(
        db=db,
        master_db=master_db,
        days_ahead=90
    )
    
    # Group by timeframe
    by_timeframe = {
        "this_week": 0,
        "next_week": 0,
        "week_3": 0,
        "week_4": 0,
        "month_2": 0,
        "month_3": 0
    }
    
    for renewal in summary.renewals:
        days = renewal.days_until_expiration
        if days <= 7:
            by_timeframe["this_week"] += 1
        elif days <= 14:
            by_timeframe["next_week"] += 1
        elif days <= 21:
            by_timeframe["week_3"] += 1
        elif days <= 30:
            by_timeframe["week_4"] += 1
        elif days <= 60:
            by_timeframe["month_2"] += 1
        else:
            by_timeframe["month_3"] += 1
    
    return RenewalDashboard(
        summary={
            "total_renewals": summary.total_renewals,
            "critical_count": summary.critical_count,
            "high_count": summary.high_count,
            "medium_count": summary.medium_count,
            "low_count": summary.low_count,
            "total_premium_at_risk": summary.total_premium_at_risk
        },
        by_timeframe=by_timeframe,
        top_priority=summary.renewals[:5]
    )
