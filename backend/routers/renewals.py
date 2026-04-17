"""
Renewals Router - Renewal tracking and prioritization endpoints
"""
from typing import Optional
from fastapi import APIRouter, Query

from models.schemas import RenewalSummary, RenewalUrgency
from services.renewal_tracker import get_upcoming_renewals

router = APIRouter(prefix="/api/renewals", tags=["Renewals"])


@router.get("/", response_model=RenewalSummary)
async def list_upcoming_renewals(
    days_ahead: int = Query(90, ge=1, le=365, description="Look ahead window in days"),
    urgency: Optional[RenewalUrgency] = Query(None, description="Filter by urgency level"),
    client_id: Optional[str] = Query(None, description="Filter by client ID")
):
    """
    Get all policies with upcoming renewals within the specified timeframe.
    
    Returns renewals sorted by priority score (highest first).
    
    Priority scoring factors:
    - Time urgency (40%): Closer expiration = higher priority
    - Premium size (30%): Larger premium = higher priority  
    - Client value (20%): Higher revenue clients = higher priority
    - Policy complexity (10%): Complex policy types = higher priority
    """
    return get_upcoming_renewals(
        days_ahead=days_ahead,
        urgency_filter=urgency,
        client_id=client_id
    )


@router.get("/critical", response_model=RenewalSummary)
async def get_critical_renewals():
    """
    Get all CRITICAL renewals (expiring within 30 days).
    These require immediate action.
    """
    return get_upcoming_renewals(days_ahead=30, urgency_filter=RenewalUrgency.CRITICAL)


@router.get("/dashboard")
async def get_renewal_dashboard():
    """
    Get a dashboard summary of all upcoming renewals for the next 90 days.
    Useful for the main workbench UI.
    """
    summary = get_upcoming_renewals(days_ahead=90)
    
    # Group renewals by week
    renewals_by_week = {
        "week_1": [],  # Days 1-7
        "week_2": [],  # Days 8-14
        "week_3": [],  # Days 15-21
        "week_4": [],  # Days 22-30
        "month_2": [], # Days 31-60
        "month_3": []  # Days 61-90
    }
    
    for renewal in summary.renewals:
        days = renewal.days_until_renewal
        if days <= 7:
            renewals_by_week["week_1"].append(renewal)
        elif days <= 14:
            renewals_by_week["week_2"].append(renewal)
        elif days <= 21:
            renewals_by_week["week_3"].append(renewal)
        elif days <= 30:
            renewals_by_week["week_4"].append(renewal)
        elif days <= 60:
            renewals_by_week["month_2"].append(renewal)
        else:
            renewals_by_week["month_3"].append(renewal)
    
    return {
        "summary": {
            "total_renewals": summary.total_renewals,
            "critical_count": summary.critical_count,
            "high_count": summary.high_count,
            "medium_count": summary.medium_count,
            "low_count": summary.low_count,
            "total_premium_at_risk": summary.total_premium_at_risk
        },
        "by_timeframe": {
            "this_week": len(renewals_by_week["week_1"]),
            "next_week": len(renewals_by_week["week_2"]),
            "week_3": len(renewals_by_week["week_3"]),
            "week_4": len(renewals_by_week["week_4"]),
            "month_2": len(renewals_by_week["month_2"]),
            "month_3": len(renewals_by_week["month_3"])
        },
        "top_priority": summary.renewals[:5] if summary.renewals else [],
        "renewals_by_week": renewals_by_week
    }
