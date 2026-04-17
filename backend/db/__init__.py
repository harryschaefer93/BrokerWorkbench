"""
Database module for Insurance Broker Workbench.
Uses SQLAlchemy with async support for database operations.
Designed for easy swap between SQLite (dev) and Azure SQL (prod).
"""

from .connection import get_db, engine, AsyncSessionLocal
from .models import (
    Base,
    Carrier,
    Client,
    ProductLine,
    MarketRate,
    Policy,
    Quote,
    Task,
    Claim,
    AIInteraction,
    Document,
    CrossSellOpportunity
)

__all__ = [
    "get_db",
    "engine", 
    "AsyncSessionLocal",
    "Base",
    "Carrier",
    "Client",
    "ProductLine",
    "MarketRate",
    "Policy",
    "Quote",
    "Task",
    "Claim",
    "AIInteraction",
    "Document",
    "CrossSellOpportunity"
]
