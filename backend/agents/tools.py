"""
Agent Tools for Broker Workbench

These tools wrap the existing backend services and provide structured
function definitions that can be called by Azure AI Foundry agents.

Each tool is defined as a FunctionTool with:
- name: Unique identifier
- parameters: JSON schema for input
- description: What the tool does (used by the agent to decide when to call it)
"""
import json
from datetime import date, timedelta
from typing import Dict, List, Any, Optional

# Import existing data and services
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data.mock_data import CLIENTS, POLICIES, CARRIERS
from models.schemas import PolicyType, PolicyStatus, RenewalUrgency
from services.renewal_tracker import (
    calculate_urgency,
    calculate_priority_score,
    get_upcoming_renewals,
)


# =============================================================================
# Tool Functions - These wrap existing services for agent use
# =============================================================================

def get_client_info(client_id: str) -> Dict[str, Any]:
    """
    Get detailed information about a specific client.
    
    Args:
        client_id: The unique identifier for the client (e.g., "CLI001")
    
    Returns:
        Dictionary with client details or error message
    """
    if client_id not in CLIENTS:
        return {"error": f"Client not found: {client_id}"}
    
    client = CLIENTS[client_id].copy()
    # Convert datetime objects to strings for JSON serialization
    client["created_at"] = str(client["created_at"])
    client["updated_at"] = str(client["updated_at"])
    
    # Add summary stats
    policies = [p for p in POLICIES.values() if p["client_id"] == client_id]
    client["total_policies"] = len(policies)
    client["total_premium"] = sum(p["premium"] for p in policies)
    
    return client


def get_all_clients() -> List[Dict[str, Any]]:
    """
    Get a list of all clients with summary information.
    
    Returns:
        List of client dictionaries with basic info and policy counts
    """
    result = []
    for client_id, client in CLIENTS.items():
        policies = [p for p in POLICIES.values() if p["client_id"] == client_id]
        result.append({
            "client_id": client_id,
            "name": client["name"],
            "industry": client["industry"],
            "contact_name": client["contact_name"],
            "total_policies": len(policies),
            "total_premium": sum(p["premium"] for p in policies),
            "annual_revenue": client.get("annual_revenue"),
            "employee_count": client.get("employee_count"),
        })
    return result


def get_client_policies(client_id: str) -> List[Dict[str, Any]]:
    """
    Get all policies for a specific client.
    
    Args:
        client_id: The unique identifier for the client
    
    Returns:
        List of policy dictionaries with carrier info
    """
    if client_id not in CLIENTS:
        return [{"error": f"Client not found: {client_id}"}]
    
    policies = []
    for policy_id, policy in POLICIES.items():
        if policy["client_id"] == client_id:
            carrier = CARRIERS.get(policy["carrier_id"], {})
            
            # Calculate days until renewal
            exp_date = policy["expiration_date"]
            days_until = (exp_date - date.today()).days
            
            policies.append({
                "policy_id": policy_id,
                "policy_number": policy["policy_number"],
                "policy_type": policy["policy_type"].value if hasattr(policy["policy_type"], 'value') else policy["policy_type"],
                "carrier_name": carrier.get("name", "Unknown"),
                "carrier_rating": carrier.get("am_best_rating", "Unknown"),
                "premium": policy["premium"],
                "coverage_limit": policy["coverage_limit"],
                "deductible": policy["deductible"],
                "effective_date": str(policy["effective_date"]),
                "expiration_date": str(policy["expiration_date"]),
                "days_until_renewal": days_until,
                "urgency": calculate_urgency(days_until).value if days_until > 0 else "expired",
                "status": policy["status"].value if hasattr(policy["status"], 'value') else policy["status"],
                "notes": policy.get("notes", ""),
            })
    
    return sorted(policies, key=lambda x: x["days_until_renewal"])


