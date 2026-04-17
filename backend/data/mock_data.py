"""
Synthetic mock data for Insurance Broker Workbench
This will be replaced with Azure SQL database connection when ready
"""
from datetime import datetime, date, timedelta
from typing import Dict, List
import uuid

from models.schemas import (
    Client, Carrier, Policy,
    PolicyType, PolicyStatus, CarrierRating
)


def _now() -> datetime:
    return datetime.utcnow()


# ============ Mock Carriers ============

CARRIERS: Dict[str, dict] = {
    "CAR001": {
        "carrier_id": "CAR001",
        "name": "Liberty Mutual",
        "am_best_rating": CarrierRating.A,
        "supported_lines": [
            PolicyType.COMMERCIAL_PROPERTY,
            PolicyType.GENERAL_LIABILITY,
            PolicyType.WORKERS_COMP,
            PolicyType.COMMERCIAL_AUTO
        ],
        "api_enabled": True,
        "average_quote_time_hours": 2.5,
        "notes": "Strong in middle market",
        "created_at": _now(),
        "updated_at": _now()
    },
    "CAR002": {
        "carrier_id": "CAR002",
        "name": "The Hartford",
        "am_best_rating": CarrierRating.A_PLUS,
        "supported_lines": [
            PolicyType.COMMERCIAL_PROPERTY,
            PolicyType.GENERAL_LIABILITY,
            PolicyType.WORKERS_COMP,
            PolicyType.PROFESSIONAL_LIABILITY
        ],
        "api_enabled": True,
        "average_quote_time_hours": 3.0,
        "notes": "Excellent small business programs",
        "created_at": _now(),
        "updated_at": _now()
    },
    "CAR003": {
        "carrier_id": "CAR003",
        "name": "Travelers",
        "am_best_rating": CarrierRating.A_PLUS_PLUS,
        "supported_lines": [
            PolicyType.COMMERCIAL_PROPERTY,
            PolicyType.GENERAL_LIABILITY,
            PolicyType.COMMERCIAL_AUTO,
            PolicyType.UMBRELLA
        ],
        "api_enabled": True,
        "average_quote_time_hours": 1.5,
        "notes": "Fast API integration, competitive rates",
        "created_at": _now(),
        "updated_at": _now()
    },
    "CAR004": {
        "carrier_id": "CAR004",
        "name": "CNA Insurance",
        "am_best_rating": CarrierRating.A,
        "supported_lines": [
            PolicyType.PROFESSIONAL_LIABILITY,
            PolicyType.CYBER_LIABILITY,
            PolicyType.GENERAL_LIABILITY
        ],
        "api_enabled": False,
        "average_quote_time_hours": 24.0,
        "notes": "Specialty lines focus, manual quoting",
        "created_at": _now(),
        "updated_at": _now()
    },
    "CAR005": {
        "carrier_id": "CAR005",
        "name": "Chubb",
        "am_best_rating": CarrierRating.A_PLUS_PLUS,
        "supported_lines": [
            PolicyType.COMMERCIAL_PROPERTY,
            PolicyType.CYBER_LIABILITY,
            PolicyType.PROFESSIONAL_LIABILITY,
            PolicyType.UMBRELLA
        ],
        "api_enabled": True,
        "average_quote_time_hours": 4.0,
        "notes": "Premium carrier, high limits available",
        "created_at": _now(),
        "updated_at": _now()
    },
    "CAR006": {
        "carrier_id": "CAR006",
        "name": "Zurich",
        "am_best_rating": CarrierRating.A_PLUS,
        "supported_lines": [
            PolicyType.COMMERCIAL_PROPERTY,
            PolicyType.GENERAL_LIABILITY,
            PolicyType.WORKERS_COMP,
            PolicyType.COMMERCIAL_AUTO,
            PolicyType.UMBRELLA
        ],
        "api_enabled": True,
        "average_quote_time_hours": 2.0,
        "notes": "Strong risk engineering services",
        "created_at": _now(),
        "updated_at": _now()
    },
    "CAR007": {
        "carrier_id": "CAR007",
        "name": "Berkshire Hathaway",
        "am_best_rating": CarrierRating.A_PLUS_PLUS,
        "supported_lines": [
            PolicyType.WORKERS_COMP,
            PolicyType.COMMERCIAL_AUTO,
            PolicyType.GENERAL_LIABILITY
        ],
        "api_enabled": False,
        "average_quote_time_hours": 48.0,
        "notes": "Selective underwriting, large accounts",
        "created_at": _now(),
        "updated_at": _now()
    },
    "CAR008": {
        "carrier_id": "CAR008",
        "name": "Coalition",
        "am_best_rating": CarrierRating.A_MINUS,
        "supported_lines": [
            PolicyType.CYBER_LIABILITY
        ],
        "api_enabled": True,
        "average_quote_time_hours": 0.5,
        "notes": "Cyber specialist, instant quotes",
        "created_at": _now(),
        "updated_at": _now()
    }
}


