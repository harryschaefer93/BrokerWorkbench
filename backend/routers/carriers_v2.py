"""
Carrier Router v2 - Using SQLite/SQLAlchemy database
Replaces mock data with real database queries.
"""
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from db.connection import get_master_db
from db.repository import CarrierRepository
from db import models as db_models

router = APIRouter(prefix="/api/v2/carriers", tags=["Carriers v2"])


# ============ Response Models (Pydantic) ============
from pydantic import BaseModel
from datetime import datetime
from decimal import Decimal


class CarrierResponse(BaseModel):
    """Carrier response model matching SQLite schema."""
    carrier_id: int
    carrier_name: str
    carrier_code: str
    api_endpoint: Optional[str] = None
    api_status: str = "active"
    rating: Optional[str] = None
    specialty_lines: Optional[str] = None
    market_share: Optional[float] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ============ Endpoints ============

@router.get("/", response_model=List[CarrierResponse])
async def list_carriers(
    db: AsyncSession = Depends(get_master_db),
    specialty: Optional[str] = Query(None, description="Filter by specialty line (e.g., 'Auto', 'Commercial')"),
    active_only: bool = Query(False, description="Only return carriers with active/connected API")
):
    """
    List all carriers with optional filters.
    Data sourced from master_data.db.
    """
    if active_only:
        carriers = await CarrierRepository.get_active_carriers(db)
    elif specialty:
        carriers = await CarrierRepository.get_by_specialty(db, specialty)
    else:
        carriers = await CarrierRepository.get_all(db)
    
    return [CarrierResponse.model_validate(c) for c in carriers]


@router.get("/{carrier_id}", response_model=CarrierResponse)
async def get_carrier(
    carrier_id: int,
    db: AsyncSession = Depends(get_master_db)
):
    """
    Get a specific carrier by ID.
    """
    carrier = await CarrierRepository.get_by_id(db, carrier_id)
    if not carrier:
        raise HTTPException(status_code=404, detail=f"Carrier {carrier_id} not found")
    
    return CarrierResponse.model_validate(carrier)


@router.get("/code/{carrier_code}", response_model=CarrierResponse)
async def get_carrier_by_code(
    carrier_code: str,
    db: AsyncSession = Depends(get_master_db)
):
    """
    Get a specific carrier by code (e.g., 'SF' for State Farm).
    """
    carrier = await CarrierRepository.get_by_code(db, carrier_code.upper())
    if not carrier:
        raise HTTPException(status_code=404, detail=f"Carrier with code '{carrier_code}' not found")
    
    return CarrierResponse.model_validate(carrier)


@router.get("/specialty/{specialty}", response_model=List[CarrierResponse])
async def get_carriers_by_specialty(
    specialty: str,
    db: AsyncSession = Depends(get_master_db)
):
    """
    Get all carriers that support a specific product line/specialty.
    Examples: 'Auto', 'Commercial', 'Home', 'Life'
    """
    carriers = await CarrierRepository.get_by_specialty(db, specialty)
    return [CarrierResponse.model_validate(c) for c in carriers]
