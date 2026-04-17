"""
Renewal Tracking Service for Insurance Broker Workbench

Provides logic for:
- Identifying policies approaching renewal
- Calculating priority scores for task ranking
- Categorizing renewals by urgency
"""
from datetime import date, timedelta
from typing import List, Dict, Optional

from models.schemas import (
    RenewalInfo, RenewalSummary, RenewalUrgency, PolicyType
)
from data.mock_data import POLICIES, CLIENTS, CARRIERS


def calculate_urgency(days_until_renewal: int) -> RenewalUrgency:
    """
    Determine urgency level based on days until policy expiration.
    
    - CRITICAL: 0-30 days (immediate action required)
    - HIGH: 31-60 days (start renewal process)
    - MEDIUM: 61-90 days (begin planning)
    - LOW: 90+ days (monitor)
    """
    if days_until_renewal <= 30:
        return RenewalUrgency.CRITICAL
    elif days_until_renewal <= 60:
        return RenewalUrgency.HIGH
    elif days_until_renewal <= 90:
        return RenewalUrgency.MEDIUM
    else:
        return RenewalUrgency.LOW


def calculate_priority_score(
    days_until_renewal: int,
    premium: float,
    policy_type: PolicyType,
    client_revenue: Optional[float] = None
) -> float:
    """
    Calculate a 0-100 priority score for task ranking.
    
    Factors considered:
    - Time urgency (40% weight) - closer = higher priority
    - Premium size (30% weight) - larger = higher priority
    - Client value (20% weight) - higher revenue = higher priority
    - Policy complexity (10% weight) - some types need more attention
    
    Returns a score from 0-100 where higher = more urgent
    """
    # Time urgency score (0-40 points)
    # Exponential decay: score decreases as days increase
    if days_until_renewal <= 0:
        time_score = 40  # Already expired - max urgency
    elif days_until_renewal <= 30:
        time_score = 40 - (days_until_renewal * 0.5)  # 40 -> 25
    elif days_until_renewal <= 60:
        time_score = 25 - ((days_until_renewal - 30) * 0.5)  # 25 -> 10
    elif days_until_renewal <= 90:
        time_score = 10 - ((days_until_renewal - 60) * 0.2)  # 10 -> 4
    else:
        time_score = max(0, 4 - ((days_until_renewal - 90) * 0.02))
    
    # Premium size score (0-30 points)
    # Logarithmic scale to handle wide range of premiums
    if premium <= 10000:
        premium_score = 5
    elif premium <= 50000:
        premium_score = 10
    elif premium <= 100000:
        premium_score = 20
    else:
        premium_score = 30
    
    # Client value score (0-20 points)
    if client_revenue:
        if client_revenue >= 25000000:
            client_score = 20
        elif client_revenue >= 10000000:
            client_score = 15
        elif client_revenue >= 5000000:
            client_score = 10
        else:
            client_score = 5
    else:
        client_score = 10  # Default if unknown
    
    # Policy complexity score (0-10 points)
    complex_types = [
        PolicyType.WORKERS_COMP,
        PolicyType.PROFESSIONAL_LIABILITY,
        PolicyType.CYBER_LIABILITY
    ]
    if policy_type in complex_types:
        complexity_score = 10
    else:
        complexity_score = 5
    
    total_score = time_score + premium_score + client_score + complexity_score
    return min(100, max(0, round(total_score, 1)))


def get_upcoming_renewals(
    days_ahead: int = 90,
    urgency_filter: Optional[RenewalUrgency] = None,
    client_id: Optional[str] = None
) -> RenewalSummary:
    """
    Get all policies with renewals within the specified timeframe.
    
    Args:
        days_ahead: Look ahead window (default 90 days)
        urgency_filter: Optional filter by urgency level
        client_id: Optional filter by specific client
    
    Returns:
        RenewalSummary with all matching renewals sorted by priority
    """
    today = date.today()
    cutoff_date = today + timedelta(days=days_ahead)
    
    renewals: List[RenewalInfo] = []
    
    for policy_id, policy in POLICIES.items():
        # Skip if not active
        if policy.get("status") != "active":
            continue
            
        exp_date = policy["expiration_date"]
        
        # Skip if expiration is beyond our window or already passed
        if exp_date > cutoff_date or exp_date < today:
            continue
        
        # Apply client filter if specified
        if client_id and policy["client_id"] != client_id:
            continue
        
        # Calculate days until renewal
        days_until = (exp_date - today).days
        
        # Get urgency
        urgency = calculate_urgency(days_until)
        
        # Apply urgency filter if specified
        if urgency_filter and urgency != urgency_filter:
            continue
        
        # Get client and carrier info
        client = CLIENTS.get(policy["client_id"], {})
        carrier = CARRIERS.get(policy["carrier_id"], {})
        
        # Calculate priority score
        priority = calculate_priority_score(
            days_until_renewal=days_until,
            premium=policy["premium"],
            policy_type=policy["policy_type"],
            client_revenue=client.get("annual_revenue")
        )
        
        renewal_info = RenewalInfo(
            policy_id=policy_id,
            policy_number=policy["policy_number"],
            client_id=policy["client_id"],
            client_name=client.get("name", "Unknown"),
            carrier_id=policy["carrier_id"],
            carrier_name=carrier.get("name", "Unknown"),
            policy_type=policy["policy_type"],
            expiration_date=exp_date,
            days_until_renewal=days_until,
            urgency=urgency,
            premium=policy["premium"],
            priority_score=priority
        )
        renewals.append(renewal_info)
    
    # Sort by priority score descending (highest priority first)
    renewals.sort(key=lambda r: r.priority_score, reverse=True)
    
    # Calculate summary stats
    critical_count = sum(1 for r in renewals if r.urgency == RenewalUrgency.CRITICAL)
    high_count = sum(1 for r in renewals if r.urgency == RenewalUrgency.HIGH)
    medium_count = sum(1 for r in renewals if r.urgency == RenewalUrgency.MEDIUM)
    low_count = sum(1 for r in renewals if r.urgency == RenewalUrgency.LOW)
    total_premium = sum(r.premium for r in renewals)
    
    return RenewalSummary(
        total_renewals=len(renewals),
        critical_count=critical_count,
        high_count=high_count,
        medium_count=medium_count,
        low_count=low_count,
        total_premium_at_risk=total_premium,
        renewals=renewals
    )


def get_renewal_for_policy(policy_id: str) -> Optional[RenewalInfo]:
    """Get renewal information for a specific policy."""
    policy = POLICIES.get(policy_id)
    if not policy:
        return None
    
    today = date.today()
    exp_date = policy["expiration_date"]
    days_until = (exp_date - today).days
    
    client = CLIENTS.get(policy["client_id"], {})
    carrier = CARRIERS.get(policy["carrier_id"], {})
    
    urgency = calculate_urgency(days_until)
    priority = calculate_priority_score(
        days_until_renewal=days_until,
        premium=policy["premium"],
        policy_type=policy["policy_type"],
        client_revenue=client.get("annual_revenue")
    )
    
    return RenewalInfo(
        policy_id=policy_id,
        policy_number=policy["policy_number"],
        client_id=policy["client_id"],
        client_name=client.get("name", "Unknown"),
        carrier_id=policy["carrier_id"],
        carrier_name=carrier.get("name", "Unknown"),
        policy_type=policy["policy_type"],
        expiration_date=exp_date,
        days_until_renewal=days_until,
        urgency=urgency,
        premium=policy["premium"],
        priority_score=priority
    )
