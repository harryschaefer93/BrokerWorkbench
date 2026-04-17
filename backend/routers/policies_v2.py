"""
Policy Router v2 - Using SQLite/SQLAlchemy database
Replaces mock data with real database queries.
"""
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, HTTPException, Query, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from decimal import Decimal

from db.connection import get_db
from db.repository import PolicyRepository, ClaimRepository

router = APIRouter(prefix="/api/v2/policies", tags=["Policies v2"])


# ============ Response Models (Pydantic) ============
from pydantic import BaseModel
from datetime import datetime, date


class PolicyResponse(BaseModel):
    """Policy response model matching SQLite schema."""
    policy_id: int
    policy_number: str
    client_id: int
    carrier_id: int
    product_category: str
    policy_status: str = "active"
    premium_amount: Optional[float] = None
    deductible: Optional[float] = None
    coverage_limit: Optional[float] = None
    effective_date: Optional[date] = None
    expiration_date: Optional[date] = None
    renewal_date: Optional[date] = None
    auto_renew: bool = True
    commission_rate: Optional[float] = None
    commission_amount: Optional[float] = None
    last_review_date: Optional[date] = None
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class PolicySummary(BaseModel):
    """Lightweight policy summary for lists."""
    policy_id: int
    policy_number: str
    client_id: int
    carrier_id: int
    product_category: str
    policy_status: str
    premium_amount: Optional[float] = None
    expiration_date: Optional[date] = None

    class Config:
        from_attributes = True


class RenewalDashboard(BaseModel):
    """Renewal dashboard summary."""
    critical_count: int
    upcoming_count: int
    planned_count: int
    total_premium_at_risk: float


# ============ Endpoints ============

@router.get("/", response_model=List[PolicySummary])
async def list_policies(
    db: AsyncSession = Depends(get_db),
    status: Optional[str] = Query(None, description="Filter by status: active, renewal_due, expired, cancelled"),
    client_id: Optional[int] = Query(None, description="Filter by client ID"),
    carrier_id: Optional[int] = Query(None, description="Filter by carrier ID"),
    limit: int = Query(100, ge=1, le=500, description="Maximum results to return")
):
    """
    List all policies with optional filters.
    Data sourced from transactional_data.db.
    """
    policies = await PolicyRepository.get_all(
        db, 
        status=status, 
        client_id=client_id, 
        carrier_id=carrier_id,
        limit=limit
    )
    return [PolicySummary.model_validate(p) for p in policies]


@router.get("/expiring", response_model=List[PolicyResponse])
async def get_expiring_policies(
    days: int = Query(30, ge=1, le=365, description="Days ahead to check"),
    status: Optional[str] = Query(None, description="Filter by policy status"),
    db: AsyncSession = Depends(get_db)
):
    """
    Get policies expiring within the specified number of days.
    Critical for renewal management.
    """
    policies = await PolicyRepository.get_expiring_soon(db, days=days, status=status)
    return [PolicyResponse.model_validate(p) for p in policies]


@router.get("/renewals/summary", response_model=RenewalDashboard)
async def get_renewal_summary(
    db: AsyncSession = Depends(get_db)
):
    """
    Get a summary of policies by renewal urgency.
    - Critical: Expiring in 30 days
    - Upcoming: 31-60 days
    - Planned: 61-90 days
    """
    summary = await PolicyRepository.get_renewal_summary(db)
    return RenewalDashboard(**summary)


@router.get("/{policy_id}", response_model=PolicyResponse)
async def get_policy(
    policy_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Get a specific policy by ID with full details.
    """
    policy = await PolicyRepository.get_by_id(db, policy_id)
    if not policy:
        raise HTTPException(status_code=404, detail=f"Policy {policy_id} not found")
    
    return PolicyResponse.model_validate(policy)


@router.get("/number/{policy_number}", response_model=PolicyResponse)
async def get_policy_by_number(
    policy_number: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Get a specific policy by policy number (e.g., 'POL12344').
    """
    policy = await PolicyRepository.get_by_number(db, policy_number)
    if not policy:
        raise HTTPException(status_code=404, detail=f"Policy '{policy_number}' not found")
    
    return PolicyResponse.model_validate(policy)


@router.get("/client/{client_id}", response_model=List[PolicyResponse])
async def get_client_policies(
    client_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Get all policies for a specific client.
    """
    policies = await PolicyRepository.get_by_client(db, client_id)
    return [PolicyResponse.model_validate(p) for p in policies]


@router.get("/{policy_id}/claims")
async def get_policy_claims(
    policy_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Get all claims associated with a policy.
    Useful for assessing renewal impact.
    """
    # First verify policy exists
    policy = await PolicyRepository.get_by_id(db, policy_id)
    if not policy:
        raise HTTPException(status_code=404, detail=f"Policy {policy_id} not found")
    
    claims = await ClaimRepository.get_by_policy(db, policy_id)
    return {
        "policy_id": policy_id,
        "policy_number": policy.policy_number,
        "claims_count": len(claims),
        "claims": claims
    }


@router.patch("/{policy_id}/status")
async def update_policy_status(
    policy_id: int,
    status: str = Query(..., description="New status: active, renewal_due, expired, cancelled"),
    db: AsyncSession = Depends(get_db)
):
    """
    Update a policy's status.
    """
    valid_statuses = ["active", "renewal_due", "expired", "cancelled"]
    if status not in valid_statuses:
        raise HTTPException(
            status_code=400, 
            detail=f"Invalid status. Must be one of: {valid_statuses}"
        )
    
    policy = await PolicyRepository.update_status(db, policy_id, status)
    if not policy:
        raise HTTPException(status_code=404, detail=f"Policy {policy_id} not found")
    
    return PolicyResponse.model_validate(policy)