def get_policy_details(policy_id: str) -> Dict[str, Any]:
    """
    Get detailed information about a specific policy including carrier info.
    
    Args:
        policy_id: The unique identifier for the policy (e.g., "POL001")
    
    Returns:
        Dictionary with complete policy details
    """
    if policy_id not in POLICIES:
        return {"error": f"Policy not found: {policy_id}"}
    
    policy = POLICIES[policy_id].copy()
    client = CLIENTS.get(policy["client_id"], {})
    carrier = CARRIERS.get(policy["carrier_id"], {})
    
    # Calculate renewal info
    exp_date = policy["expiration_date"]
    days_until = (exp_date - date.today()).days
    
    return {
        "policy_id": policy_id,
        "policy_number": policy["policy_number"],
        "policy_type": policy["policy_type"].value if hasattr(policy["policy_type"], 'value') else policy["policy_type"],
        
        # Client info
        "client_id": policy["client_id"],
        "client_name": client.get("name", "Unknown"),
        "client_industry": client.get("industry", "Unknown"),
        
        # Carrier info
        "carrier_id": policy["carrier_id"],
        "carrier_name": carrier.get("name", "Unknown"),
        "carrier_rating": carrier.get("am_best_rating", "Unknown"),
        "carrier_api_enabled": carrier.get("api_enabled", False),
        
        # Coverage details
        "premium": policy["premium"],
        "coverage_limit": policy["coverage_limit"],
        "deductible": policy["deductible"],
        "effective_date": str(policy["effective_date"]),
        "expiration_date": str(policy["expiration_date"]),
        "status": policy["status"].value if hasattr(policy["status"], 'value') else policy["status"],
        
        # Renewal info
        "days_until_renewal": days_until,
        "urgency": calculate_urgency(days_until).value if days_until > 0 else "expired",
        "priority_score": calculate_priority_score(
            days_until,
            policy["premium"],
            policy["policy_type"],
            client.get("annual_revenue")
        ),
        
        "notes": policy.get("notes", ""),
    }


def get_renewals_by_urgency(urgency: Optional[str] = None, days_ahead: int = 90) -> Dict[str, Any]:
    """
    Get upcoming policy renewals, optionally filtered by urgency level.
    
    Args:
        urgency: Filter by urgency level ("critical", "high", "medium", "low") or None for all
        days_ahead: Number of days to look ahead (default 90)
    
    Returns:
        Dictionary with renewal summary and list of policies
    """
    # Coerce days_ahead to int in case model passes a string
    try:
        days_ahead = int(days_ahead)
    except (TypeError, ValueError):
        days_ahead = 90

    urgency_filter = None
    if urgency and str(urgency).lower() not in ('none', 'null', ''):
        try:
            urgency_filter = RenewalUrgency(str(urgency).lower())
        except ValueError:
            return {"error": f"Invalid urgency level: {urgency}. Use critical, high, medium, or low."}
    
    summary = get_upcoming_renewals(days_ahead=days_ahead, urgency_filter=urgency_filter)
    
    # Convert to serializable format
    renewals = []
    for r in summary.renewals:
        renewals.append({
            "policy_id": r.policy_id,
            "policy_number": r.policy_number,
            "policy_type": r.policy_type.value if hasattr(r.policy_type, 'value') else str(r.policy_type),
            "client_id": r.client_id,
            "client_name": r.client_name,
            "carrier_name": r.carrier_name,
            "expiration_date": str(r.expiration_date),
            "days_until_renewal": r.days_until_renewal,
            "premium": r.premium,
            "urgency": r.urgency.value if hasattr(r.urgency, 'value') else str(r.urgency),
            "priority_score": r.priority_score,
        })
    
    return {
        "total_renewals": summary.total_renewals,
        "critical_count": summary.critical_count,
        "high_count": summary.high_count,
        "medium_count": summary.medium_count,
        "low_count": summary.low_count,
        "total_premium_at_risk": summary.total_premium_at_risk,
        "renewals": renewals,
    }


