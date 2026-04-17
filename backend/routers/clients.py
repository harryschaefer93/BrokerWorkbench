"""
Client Router - CRUD operations for insurance clients
"""
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query

from models.schemas import Client, ClientCreate, ClientUpdate
from data.mock_data import CLIENTS, POLICIES, generate_id

router = APIRouter(prefix="/api/clients", tags=["Clients"])


@router.get("/", response_model=List[Client])
async def list_clients(
    industry: Optional[str] = Query(None, description="Filter by industry"),
    min_revenue: Optional[float] = Query(None, description="Minimum annual revenue"),
    max_revenue: Optional[float] = Query(None, description="Maximum annual revenue")
):
    """
    List all clients with optional filters.
    """
    clients = []
    
    for client_id, client_data in CLIENTS.items():
        # Apply filters
        if industry and client_data.get("industry", "").lower() != industry.lower():
            continue
        
        revenue = client_data.get("annual_revenue", 0)
        if min_revenue and revenue < min_revenue:
            continue
        if max_revenue and revenue > max_revenue:
            continue
        
        clients.append(Client(**client_data))
    
    return clients


@router.get("/{client_id}", response_model=Client)
async def get_client(client_id: str):
    """
    Get a specific client by ID.
    """
    client_data = CLIENTS.get(client_id)
    if not client_data:
        raise HTTPException(status_code=404, detail=f"Client {client_id} not found")
    
    return Client(**client_data)


@router.post("/", response_model=Client, status_code=201)
async def create_client(client: ClientCreate):
    """
    Create a new client.
    """
    # Generate new ID
    client_id = generate_id("CLI")
    now = datetime.utcnow()
    
    # Create client record
    client_data = {
        "client_id": client_id,
        **client.model_dump(),
        "created_at": now,
        "updated_at": now
    }
    
    CLIENTS[client_id] = client_data
    
    return Client(**client_data)


@router.put("/{client_id}", response_model=Client)
async def update_client(client_id: str, client_update: ClientUpdate):
    """
    Update an existing client.
    """
    if client_id not in CLIENTS:
        raise HTTPException(status_code=404, detail=f"Client {client_id} not found")
    
    existing = CLIENTS[client_id]
    update_data = client_update.model_dump(exclude_unset=True)
    
    # Update fields
    for field, value in update_data.items():
        existing[field] = value
    
    existing["updated_at"] = datetime.utcnow()
    
    return Client(**existing)


@router.delete("/{client_id}", status_code=204)
async def delete_client(client_id: str):
    """
    Delete a client. Will fail if client has active policies.
    """
    if client_id not in CLIENTS:
        raise HTTPException(status_code=404, detail=f"Client {client_id} not found")
    
    # Check for active policies
    active_policies = [
        p for p in POLICIES.values() 
        if p["client_id"] == client_id and p["status"] == "active"
    ]
    
    if active_policies:
        raise HTTPException(
            status_code=400, 
            detail=f"Cannot delete client with {len(active_policies)} active policies"
        )
    
    del CLIENTS[client_id]
    return None


@router.get("/{client_id}/policies")
async def get_client_policies(client_id: str):
    """
    Get all policies for a specific client.
    """
    if client_id not in CLIENTS:
        raise HTTPException(status_code=404, detail=f"Client {client_id} not found")
    
    client_policies = [
        p for p in POLICIES.values() 
        if p["client_id"] == client_id
    ]
    
    return {
        "client_id": client_id,
        "client_name": CLIENTS[client_id]["name"],
        "policy_count": len(client_policies),
        "policies": client_policies
    }


@router.get("/search/")
async def search_clients(
    q: str = Query(..., min_length=2, description="Search query (name, contact, or email)")
):
    """
    Search clients by name, contact name, or email.
    """
    query = q.lower()
    results = []
    
    for client_id, client_data in CLIENTS.items():
        name_match = query in client_data.get("name", "").lower()
        contact_match = query in client_data.get("contact_name", "").lower()
        email_match = query in client_data.get("contact_email", "").lower()
        
        if name_match or contact_match or email_match:
            results.append(Client(**client_data))
    
    return results
