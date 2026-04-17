"""
SQLAlchemy ORM Models for Insurance Broker Workbench.
Maps to Paras's SQLite schema in /data/db/*.db

These models work with both SQLite (dev) and Azure SQL (prod).

Azure SQL layout: single database, two schemas:
  - master_data: carriers, clients, product_lines, market_rates
  - txn: policies, quotes, tasks, claims, ai_interactions, documents, cross_sell_opportunities

For SQLite, schema names are ignored via execution_options.schema_translate_map.
"""

from datetime import datetime, date
from decimal import Decimal
from typing import Optional, List
from sqlalchemy import (
    String, Integer, Boolean, Text, Date, DateTime, 
    DECIMAL, ForeignKey, JSON
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# Schema constants — used in models and in connection.py schema_translate_map
MASTER_SCHEMA = "master_data"
TXN_SCHEMA = "txn"


class Base(DeclarativeBase):
    """Base class for all models."""
    pass


# ============ Master Database Models ============

class Carrier(Base):
    """Insurance carrier/company reference data."""
    __tablename__ = "carriers"
    __table_args__ = {"schema": MASTER_SCHEMA}
    
    carrier_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    carrier_name: Mapped[str] = mapped_column(String(100), nullable=False)
    carrier_code: Mapped[str] = mapped_column(String(10), unique=True, nullable=False)
    api_endpoint: Mapped[Optional[str]] = mapped_column(String(255))
    api_status: Mapped[str] = mapped_column(String(20), default="active")  # active, connected, slow, offline
    rating: Mapped[Optional[str]] = mapped_column(String(10))  # AM Best rating: A++, A+, A, etc.
    specialty_lines: Mapped[Optional[str]] = mapped_column(Text)  # Comma-separated
    market_share: Mapped[Optional[Decimal]] = mapped_column(DECIMAL(5, 2))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    market_rates: Mapped[List["MarketRate"]] = relationship(back_populates="carrier")


class Client(Base):
    """Client/customer master data."""
    __tablename__ = "clients"
    __table_args__ = {"schema": MASTER_SCHEMA}
    
    client_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_name: Mapped[str] = mapped_column(String(200), nullable=False)
    client_type: Mapped[str] = mapped_column(String(20), nullable=False)  # individual, business
    business_industry: Mapped[Optional[str]] = mapped_column(String(100))
    primary_contact_name: Mapped[Optional[str]] = mapped_column(String(100))
    email: Mapped[Optional[str]] = mapped_column(String(100))
    phone: Mapped[Optional[str]] = mapped_column(String(20))
    address_line1: Mapped[Optional[str]] = mapped_column(String(200))
    address_line2: Mapped[Optional[str]] = mapped_column(String(200))
    city: Mapped[Optional[str]] = mapped_column(String(100))
    state: Mapped[Optional[str]] = mapped_column(String(50))
    zip_code: Mapped[Optional[str]] = mapped_column(String(10))
    risk_score: Mapped[int] = mapped_column(Integer, default=50)  # 1-100 scale
    customer_since: Mapped[Optional[date]] = mapped_column(Date)
    total_premium_ytd: Mapped[Decimal] = mapped_column(DECIMAL(12, 2), default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ProductLine(Base):
    """Insurance product line definitions."""
    __tablename__ = "product_lines"
    __table_args__ = {"schema": MASTER_SCHEMA}
    
    product_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_name: Mapped[str] = mapped_column(String(100), nullable=False)
    product_category: Mapped[str] = mapped_column(String(50), nullable=False)  # auto, home, commercial, life, umbrella
    base_premium_range: Mapped[Optional[str]] = mapped_column(String(50))
    risk_factors: Mapped[Optional[str]] = mapped_column(Text)  # JSON array
    coverage_options: Mapped[Optional[str]] = mapped_column(Text)  # JSON array
    target_market: Mapped[Optional[str]] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class MarketRate(Base):
    """Competitive market rates by carrier and product."""
    __tablename__ = "market_rates"
    __table_args__ = {"schema": MASTER_SCHEMA}
    
    rate_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    carrier_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey(f"{MASTER_SCHEMA}.carriers.carrier_id"))
    product_category: Mapped[Optional[str]] = mapped_column(String(50))
    risk_profile: Mapped[Optional[str]] = mapped_column(String(50))  # low, medium, high
    base_rate: Mapped[Optional[Decimal]] = mapped_column(DECIMAL(10, 2))
    rate_factor: Mapped[Optional[Decimal]] = mapped_column(DECIMAL(5, 3))
    effective_date: Mapped[Optional[date]] = mapped_column(Date)
    expiration_date: Mapped[Optional[date]] = mapped_column(Date)
    market_region: Mapped[Optional[str]] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    # Relationships
    carrier: Mapped[Optional["Carrier"]] = relationship(back_populates="market_rates")


# ============ Transactional Database Models ============

class Policy(Base):
    """Insurance policy records."""
    __tablename__ = "policies"
    __table_args__ = {"schema": TXN_SCHEMA}
    
    policy_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    policy_number: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    client_id: Mapped[int] = mapped_column(Integer, nullable=False)  # FK to master.clients
    carrier_id: Mapped[int] = mapped_column(Integer, nullable=False)  # FK to master.carriers
    product_category: Mapped[str] = mapped_column(String(50), nullable=False)
    policy_status: Mapped[str] = mapped_column(String(20), default="active")  # active, renewal_due, expired, cancelled
    premium_amount: Mapped[Optional[Decimal]] = mapped_column(DECIMAL(12, 2))
    deductible: Mapped[Optional[Decimal]] = mapped_column(DECIMAL(10, 2))
    coverage_limit: Mapped[Optional[Decimal]] = mapped_column(DECIMAL(15, 2))
    effective_date: Mapped[Optional[date]] = mapped_column(Date)
    expiration_date: Mapped[Optional[date]] = mapped_column(Date)
    renewal_date: Mapped[Optional[date]] = mapped_column(Date)
    auto_renew: Mapped[bool] = mapped_column(Boolean, default=True)
    commission_rate: Mapped[Optional[Decimal]] = mapped_column(DECIMAL(5, 2))
    commission_amount: Mapped[Optional[Decimal]] = mapped_column(DECIMAL(10, 2))
    last_review_date: Mapped[Optional[date]] = mapped_column(Date)
    notes: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    quotes: Mapped[List["Quote"]] = relationship(back_populates="policy", foreign_keys="Quote.policy_id")
    claims: Mapped[List["Claim"]] = relationship(back_populates="policy")
    tasks: Mapped[List["Task"]] = relationship(back_populates="policy")
    documents: Mapped[List["Document"]] = relationship(back_populates="policy")


class Quote(Base):
    """Insurance quote records."""
    __tablename__ = "quotes"
    __table_args__ = {"schema": TXN_SCHEMA}
    
    quote_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_id: Mapped[int] = mapped_column(Integer, nullable=False)
    carrier_id: Mapped[int] = mapped_column(Integer, nullable=False)
    policy_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey(f"{TXN_SCHEMA}.policies.policy_id"))
    product_category: Mapped[Optional[str]] = mapped_column(String(50))
    quote_number: Mapped[Optional[str]] = mapped_column(String(50))
    quoted_premium: Mapped[Optional[Decimal]] = mapped_column(DECIMAL(12, 2))
    coverage_details: Mapped[Optional[str]] = mapped_column(Text)  # JSON
    quote_status: Mapped[str] = mapped_column(String(20), default="pending")  # pending, presented, accepted, declined, expired
    valid_until: Mapped[Optional[date]] = mapped_column(Date)
    competitive_position: Mapped[Optional[str]] = mapped_column(String(20))  # best, competitive, high
    savings_vs_current: Mapped[Optional[Decimal]] = mapped_column(DECIMAL(10, 2))
    quote_source: Mapped[Optional[str]] = mapped_column(String(50))  # api, manual, rate_sheet
    response_time_seconds: Mapped[Optional[int]] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    presented_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    decision_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    
    # Relationships
    policy: Mapped[Optional["Policy"]] = relationship(back_populates="quotes")