def get_carriers_for_policy_type(policy_type: str) -> List[Dict[str, Any]]:
    """
    Get all carriers that support a specific policy type.
    
    Args:
        policy_type: Type of policy (e.g., "commercial_property", "cyber_liability")
    
    Returns:
        List of carriers with their ratings and capabilities
    """
    try:
        policy_type_enum = PolicyType(policy_type.lower())
    except ValueError:
        valid_types = [pt.value for pt in PolicyType]
        return [{"error": f"Invalid policy type: {policy_type}. Valid types: {valid_types}"}]
    
    matching_carriers = []
    for carrier_id, carrier in CARRIERS.items():
        if policy_type_enum in carrier["supported_lines"]:
            matching_carriers.append({
                "carrier_id": carrier_id,
                "name": carrier["name"],
                "am_best_rating": carrier["am_best_rating"].value if hasattr(carrier["am_best_rating"], 'value') else carrier["am_best_rating"],
                "api_enabled": carrier["api_enabled"],
                "average_quote_time_hours": carrier.get("average_quote_time_hours"),
                "notes": carrier.get("notes", ""),
                "supported_lines": [
                    line.value if hasattr(line, 'value') else line 
                    for line in carrier["supported_lines"]
                ],
            })
    
    # Sort by rating (A++ first)
    rating_order = {"A++": 0, "A+": 1, "A": 2, "A-": 3, "B++": 4, "B+": 5, "B": 6}
    matching_carriers.sort(key=lambda x: rating_order.get(x["am_best_rating"], 99))
    
    return matching_carriers


def compare_carrier_rates(
    policy_type: str,
    coverage_limit: float,
    industry: str,
    annual_revenue: Optional[float] = None
) -> List[Dict[str, Any]]:
    """
    Compare estimated rates from different carriers for a policy type.
    
    This is a SIMULATED comparison - in production this would call carrier APIs.
    
    Args:
        policy_type: Type of policy to quote
        coverage_limit: Desired coverage limit
        industry: Client's industry (affects rating)
        annual_revenue: Optional annual revenue for premium estimation
    
    Returns:
        List of carrier quotes with estimated premiums
    """
    carriers = get_carriers_for_policy_type(policy_type)
    if not carriers or (len(carriers) == 1 and "error" in carriers[0]):
        return carriers
    
    # Industry risk factors (simulated)
    industry_factors = {
        "Technology": 0.9,
        "Healthcare": 1.3,
        "Manufacturing": 1.1,
        "Construction": 1.4,
        "Transportation": 1.2,
        "Retail": 1.0,
        "Professional Services": 0.85,
    }
    
    # Policy type base rates (simulated per $1M coverage)
    base_rates = {
        "commercial_property": 800,
        "general_liability": 1200,
        "workers_comp": 2500,
        "commercial_auto": 3500,
        "professional_liability": 1500,
        "cyber_liability": 2000,
        "umbrella": 500,
    }
    
    industry_factor = industry_factors.get(industry, 1.0)
    base_rate = base_rates.get(policy_type.lower(), 1000)
    
    quotes = []
    for carrier in carriers:
        # Carrier rating affects price (better rated = slightly higher)
        rating_factor = {"A++": 1.05, "A+": 1.02, "A": 1.0, "A-": 0.95}.get(
            carrier["am_best_rating"], 1.0
        )
        
        # Random variation to simulate market differences (±15%)
        import random
        random.seed(hash(carrier["carrier_id"] + policy_type))
        market_factor = 0.85 + (random.random() * 0.30)
        
        # Calculate estimated premium
        units = coverage_limit / 1000000
        estimated_premium = base_rate * units * industry_factor * rating_factor * market_factor
        
        # API-enabled carriers might offer discounts
        if carrier["api_enabled"]:
            estimated_premium *= 0.95  # 5% digital discount
        
        quotes.append({
            "carrier_id": carrier["carrier_id"],
            "carrier_name": carrier["name"],
            "am_best_rating": carrier["am_best_rating"],
            "api_enabled": carrier["api_enabled"],
            "quote_time_hours": carrier["average_quote_time_hours"],
            "estimated_annual_premium": round(estimated_premium, 2),
            "coverage_limit": coverage_limit,
            "notes": carrier.get("notes", ""),
            "quote_valid_days": 30,
            "disclaimer": "Estimated rate - actual quote may vary based on underwriting"
        })
    
    # Sort by premium (lowest first)
    quotes.sort(key=lambda x: x["estimated_annual_premium"])
    
    return quotes


