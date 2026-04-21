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
    Returns renewals grouped by urgency for the main workbench UI.
    """
    summary = get_upcoming_renewals(days_ahead=90)

    def _serialize(r: "RenewalInfo") -> dict:
        return {
            "policy_id": r.policy_id,
            "client_name": r.client_name,
            "policy_type": r.policy_type.value if hasattr(r.policy_type, "value") else r.policy_type,
            "carrier_name": r.carrier_name,
            "premium": r.premium,
            "expiration_date": r.expiration_date.isoformat(),
            "days_until_expiry": r.days_until_renewal,
            "urgency": r.urgency.value if hasattr(r.urgency, "value") else r.urgency,
            "priority_score": r.priority_score,
        }

    grouped: dict[str, list] = {"critical": [], "high": [], "medium": [], "low": []}
    for renewal in summary.renewals:
        key = renewal.urgency.value if hasattr(renewal.urgency, "value") else renewal.urgency
        grouped.setdefault(key, []).append(_serialize(renewal))

    return {
        "critical": grouped["critical"],
        "high": grouped["high"],
        "medium": grouped["medium"],
        "low": grouped["low"],
        "total_premium_at_risk": summary.total_premium_at_risk,
        "total_policies": summary.total_renewals,
    }