# ============ Mock Clients ============

CLIENTS: Dict[str, dict] = {
    "CLI001": {
        "client_id": "CLI001",
        "name": "Acme Manufacturing Co.",
        "industry": "Manufacturing",
        "contact_name": "John Smith",
        "contact_email": "jsmith@acmemfg.com",
        "contact_phone": "(555) 123-4567",
        "address": "1234 Industrial Blvd, Chicago, IL 60601",
        "annual_revenue": 15000000.00,
        "employee_count": 120,
        "created_at": _now(),
        "updated_at": _now()
    },
    "CLI002": {
        "client_id": "CLI002",
        "name": "TechStart Solutions",
        "industry": "Technology",
        "contact_name": "Sarah Johnson",
        "contact_email": "sjohnson@techstart.io",
        "contact_phone": "(555) 234-5678",
        "address": "500 Innovation Way, Austin, TX 78701",
        "annual_revenue": 5000000.00,
        "employee_count": 45,
        "created_at": _now(),
        "updated_at": _now()
    },
    "CLI003": {
        "client_id": "CLI003",
        "name": "Riverside Medical Group",
        "industry": "Healthcare",
        "contact_name": "Dr. Michael Chen",
        "contact_email": "mchen@riversidemedical.com",
        "contact_phone": "(555) 345-6789",
        "address": "789 Health Center Dr, Seattle, WA 98101",
        "annual_revenue": 25000000.00,
        "employee_count": 200,
        "created_at": _now(),
        "updated_at": _now()
    },
    "CLI004": {
        "client_id": "CLI004",
        "name": "Green Valley Construction",
        "industry": "Construction",
        "contact_name": "Mike Rodriguez",
        "contact_email": "mrodriguez@greenvalley.com",
        "contact_phone": "(555) 456-7890",
        "address": "2100 Builder's Way, Denver, CO 80202",
        "annual_revenue": 35000000.00,
        "employee_count": 300,
        "created_at": _now(),
        "updated_at": _now()
    },
    "CLI005": {
        "client_id": "CLI005",
        "name": "Pacific Logistics Inc.",
        "industry": "Transportation",
        "contact_name": "Lisa Wong",
        "contact_email": "lwong@pacificlogistics.com",
        "contact_phone": "(555) 567-8901",
        "address": "3300 Harbor Blvd, Long Beach, CA 90802",
        "annual_revenue": 50000000.00,
        "employee_count": 450,
        "created_at": _now(),
        "updated_at": _now()
    }
}


# ============ Mock Policies ============

# Helper to create dates relative to today
def _future_date(days: int) -> date:
    return date.today() + timedelta(days=days)


def _past_date(days: int) -> date:
    return date.today() - timedelta(days=days)