def get_coverage_gaps(client_id: str) -> Dict[str, Any]:
    """
    Analyze a client's current coverage and identify gaps or opportunities.
    
    Args:
        client_id: The client to analyze
    
    Returns:
        Dictionary with coverage analysis and recommendations
    """
    if client_id not in CLIENTS:
        return {"error": f"Client not found: {client_id}"}
    
    client = CLIENTS[client_id]
    policies = [p for p in POLICIES.values() if p["client_id"] == client_id]
    
    # Get policy types client has
    current_coverage = set()
    for policy in policies:
        policy_type = policy["policy_type"]
        if hasattr(policy_type, 'value'):
            current_coverage.add(policy_type.value)
        else:
            current_coverage.add(str(policy_type))
    
    # Industry-specific recommended coverage
    industry_recommendations = {
        "Technology": [
            PolicyType.CYBER_LIABILITY,
            PolicyType.PROFESSIONAL_LIABILITY,
            PolicyType.GENERAL_LIABILITY,
            PolicyType.COMMERCIAL_PROPERTY,
        ],
        "Healthcare": [
            PolicyType.PROFESSIONAL_LIABILITY,
            PolicyType.GENERAL_LIABILITY,
            PolicyType.CYBER_LIABILITY,
            PolicyType.COMMERCIAL_PROPERTY,
            PolicyType.WORKERS_COMP,
        ],
        "Manufacturing": [
            PolicyType.COMMERCIAL_PROPERTY,
            PolicyType.GENERAL_LIABILITY,
            PolicyType.WORKERS_COMP,
            PolicyType.COMMERCIAL_AUTO,
            PolicyType.UMBRELLA,
        ],
        "Construction": [
            PolicyType.GENERAL_LIABILITY,
            PolicyType.WORKERS_COMP,
            PolicyType.COMMERCIAL_AUTO,
            PolicyType.UMBRELLA,
            PolicyType.PROFESSIONAL_LIABILITY,
        ],
        "Transportation": [
            PolicyType.COMMERCIAL_AUTO,
            PolicyType.GENERAL_LIABILITY,
            PolicyType.WORKERS_COMP,
            PolicyType.UMBRELLA,
            PolicyType.COMMERCIAL_PROPERTY,
        ],
    }
    
    recommended = industry_recommendations.get(
        client["industry"], 
        [PolicyType.GENERAL_LIABILITY, PolicyType.COMMERCIAL_PROPERTY]
    )
    
    # Identify gaps
    gaps = []
    for rec in recommended:
        rec_value = rec.value if hasattr(rec, 'value') else str(rec)
        if rec_value not in current_coverage:
            # Get carriers for this type
            carriers = get_carriers_for_policy_type(rec_value)
            carrier_count = len([c for c in carriers if "error" not in c])
            
            gaps.append({
                "policy_type": rec_value,
                "priority": "high" if rec in recommended[:2] else "medium",
                "reason": f"Recommended for {client['industry']} industry",
                "available_carriers": carrier_count,
            })
    
    # Check for umbrella if they have multiple underlying policies
    if len(policies) >= 2 and "umbrella" not in current_coverage:
        total_premium = sum(p["premium"] for p in policies)
        if total_premium > 50000:
            gaps.append({
                "policy_type": "umbrella",
                "priority": "high",
                "reason": f"Multiple underlying policies totaling ${total_premium:,.2f} in premium",
                "available_carriers": 3,
            })
    
    # Coverage limit analysis
    limit_concerns = []
    revenue = client.get("annual_revenue", 0)
    for policy in policies:
        policy_type = policy["policy_type"]
        type_value = policy_type.value if hasattr(policy_type, 'value') else str(policy_type)
        
        # Check if limits seem adequate
        if type_value == "general_liability" and policy["coverage_limit"] < revenue * 0.1:
            limit_concerns.append({
                "policy_id": policy["policy_id"],
                "policy_type": type_value,
                "current_limit": policy["coverage_limit"],
                "recommended_minimum": revenue * 0.1,
                "concern": "GL limit may be low relative to revenue"
            })
    
    return {
        "client_id": client_id,
        "client_name": client["name"],
        "industry": client["industry"],
        "current_policies": len(policies),
        "current_coverage_types": list(current_coverage),
        "total_current_premium": sum(p["premium"] for p in policies),
        "coverage_gaps": gaps,
        "limit_concerns": limit_concerns,
        "cross_sell_opportunities": len(gaps),
    }