class Task(Base):
    """Broker tasks and priorities."""
    __tablename__ = "tasks"
    __table_args__ = {"schema": TXN_SCHEMA}
    
    task_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_id: Mapped[Optional[int]] = mapped_column(Integer)
    policy_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey(f"{TXN_SCHEMA}.policies.policy_id"))
    task_type: Mapped[str] = mapped_column(String(50), nullable=False)  # renewal, follow_up, claim_review, cross_sell
    priority_level: Mapped[str] = mapped_column(String(10), nullable=False)  # high, medium, low
    task_title: Mapped[str] = mapped_column(String(200), nullable=False)
    task_description: Mapped[Optional[str]] = mapped_column(Text)
    due_date: Mapped[Optional[date]] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending, in_progress, completed, cancelled
    assigned_to: Mapped[Optional[str]] = mapped_column(String(100))
    potential_value: Mapped[Optional[Decimal]] = mapped_column(DECIMAL(12, 2))
    completion_notes: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    
    # Relationships
    policy: Mapped[Optional["Policy"]] = relationship(back_populates="tasks")


class Claim(Base):
    """Insurance claim records."""
    __tablename__ = "claims"
    __table_args__ = {"schema": TXN_SCHEMA}
    
    claim_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    policy_id: Mapped[int] = mapped_column(Integer, ForeignKey(f"{TXN_SCHEMA}.policies.policy_id"), nullable=False)
    claim_number: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    claim_type: Mapped[Optional[str]] = mapped_column(String(50))  # auto_accident, property_damage, theft, liability
    claim_amount: Mapped[Optional[Decimal]] = mapped_column(DECIMAL(12, 2))
    claim_status: Mapped[str] = mapped_column(String(30), default="reported")  # reported, investigating, approved, denied, settled
    date_of_loss: Mapped[Optional[date]] = mapped_column(Date)
    reported_date: Mapped[Optional[date]] = mapped_column(Date)
    description: Mapped[Optional[str]] = mapped_column(Text)
    adjuster_name: Mapped[Optional[str]] = mapped_column(String(100))
    settlement_amount: Mapped[Optional[Decimal]] = mapped_column(DECIMAL(12, 2))
    impact_on_renewal: Mapped[Optional[str]] = mapped_column(String(20))  # none, minor, major
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    policy: Mapped["Policy"] = relationship(back_populates="claims")


