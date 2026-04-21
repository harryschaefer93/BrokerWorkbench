"""
Pydantic models for Insurance Broker Workbench API
"""
from datetime import date, datetime
from typing import Optional, List
from enum import Enum
from pydantic import BaseModel, Field


# ============ Enums ============

class PolicyStatus(str, Enum):
    ACTIVE = "active"
    PENDING = "pending"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class PolicyType(str, Enum):
    COMMERCIAL_PROPERTY = "commercial_property"
    GENERAL_LIABILITY = "general_liability"
    WORKERS_COMP = "workers_comp"
    COMMERCIAL_AUTO = "commercial_auto"
    PROFESSIONAL_LIABILITY = "professional_liability"
    CYBER_LIABILITY = "cyber_liability"
    UMBRELLA = "umbrella"


class RenewalUrgency(str, Enum):
    CRITICAL = "critical"      # Within 30 days
    HIGH = "high"              # 31-60 days
    MEDIUM = "medium"          # 61-90 days
    LOW = "low"                # 90+ days


class CarrierRating(str, Enum):
    A_PLUS_PLUS = "A++"
    A_PLUS = "A+"
    A = "A"
    A_MINUS = "A-"
    B_PLUS_PLUS = "B++"
    B_PLUS = "B+"
    B = "B"


# ============ Client Models ============

class ClientBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    industry: str
    contact_name: str
    contact_email: str
    contact_phone: str
    address: Optional[str] = None
    annual_revenue: Optional[float] = None
    employee_count: Optional[int] = None


class ClientCreate(ClientBase):
    pass


class ClientUpdate(BaseModel):
    name: Optional[str] = None
    industry: Optional[str] = None
    contact_name: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    address: Optional[str] = None
    annual_revenue: Optional[float] = None
    employee_count: Optional[int] = None


class Client(ClientBase):
    client_id: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ============ Carrier Models ============

class CarrierBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    am_best_rating: CarrierRating
    supported_lines: List[PolicyType]
    api_enabled: bool = False
    api_status: str = "inactive"
    average_quote_time_hours: Optional[float] = None
    notes: Optional[str] = None


class CarrierCreate(CarrierBase):
    pass


class CarrierUpdate(BaseModel):
    name: Optional[str] = None
    am_best_rating: Optional[CarrierRating] = None
    supported_lines: Optional[List[PolicyType]] = None
    api_enabled: Optional[bool] = None
    average_quote_time_hours: Optional[float] = None
    notes: Optional[str] = None


class Carrier(CarrierBase):
    carrier_id: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ============ Policy Models ============

class PolicyBase(BaseModel):
    client_id: str
    carrier_id: str
    policy_type: PolicyType
    policy_number: str
    effective_date: date
    expiration_date: date
    premium: float
    coverage_limit: float
    deductible: float
    status: PolicyStatus = PolicyStatus.ACTIVE
    notes: Optional[str] = None


class PolicyCreate(PolicyBase):
    pass


class PolicyUpdate(BaseModel):
    carrier_id: Optional[str] = None
    policy_type: Optional[PolicyType] = None
    policy_number: Optional[str] = None
    effective_date: Optional[date] = None
    expiration_date: Optional[date] = None
    premium: Optional[float] = None
    coverage_limit: Optional[float] = None
    deductible: Optional[float] = None
    status: Optional[PolicyStatus] = None
    notes: Optional[str] = None


class Policy(PolicyBase):
    policy_id: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ============ Renewal Tracking Models ============

class RenewalInfo(BaseModel):
    policy_id: str
    policy_number: str
    client_id: str
    client_name: str
    carrier_id: str
    carrier_name: str
    policy_type: PolicyType
    expiration_date: date
    days_until_renewal: int
    urgency: RenewalUrgency
    premium: float
    priority_score: float = Field(..., description="0-100 score for task prioritization")


class RenewalSummary(BaseModel):
    total_renewals: int
    critical_count: int
    high_count: int
    medium_count: int
    low_count: int
    total_premium_at_risk: float
    renewals: List[RenewalInfo]