def get_claims_history(client_id: str) -> Dict[str, Any]:
    """
    Get claims history and loss analysis for a client.
    
    NOTE: This returns SIMULATED data for the hackathon.
    In production, this would integrate with a claims management system.
    
    Args:
        client_id: The client to analyze
    
    Returns:
        Dictionary with claims history and renewal impact analysis
    """
    if client_id not in CLIENTS:
        return {"error": f"Client not found: {client_id}"}
    
    client = CLIENTS[client_id]
    policies = [p for p in POLICIES.values() if p["client_id"] == client_id]
    total_premium = sum(p["premium"] for p in policies)
    
    # Simulated claims data based on industry
    industry_claim_rates = {
        "Technology": {"frequency": 0.1, "severity": 15000},
        "Healthcare": {"frequency": 0.25, "severity": 75000},
        "Manufacturing": {"frequency": 0.2, "severity": 25000},
        "Construction": {"frequency": 0.35, "severity": 45000},
        "Transportation": {"frequency": 0.3, "severity": 35000},
    }
    
    rates = industry_claim_rates.get(
        client["industry"], 
        {"frequency": 0.15, "severity": 20000}
    )
    
    # Generate simulated 3-year claims history
    import random
    random.seed(hash(client_id))
    
    claims_by_year = []
    for year_offset in range(3):
        year = date.today().year - year_offset
        num_claims = int(random.gauss(rates["frequency"] * len(policies), 0.5))
        num_claims = max(0, num_claims)
        
        total_incurred = sum(
            random.gauss(rates["severity"], rates["severity"] * 0.3)
            for _ in range(num_claims)
        ) if num_claims > 0 else 0
        
        claims_by_year.append({
            "year": year,
            "claim_count": num_claims,
            "total_incurred": round(total_incurred, 2),
            "loss_ratio": round(total_incurred / total_premium, 2) if total_premium > 0 else 0,
        })
    
    # Calculate 3-year loss ratio
    total_claims = sum(y["total_incurred"] for y in claims_by_year)
    three_year_premium = total_premium * 3
    loss_ratio = total_claims / three_year_premium if three_year_premium > 0 else 0
    
    # Renewal impact analysis
    if loss_ratio < 0.4:
        impact = "favorable"
        rate_change = round(random.uniform(-5, 2), 1)
        message = "Claims experience is favorable. Expect flat to modest renewal increase."
    elif loss_ratio < 0.6:
        impact = "neutral"
        rate_change = round(random.uniform(3, 8), 1)
        message = "Claims experience is average. Expect standard market renewal increase."
    elif loss_ratio < 0.8:
        impact = "unfavorable"
        rate_change = round(random.uniform(10, 20), 1)
        message = "Elevated claims activity. Expect above-market renewal increase."
    else:
        impact = "adverse"
        rate_change = round(random.uniform(20, 35), 1)
        message = "Poor loss experience. Significant renewal increase likely. Consider loss control measures."
    
    return {
        "client_id": client_id,
        "client_name": client["name"],
        "industry": client["industry"],
        "analysis_period": "3 years",
        "claims_history": claims_by_year,
        "summary": {
            "total_claims": sum(y["claim_count"] for y in claims_by_year),
            "total_incurred": round(total_claims, 2),
            "average_claim_size": round(total_claims / max(1, sum(y["claim_count"] for y in claims_by_year)), 2),
            "three_year_loss_ratio": round(loss_ratio, 2),
        },
        "renewal_impact": {
            "assessment": impact,
            "expected_rate_change_percent": rate_change,
            "message": message,
        },
        "recommendations": _get_loss_control_recommendations(client["industry"], loss_ratio),
        "disclaimer": "Simulated data for demonstration purposes"
    }