class AIInteraction(Base):
    """AI assistant interaction logs."""
    __tablename__ = "ai_interactions"
    __table_args__ = {"schema": TXN_SCHEMA}
    
    interaction_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[Optional[str]] = mapped_column(String(100))
    session_id: Mapped[Optional[str]] = mapped_column(String(100))
    interaction_type: Mapped[Optional[str]] = mapped_column(String(50))  # search, insight, recommendation, summary
    user_query: Mapped[Optional[str]] = mapped_column(Text)
    ai_response: Mapped[Optional[str]] = mapped_column(Text)
    context_data: Mapped[Optional[str]] = mapped_column(Text)  # JSON with relevant IDs and metadata
    confidence_score: Mapped[Optional[Decimal]] = mapped_column(DECIMAL(3, 2))
    feedback_rating: Mapped[Optional[int]] = mapped_column(Integer)  # 1-5 rating from user
    processing_time_ms: Mapped[Optional[int]] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Document(Base):
    """Document storage and tracking."""
    __tablename__ = "documents"
    __table_args__ = {"schema": TXN_SCHEMA}
    
    document_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_id: Mapped[Optional[int]] = mapped_column(Integer)
    policy_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey(f"{TXN_SCHEMA}.policies.policy_id"))
    document_type: Mapped[Optional[str]] = mapped_column(String(50))  # policy_doc, claim_form, quote_comparison, presentation
    document_name: Mapped[Optional[str]] = mapped_column(String(255))
    file_path: Mapped[Optional[str]] = mapped_column(String(500))
    file_size_bytes: Mapped[Optional[int]] = mapped_column(Integer)
    mime_type: Mapped[Optional[str]] = mapped_column(String(100))
    generated_by: Mapped[Optional[str]] = mapped_column(String(50))  # user, ai, system
    tags: Mapped[Optional[str]] = mapped_column(Text)  # JSON array of tags
    last_accessed: Mapped[Optional[datetime]] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    # Relationships
    policy: Mapped[Optional["Policy"]] = relationship(back_populates="documents")


class CrossSellOpportunity(Base):
    """AI-identified cross-sell opportunities."""
    __tablename__ = "cross_sell_opportunities"
    __table_args__ = {"schema": TXN_SCHEMA}
    
    opportunity_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_id: Mapped[int] = mapped_column(Integer, nullable=False)
    current_product_category: Mapped[Optional[str]] = mapped_column(String(50))
    recommended_product_category: Mapped[Optional[str]] = mapped_column(String(50))
    opportunity_type: Mapped[Optional[str]] = mapped_column(String(50))  # gap_coverage, life_event, risk_increase
    estimated_premium: Mapped[Optional[Decimal]] = mapped_column(DECIMAL(10, 2))
    confidence_score: Mapped[Optional[Decimal]] = mapped_column(DECIMAL(3, 2))
    status: Mapped[str] = mapped_column(String(20), default="identified")  # identified, presented, accepted, declined
    reasoning: Mapped[Optional[str]] = mapped_column(Text)
    ai_generated: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    presented_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    decision_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