POLICIES: Dict[str, dict] = {
    # Acme Manufacturing - Multiple policies, one renewing soon
    "POL001": {
        "policy_id": "POL001",
        "client_id": "CLI001",
        "carrier_id": "CAR001",
        "policy_type": PolicyType.COMMERCIAL_PROPERTY,
        "policy_number": "LM-CP-2024-001234",
        "effective_date": _past_date(330),
        "expiration_date": _future_date(35),  # Renews in 35 days - HIGH priority
        "premium": 45000.00,
        "coverage_limit": 5000000.00,
        "deductible": 10000.00,
        "status": PolicyStatus.ACTIVE,
        "notes": "Main manufacturing facility coverage",
        "created_at": _now(),
        "updated_at": _now()
    },
    "POL002": {
        "policy_id": "POL002",
        "client_id": "CLI001",
        "carrier_id": "CAR002",
        "policy_type": PolicyType.WORKERS_COMP,
        "policy_number": "HF-WC-2024-005678",
        "effective_date": _past_date(200),
        "expiration_date": _future_date(165),
        "premium": 62000.00,
        "coverage_limit": 1000000.00,
        "deductible": 5000.00,
        "status": PolicyStatus.ACTIVE,
        "notes": "120 employees covered",
        "created_at": _now(),
        "updated_at": _now()
    },
    
    # TechStart Solutions - Cyber coverage renewing CRITICAL
    "POL003": {
        "policy_id": "POL003",
        "client_id": "CLI002",
        "carrier_id": "CAR008",
        "policy_type": PolicyType.CYBER_LIABILITY,
        "policy_number": "COA-CY-2024-009012",
        "effective_date": _past_date(350),
        "expiration_date": _future_date(15),  # Renews in 15 days - CRITICAL
        "premium": 18000.00,
        "coverage_limit": 2000000.00,
        "deductible": 25000.00,
        "status": PolicyStatus.ACTIVE,
        "notes": "Tech company - high cyber risk",
        "created_at": _now(),
        "updated_at": _now()
    },
    "POL004": {
        "policy_id": "POL004",
        "client_id": "CLI002",
        "carrier_id": "CAR004",
        "policy_type": PolicyType.PROFESSIONAL_LIABILITY,
        "policy_number": "CNA-PL-2024-003456",
        "effective_date": _past_date(100),
        "expiration_date": _future_date(265),
        "premium": 12000.00,
        "coverage_limit": 1000000.00,
        "deductible": 10000.00,
        "status": PolicyStatus.ACTIVE,
        "notes": "E&O coverage for consulting services",
        "created_at": _now(),
        "updated_at": _now()
    },
    
    # Riverside Medical - Multiple policies
    "POL005": {
        "policy_id": "POL005",
        "client_id": "CLI003",
        "carrier_id": "CAR005",
        "policy_type": PolicyType.PROFESSIONAL_LIABILITY,
        "policy_number": "CHB-PL-2024-007890",
        "effective_date": _past_date(280),
        "expiration_date": _future_date(85),  # Renews in 85 days - MEDIUM
        "premium": 95000.00,
        "coverage_limit": 5000000.00,
        "deductible": 50000.00,
        "status": PolicyStatus.ACTIVE,
        "notes": "Medical malpractice - 15 physicians",
        "created_at": _now(),
        "updated_at": _now()
    },
    "POL006": {
        "policy_id": "POL006",
        "client_id": "CLI003",
        "carrier_id": "CAR003",
        "policy_type": PolicyType.COMMERCIAL_PROPERTY,
        "policy_number": "TRV-CP-2024-002345",
        "effective_date": _past_date(150),
        "expiration_date": _future_date(215),
        "premium": 38000.00,
        "coverage_limit": 8000000.00,
        "deductible": 25000.00,
        "status": PolicyStatus.ACTIVE,
        "notes": "Medical office building",
        "created_at": _now(),
        "updated_at": _now()
    },
    
    # Green Valley Construction - High risk, renewing soon
    "POL007": {
        "policy_id": "POL007",
        "client_id": "CLI004",
        "carrier_id": "CAR006",
        "policy_type": PolicyType.GENERAL_LIABILITY,
        "policy_number": "ZUR-GL-2024-004567",
        "effective_date": _past_date(340),
        "expiration_date": _future_date(25),  # Renews in 25 days - CRITICAL
        "premium": 85000.00,
        "coverage_limit": 2000000.00,
        "deductible": 15000.00,
        "status": PolicyStatus.ACTIVE,
        "notes": "Construction GL - high hazard",
        "created_at": _now(),
        "updated_at": _now()
    },
    "POL008": {
        "policy_id": "POL008",
        "client_id": "CLI004",
        "carrier_id": "CAR007",
        "policy_type": PolicyType.WORKERS_COMP,
        "policy_number": "BH-WC-2024-006789",
        "effective_date": _past_date(60),
        "expiration_date": _future_date(305),
        "premium": 145000.00,
        "coverage_limit": 1000000.00,
        "deductible": 10000.00,
        "status": PolicyStatus.ACTIVE,
        "notes": "300 employees, construction class codes",
        "created_at": _now(),
        "updated_at": _now()
    },
    
    # Pacific Logistics - Fleet coverage renewing
    "POL009": {
        "policy_id": "POL009",
        "client_id": "CLI005",
        "carrier_id": "CAR003",
        "policy_type": PolicyType.COMMERCIAL_AUTO,
        "policy_number": "TRV-CA-2024-008901",
        "effective_date": _past_date(310),
        "expiration_date": _future_date(55),  # Renews in 55 days - HIGH
        "premium": 220000.00,
        "coverage_limit": 5000000.00,
        "deductible": 50000.00,
        "status": PolicyStatus.ACTIVE,
        "notes": "Fleet of 75 trucks, nationwide coverage",
        "created_at": _now(),
        "updated_at": _now()
    },
    "POL010": {
        "policy_id": "POL010",
        "client_id": "CLI005",
        "carrier_id": "CAR005",
        "policy_type": PolicyType.UMBRELLA,
        "policy_number": "CHB-UM-2024-001234",
        "effective_date": _past_date(180),
        "expiration_date": _future_date(185),
        "premium": 75000.00,
        "coverage_limit": 25000000.00,
        "deductible": 0.00,
        "status": PolicyStatus.ACTIVE,
        "notes": "Excess liability over auto and GL",
        "created_at": _now(),
        "updated_at": _now()
    }
}


def generate_id(prefix: str) -> str:
    """Generate a new unique ID with prefix"""
    return f"{prefix}{uuid.uuid4().hex[:8].upper()}"