def _get_loss_control_recommendations(industry: str, loss_ratio: float) -> List[str]:
    """Generate loss control recommendations based on industry and loss ratio."""
    recs = []
    
    if loss_ratio > 0.5:
        recs.append("Schedule loss control consultation with carrier")
        recs.append("Review and update safety protocols")
    
    industry_recs = {
        "Technology": [
            "Implement regular security training for employees",
            "Review cyber incident response plan",
        ],
        "Healthcare": [
            "Conduct risk management training for clinical staff",
            "Review documentation and consent procedures",
        ],
        "Manufacturing": [
            "Update machine guarding and safety equipment",
            "Implement regular safety inspections",
        ],
        "Construction": [
            "Enhance job site safety programs",
            "Implement subcontractor qualification process",
        ],
        "Transportation": [
            "Install telematics for fleet monitoring",
            "Implement driver safety training program",
        ],
    }
    
    recs.extend(industry_recs.get(industry, [
        "Review general safety procedures",
        "Consider employee safety training",
    ]))
    
    return recs


# =============================================================================
# Function Tool Definitions for Azure AI Foundry
# =============================================================================

TOOL_DEFINITIONS = [
    {
        "name": "get_client_info",
        "description": "Get detailed information about a specific client including contact details, industry, revenue, and policy summary.",
        "parameters": {
            "type": "object",
            "properties": {
                "client_id": {
                    "type": "string",
                    "description": "The unique identifier for the client (e.g., 'CLI001')"
                }
            },
            "required": ["client_id"],
            "additionalProperties": False
        }
    },
    {
        "name": "get_all_clients",
        "description": "Get a list of all clients with summary information including policy counts and total premiums.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False
        }
    },
    {
        "name": "get_client_policies",
        "description": "Get all insurance policies for a specific client with carrier info and renewal urgency.",
        "parameters": {
            "type": "object",
            "properties": {
                "client_id": {
                    "type": "string",
                    "description": "The unique identifier for the client"
                }
            },
            "required": ["client_id"],
            "additionalProperties": False
        }
    },
    {
        "name": "get_policy_details",
        "description": "Get complete details about a specific policy including client info, carrier info, and renewal analysis.",
        "parameters": {
            "type": "object",
            "properties": {
                "policy_id": {
                    "type": "string",
                    "description": "The unique identifier for the policy (e.g., 'POL001')"
                }
            },
            "required": ["policy_id"],
            "additionalProperties": False
        }
    },
    {
        "name": "get_renewals_by_urgency",
        "description": "Get upcoming policy renewals with priority scores, optionally filtered by urgency level (critical, high, medium, low).",
        "parameters": {
            "type": "object",
            "properties": {
                "urgency": {
                    "type": "string",
                    "description": "Filter by urgency level: 'critical' (0-30 days), 'high' (31-60 days), 'medium' (61-90 days), 'low' (90+ days). Leave empty for all.",
                    "enum": ["critical", "high", "medium", "low"]
                },
                "days_ahead": {
                    "type": "integer",
                    "description": "Number of days to look ahead for renewals (default 90)",
                    "default": 90
                }
            },
            "required": [],
            "additionalProperties": False
        }
    },
    {
        "name": "get_carriers_for_policy_type",
        "description": "Get all insurance carriers that offer a specific type of policy coverage.",
        "parameters": {
            "type": "object",
            "properties": {
                "policy_type": {
                    "type": "string",
                    "description": "Type of policy coverage",
                    "enum": [
                        "commercial_property",
                        "general_liability", 
                        "workers_comp",
                        "commercial_auto",
                        "professional_liability",
                        "cyber_liability",
                        "umbrella"
                    ]
                }
            },
            "required": ["policy_type"],
            "additionalProperties": False
        }
    },
    {
        "name": "compare_carrier_rates",
        "description": "Compare estimated insurance rates from different carriers for a specific policy type and coverage amount.",
        "parameters": {
            "type": "object",
            "properties": {
                "policy_type": {
                    "type": "string",
                    "description": "Type of policy to quote",
                    "enum": [
                        "commercial_property",
                        "general_liability",
                        "workers_comp", 
                        "commercial_auto",
                        "professional_liability",
                        "cyber_liability",
                        "umbrella"
                    ]
                },
                "coverage_limit": {
                    "type": "number",
                    "description": "Desired coverage limit in dollars (e.g., 1000000 for $1M)"
                },
                "industry": {
                    "type": "string",
                    "description": "Client's industry (affects rating factors)"
                },
                "annual_revenue": {
                    "type": "number",
                    "description": "Client's annual revenue in dollars (optional, helps with premium estimation)"
                }
            },
            "required": ["policy_type", "coverage_limit", "industry"],
            "additionalProperties": False
        }
    },
    {
        "name": "get_coverage_gaps",
        "description": "Analyze a client's current coverage portfolio and identify gaps or cross-sell opportunities based on their industry.",
        "parameters": {
            "type": "object",
            "properties": {
                "client_id": {
                    "type": "string",
                    "description": "The unique identifier for the client to analyze"
                }
            },
            "required": ["client_id"],
            "additionalProperties": False
        }
    },
    {
        "name": "get_claims_history",
        "description": "Get claims history and loss analysis for a client, including renewal impact assessment and loss control recommendations.",
        "parameters": {
            "type": "object",
            "properties": {
                "client_id": {
                    "type": "string",
                    "description": "The unique identifier for the client"
                }
            },
            "required": ["client_id"],
            "additionalProperties": False
        }
    }
]


# Function dispatcher for tool calls
TOOL_FUNCTIONS = {
    "get_client_info": get_client_info,
    "get_all_clients": get_all_clients,
    "get_client_policies": get_client_policies,
    "get_policy_details": get_policy_details,
    "get_renewals_by_urgency": get_renewals_by_urgency,
    "get_carriers_for_policy_type": get_carriers_for_policy_type,
    "compare_carrier_rates": compare_carrier_rates,
    "get_coverage_gaps": get_coverage_gaps,
    "get_claims_history": get_claims_history,
}


def execute_tool(tool_name: str, arguments: Dict[str, Any]) -> str:
    """
    Execute a tool function and return JSON result.
    
    Args:
        tool_name: Name of the tool to execute
        arguments: Dictionary of arguments to pass to the tool
    
    Returns:
        JSON string with the tool result
    """
    if tool_name not in TOOL_FUNCTIONS:
        return json.dumps({"error": f"Unknown tool: {tool_name}"})
    
    try:
        result = TOOL_FUNCTIONS[tool_name](**arguments)
        return json.dumps(result, default=str)
    except Exception as e:
        return json.dumps({"error": str(e)})
