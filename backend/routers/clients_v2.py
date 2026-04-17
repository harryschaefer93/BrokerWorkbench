"""
Client Router v2 - Using SQLite/SQLAlchemy database
Replaces mock data with real database queries.
"""
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from decimal import Decimal

from db.connection import get_master_db
from db.repository import ClientRepository

router = APIRouter(prefix="/api/v2/clients", tags=["Clients v2"])


# ============ Response Models (Pydantic) ============
from pydantic import BaseModel
from datetime import datetime, date


class ClientResponse(BaseModel):
    """Client response model matching SQLite schema."""
    client_id: int
    client_name: str
    client_type: str  # 'individual' or 'business'
    business_industry: Optional[str] = None
    primary_contact_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    address_line1: Optional[str] = None
    address_line2: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    risk_score: int = 50
    customer_since: Optional[date] = None
    total_premium_ytd: float = 0
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ClientSummary(BaseModel):
    """Lightweight client summary for lists."""
    client_id: int
    client_name: str
    client_type: str
    email: Optional[str] = None
    risk_score: int
    total_premium_ytd: float

    class Config:
        from_attributes = True


# ============ Endpoints ============

@router.get("/", response_model=List[ClientSummary])
async def list_clients(
    db: AsyncSession = Depends(get_master_db),
    client_type: Optional[str] = Query(None, description="Filter by type: 'individual' or 'business'"),
    limit: int = Query(100, ge=1, le=500, description="Maximum results to return")
):
    """
    List all clients with optional filters.
    Data sourced from master_data.db.
    """
    if client_type:
        clients = await ClientRepository.get_by_type(db, client_type)
    else:
        clients = await ClientRepository.get_all(db, limit=limit)
    
    return [ClientSummary.model_validate(c) for c in clients]


@router.get("/search", response_model=List[ClientSummary])
async def search_clients(
    q: str = Query(..., min_length=2, description="Search query (name, email, or contact)"),
    client_type: Optional[str] = Query(None, description="Filter by type"),
    db: AsyncSession = Depends(get_master_db)
):
    """
    Search clients by name, email, or contact name.
    """
    clients = await ClientRepository.search(db, query=q, client_type=client_type)
    return [ClientSummary.model_validate(c) for c in clients]


@router.get("/high-value", response_model=List[ClientResponse])
async def get_high_value_clients(
    min_premium: float = Query(5000, description="Minimum YTD premium threshold"),
    db: AsyncSession = Depends(get_master_db)
):
    """
    Get high-value clients based on YTD premium.
    Useful for prioritizing renewals and cross-sell opportunities.
    """
    clients = await ClientRepository.get_high_value(db, min_premium=Decimal(str(min_premium)))
    return [ClientResponse.model_validate(c) for c in clients]


@router.get("/{client_id}", response_model=ClientResponse)
async def get_client(
    client_id: int,
    db: AsyncSession = Depends(get_master_db)
):
    """
    Get a specific client by ID with full details.
    """
    client = await ClientRepository.get_by_id(db, client_id)
    if not client:
        raise HTTPException(status_code=404, detail=f"Client {client_id} not found")
    
    return ClientResponse.model_validate(client)
