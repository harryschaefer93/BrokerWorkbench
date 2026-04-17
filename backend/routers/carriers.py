"""
Carrier Router - CRUD operations for insurance carriers
"""
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query

from models.schemas import Carrier, CarrierCreate, CarrierUpdate, CarrierRating, PolicyType
from data.mock_data import CARRIERS, POLICIES, generate_id

router = APIRouter(prefix="/api/carriers", tags=["Carriers"])


@router.get("/", response_model=List[Carrier])
async def list_carriers(
    rating: Optional[CarrierRating] = Query(None, description="Filter by AM Best rating"),
    policy_type: Optional[PolicyType] = Query(None, description="Filter by supported policy type"),
    api_enabled: Optional[bool] = Query(None, description="Filter by API integration availability")
):
    """
    List all carriers with optional filters.
    """
    carriers = []
    
    for carrier_id, carrier_data in CARRIERS.items():
        # Apply filters
        if rating and carrier_data.get("am_best_rating") != rating:
            continue
        
        if policy_type and policy_type not in carrier_data.get("supported_lines", []):
            continue
        
        if api_enabled is not None and carrier_data.get("api_enabled") != api_enabled:
            continue
        
        carriers.append(Carrier(**carrier_data))
    
    return carriers


@router.get("/{carrier_id}", response_model=Carrier)
async def get_carrier(carrier_id: str):
    """
    Get a specific carrier by ID.
    """
    carrier_data = CARRIERS.get(carrier_id)
    if not carrier_data:
        raise HTTPException(status_code=404, detail=f"Carrier {carrier_id} not found")
    
    return Carrier(**carrier_data)


@router.post("/", response_model=Carrier, status_code=201)
async def create_carrier(carrier: CarrierCreate):
    """
    Create a new carrier.
    """
    # Generate new ID
    carrier_id = generate_id("CAR")
    now = datetime.utcnow()
    
    # Create carrier record
    carrier_data = {
        "carrier_id": carrier_id,
        **carrier.model_dump(),
        "created_at": now,
        "updated_at": now
    }
    
    CARRIERS[carrier_id] = carrier_data
    
    return Carrier(**carrier_data)


@router.put("/{carrier_id}", response_model=Carrier)
async def update_carrier(carrier_id: str, carrier_update: CarrierUpdate):
    """
    Update an existing carrier.
    """
    if carrier_id not in CARRIERS:
        raise HTTPException(status_code=404, detail=f"Carrier {carrier_id} not found")
    
    existing = CARRIERS[carrier_id]
    update_data = carrier_update.model_dump(exclude_unset=True)
    
    # Update fields
    for field, value in update_data.items():
        existing[field] = value
    
    existing["updated_at"] = datetime.utcnow()
    
    return Carrier(**existing)


@router.delete("/{carrier_id}", status_code=204)
async def delete_carrier(carrier_id: str):
    """
    Delete a carrier. Will fail if carrier has active policies.
    """
    if carrier_id not in CARRIERS:
        raise HTTPException(status_code=404, detail=f"Carrier {carrier_id} not found")
    
    # Check for active policies
    active_policies = [
        p for p in POLICIES.values() 
        if p["carrier_id"] == carrier_id and p["status"] == "active"
    ]
    
    if active_policies:
        raise HTTPException(
            status_code=400, 
            detail=f"Cannot delete carrier with {len(active_policies)} active policies"
        )
    
    del CARRIERS[carrier_id]
    return None


@router.get("/{carrier_id}/policies")
async def get_carrier_policies(carrier_id: str):
    """
    Get all policies written with a specific carrier.
    """
    if carrier_id not in CARRIERS:
        raise HTTPException(status_code=404, detail=f"Carrier {carrier_id} not found")
    
    carrier_policies = [
        p for p in POLICIES.values() 
        if p["carrier_id"] == carrier_id
    ]
    
    total_premium = sum(p["premium"] for p in carrier_policies)
    
    return {
        "carrier_id": carrier_id,
        "carrier_name": CARRIERS[carrier_id]["name"],
        "policy_count": len(carrier_policies),
        "total_premium": total_premium,
        "policies": carrier_policies
    }


@router.get("/for-policy-type/{policy_type}")
async def get_carriers_for_policy_type(policy_type: PolicyType):
    """
    Get all carriers that support a specific policy type, sorted by rating.
    """
    matching_carriers = []
    
    for carrier_id, carrier_data in CARRIERS.items():
        if policy_type in carrier_data.get("supported_lines", []):
            matching_carriers.append({
                "carrier_id": carrier_id,
                "name": carrier_data["name"],
                "am_best_rating": carrier_data["am_best_rating"],
                "api_enabled": carrier_data["api_enabled"],
                "average_quote_time_hours": carrier_data.get("average_quote_time_hours")
            })
    
    # Sort by rating (A++ first)
    rating_order = ["A++", "A+", "A", "A-", "B++", "B+", "B"]
    matching_carriers.sort(
        key=lambda c: rating_order.index(c["am_best_rating"].value) 
        if c["am_best_rating"].value in rating_order else 99
    )
    
    return {
        "policy_type": policy_type.value,
        "carrier_count": len(matching_carriers),
        "carriers": matching_carriers
    }
