"""
Policy Router - CRUD operations for insurance policies
"""
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query

from models.schemas import (
    Policy, PolicyCreate, PolicyUpdate, 
    PolicyStatus, PolicyType, RenewalInfo
)
from data.mock_data import POLICIES, CLIENTS, CARRIERS, generate_id
from services.renewal_tracker import get_renewal_for_policy

router = APIRouter(prefix="/api/policies", tags=["Policies"])


@router.get("/", response_model=List[Policy])
async def list_policies(
    client_id: Optional[str] = Query(None, description="Filter by client ID"),
    carrier_id: Optional[str] = Query(None, description="Filter by carrier ID"),
    status: Optional[PolicyStatus] = Query(None, description="Filter by status"),
    policy_type: Optional[PolicyType] = Query(None, description="Filter by policy type")
):
    """
    List all policies with optional filters.
    """
    policies = []
    
    for policy_id, policy_data in POLICIES.items():
        # Apply filters
        if client_id and policy_data["client_id"] != client_id:
            continue
        if carrier_id and policy_data["carrier_id"] != carrier_id:
            continue
        if status and policy_data["status"] != status:
            continue
        if policy_type and policy_data["policy_type"] != policy_type:
            continue
        
        policies.append(Policy(**policy_data))
    
    return policies


@router.get("/{policy_id}", response_model=Policy)
async def get_policy(policy_id: str):
    """
    Get a specific policy by ID.
    """
    policy_data = POLICIES.get(policy_id)
    if not policy_data:
        raise HTTPException(status_code=404, detail=f"Policy {policy_id} not found")
    
    return Policy(**policy_data)


@router.get("/{policy_id}/renewal", response_model=RenewalInfo)
async def get_policy_renewal_info(policy_id: str):
    """
    Get renewal information for a specific policy including urgency and priority score.
    """
    if policy_id not in POLICIES:
        raise HTTPException(status_code=404, detail=f"Policy {policy_id} not found")
    
    renewal_info = get_renewal_for_policy(policy_id)
    if not renewal_info:
        raise HTTPException(status_code=404, detail=f"Could not calculate renewal info for {policy_id}")
    
    return renewal_info


@router.post("/", response_model=Policy, status_code=201)
async def create_policy(policy: PolicyCreate):
    """
    Create a new policy.
    """
    # Validate client exists
    if policy.client_id not in CLIENTS:
        raise HTTPException(status_code=400, detail=f"Client {policy.client_id} not found")
    
    # Validate carrier exists
    if policy.carrier_id not in CARRIERS:
        raise HTTPException(status_code=400, detail=f"Carrier {policy.carrier_id} not found")
    
    # Validate carrier supports this policy type
    carrier = CARRIERS[policy.carrier_id]
    if policy.policy_type not in carrier["supported_lines"]:
        raise HTTPException(
            status_code=400, 
            detail=f"Carrier {carrier['name']} does not support {policy.policy_type.value}"
        )
    
    # Generate new ID
    policy_id = generate_id("POL")
    now = datetime.utcnow()
    
    # Create policy record
    policy_data = {
        "policy_id": policy_id,
        **policy.model_dump(),
        "created_at": now,
        "updated_at": now
    }
    
    POLICIES[policy_id] = policy_data
    
    return Policy(**policy_data)


@router.put("/{policy_id}", response_model=Policy)
async def update_policy(policy_id: str, policy_update: PolicyUpdate):
    """
    Update an existing policy.
    """
    if policy_id not in POLICIES:
        raise HTTPException(status_code=404, detail=f"Policy {policy_id} not found")
    
    existing = POLICIES[policy_id]
    update_data = policy_update.model_dump(exclude_unset=True)
    
    # Validate carrier if being updated
    if "carrier_id" in update_data:
        if update_data["carrier_id"] not in CARRIERS:
            raise HTTPException(status_code=400, detail=f"Carrier {update_data['carrier_id']} not found")
    
    # Update fields
    for field, value in update_data.items():
        existing[field] = value
    
    existing["updated_at"] = datetime.utcnow()
    
    return Policy(**existing)


@router.delete("/{policy_id}", status_code=204)
async def delete_policy(policy_id: str):
    """
    Delete a policy.
    """
    if policy_id not in POLICIES:
        raise HTTPException(status_code=404, detail=f"Policy {policy_id} not found")
    
    del POLICIES[policy_id]
    return None


@router.get("/client/{client_id}/summary")
async def get_client_policy_summary(client_id: str):
    """
    Get a summary of all policies for a specific client.
    """
    if client_id not in CLIENTS:
        raise HTTPException(status_code=404, detail=f"Client {client_id} not found")
    
    client_policies = [p for p in POLICIES.values() if p["client_id"] == client_id]
    
    if not client_policies:
        return {
            "client_id": client_id,
            "client_name": CLIENTS[client_id]["name"],
            "total_policies": 0,
            "total_premium": 0,
            "total_coverage": 0,
            "policies_by_type": {},
            "carriers": []
        }
    
    total_premium = sum(p["premium"] for p in client_policies)
    total_coverage = sum(p["coverage_limit"] for p in client_policies)
    
    policies_by_type = {}
    carriers_used = set()
    
    for p in client_policies:
        ptype = p["policy_type"].value if hasattr(p["policy_type"], 'value') else p["policy_type"]
        policies_by_type[ptype] = policies_by_type.get(ptype, 0) + 1
        carriers_used.add(p["carrier_id"])
    
    carrier_names = [CARRIERS[cid]["name"] for cid in carriers_used if cid in CARRIERS]
    
    return {
        "client_id": client_id,
        "client_name": CLIENTS[client_id]["name"],
        "total_policies": len(client_policies),
        "total_premium": total_premium,
        "total_coverage": total_coverage,
        "policies_by_type": policies_by_type,
        "carriers": carrier_names
    }
