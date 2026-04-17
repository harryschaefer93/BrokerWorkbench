"""
Repository layer for database CRUD operations.
Provides async methods for querying and modifying data.
Used by FastAPI routers - abstracts database operations.
"""

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import List, Optional, Dict, Any
from sqlalchemy import select, update, delete, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from .models import (
    Carrier, Client, ProductLine, MarketRate,
    Policy, Quote, Task, Claim, AIInteraction,
    Document, CrossSellOpportunity
)


# ============ Carrier Repository ============

class CarrierRepository:
    """Repository for carrier operations."""
    
    @staticmethod
    async def get_all(db: AsyncSession) -> List[Carrier]:
        """Get all carriers."""
        result = await db.execute(select(Carrier).order_by(Carrier.carrier_name))
        return list(result.scalars().all())
    
    @staticmethod
    async def get_by_id(db: AsyncSession, carrier_id: int) -> Optional[Carrier]:
        """Get carrier by ID."""
        result = await db.execute(
            select(Carrier).where(Carrier.carrier_id == carrier_id)
        )
        return result.scalar_one_or_none()
    
    @staticmethod
    async def get_by_code(db: AsyncSession, carrier_code: str) -> Optional[Carrier]:
        """Get carrier by code."""
        result = await db.execute(
            select(Carrier).where(Carrier.carrier_code == carrier_code)
        )
        return result.scalar_one_or_none()
    
    @staticmethod
    async def get_by_specialty(db: AsyncSession, specialty: str) -> List[Carrier]:
        """Get carriers that support a specific product line."""
        result = await db.execute(
            select(Carrier).where(Carrier.specialty_lines.contains(specialty))
        )
        return list(result.scalars().all())
    
    @staticmethod
    async def get_active_carriers(db: AsyncSession) -> List[Carrier]:
        """Get carriers with active/connected API status."""
        result = await db.execute(
            select(Carrier).where(
                Carrier.api_status.in_(["active", "connected"])
            ).order_by(Carrier.carrier_name)
        )
        return list(result.scalars().all())


# ============ Client Repository ============

class ClientRepository:
    """Repository for client operations."""
    
    @staticmethod
    async def get_all(db: AsyncSession, limit: int = 100) -> List[Client]:
        """Get all clients."""
        result = await db.execute(
            select(Client).order_by(Client.client_name).limit(limit)
        )
        return list(result.scalars().all())
    
    @staticmethod
    async def get_by_id(db: AsyncSession, client_id: int) -> Optional[Client]:
        """Get client by ID."""
        result = await db.execute(
            select(Client).where(Client.client_id == client_id)
        )
        return result.scalar_one_or_none()
    
    @staticmethod
    async def search(
        db: AsyncSession, 
        query: str,
        client_type: Optional[str] = None
    ) -> List[Client]:
        """Search clients by name, email, or contact."""
        conditions = [
            or_(
                Client.client_name.ilike(f"%{query}%"),
                Client.email.ilike(f"%{query}%"),
                Client.primary_contact_name.ilike(f"%{query}%")
            )
        ]
        if client_type:
            conditions.append(Client.client_type == client_type)
        
        result = await db.execute(
            select(Client).where(and_(*conditions)).order_by(Client.client_name)
        )
        return list(result.scalars().all())
    
    @staticmethod
    async def get_by_type(db: AsyncSession, client_type: str) -> List[Client]:
        """Get clients by type (individual/business)."""
        result = await db.execute(
            select(Client).where(Client.client_type == client_type)
        )
        return list(result.scalars().all())
    
    @staticmethod
    async def get_high_value(db: AsyncSession, min_premium: Decimal = Decimal("5000")) -> List[Client]:
        """Get high-value clients by YTD premium."""
        result = await db.execute(
            select(Client)
            .where(Client.total_premium_ytd >= min_premium)
            .order_by(Client.total_premium_ytd.desc())
        )
        return list(result.scalars().all())


# ============ Policy Repository ============

class PolicyRepository:
    """Repository for policy operations."""
    
    @staticmethod
    async def get_all(
        db: AsyncSession,
        status: Optional[str] = None,
        client_id: Optional[int] = None,
        carrier_id: Optional[int] = None,
        limit: int = 100
    ) -> List[Policy]:
        """Get all policies with optional filters."""
        query = select(Policy)
        
        conditions = []
        if status:
            conditions.append(Policy.policy_status == status)
        if client_id:
            conditions.append(Policy.client_id == client_id)
        if carrier_id:
            conditions.append(Policy.carrier_id == carrier_id)
        
        if conditions:
            query = query.where(and_(*conditions))
        
        result = await db.execute(query.order_by(Policy.expiration_date).limit(limit))
        return list(result.scalars().all())
    
    @staticmethod
    async def get_by_id(db: AsyncSession, policy_id: int) -> Optional[Policy]:
        """Get policy by ID."""
        result = await db.execute(
            select(Policy).where(Policy.policy_id == policy_id)
        )
        return result.scalar_one_or_none()
    
    @staticmethod
    async def get_by_number(db: AsyncSession, policy_number: str) -> Optional[Policy]:
        """Get policy by policy number."""
        result = await db.execute(
            select(Policy).where(Policy.policy_number == policy_number)
        )
        return result.scalar_one_or_none()
    
    @staticmethod
    async def get_by_client(db: AsyncSession, client_id: int) -> List[Policy]:
        """Get all policies for a client."""
        result = await db.execute(
            select(Policy)
            .where(Policy.client_id == client_id)
            .order_by(Policy.expiration_date)
        )
        return list(result.scalars().all())
    
    @staticmethod
    async def get_expiring_soon(
        db: AsyncSession,
        days: int = 30,
        status: Optional[str] = None
    ) -> List[Policy]:
        """Get policies expiring within specified days."""
        cutoff_date = date.today() + timedelta(days=days)
        
        conditions = [
            Policy.expiration_date <= cutoff_date,
            Policy.expiration_date >= date.today()
        ]
        if status:
            conditions.append(Policy.policy_status == status)
        else:
            conditions.append(Policy.policy_status.in_(["active", "renewal_due"]))
        
        result = await db.execute(
            select(Policy)
            .where(and_(*conditions))
            .order_by(Policy.expiration_date)
        )
        return list(result.scalars().all())
    
    @staticmethod
    async def get_renewal_summary(db: AsyncSession) -> Dict[str, Any]:
        """Get summary of policies by renewal urgency."""
        today = date.today()
        
        # Count by urgency buckets
        critical = await db.execute(
            select(func.count(Policy.policy_id)).where(
                and_(
                    Policy.expiration_date <= today + timedelta(days=30),
                    Policy.expiration_date >= today,
                    Policy.policy_status.in_(["active", "renewal_due"])
                )
            )
        )
        
        upcoming = await db.execute(
            select(func.count(Policy.policy_id)).where(
                and_(
                    Policy.expiration_date > today + timedelta(days=30),
                    Policy.expiration_date <= today + timedelta(days=60),
                    Policy.policy_status.in_(["active", "renewal_due"])
                )
            )
        )
        
        planned = await db.execute(
            select(func.count(Policy.policy_id)).where(
                and_(
                    Policy.expiration_date > today + timedelta(days=60),
                    Policy.expiration_date <= today + timedelta(days=90),
                    Policy.policy_status.in_(["active", "renewal_due"])
                )
            )
        )
        
        # Total premium at risk
        premium_at_risk = await db.execute(
            select(func.sum(Policy.premium_amount)).where(
                and_(
                    Policy.expiration_date <= today + timedelta(days=90),
                    Policy.expiration_date >= today,
                    Policy.policy_status.in_(["active", "renewal_due"])
                )
            )
        )
        
        return {
            "critical_count": critical.scalar() or 0,
            "upcoming_count": upcoming.scalar() or 0,
            "planned_count": planned.scalar() or 0,
            "total_premium_at_risk": float(premium_at_risk.scalar() or 0)
        }
    
    @staticmethod
    async def update_status(
        db: AsyncSession,
        policy_id: int,
        new_status: str
    ) -> Optional[Policy]:
        """Update policy status."""
        await db.execute(
            update(Policy)
            .where(Policy.policy_id == policy_id)
            .values(policy_status=new_status, updated_at=datetime.utcnow())
        )
        await db.commit()
        return await PolicyRepository.get_by_id(db, policy_id)


# ============ Quote Repository ============

class QuoteRepository:
    """Repository for quote operations."""
    
    @staticmethod
    async def get_all(
        db: AsyncSession,
        client_id: Optional[int] = None,
        status: Optional[str] = None,
        limit: int = 100
    ) -> List[Quote]:
        """Get all quotes with optional filters."""
        query = select(Quote)
        
        conditions = []
        if client_id:
            conditions.append(Quote.client_id == client_id)
        if status:
            conditions.append(Quote.quote_status == status)
        
        if conditions:
            query = query.where(and_(*conditions))
        
        result = await db.execute(query.order_by(Quote.created_at.desc()).limit(limit))
        return list(result.scalars().all())
    
    @staticmethod
    async def get_by_id(db: AsyncSession, quote_id: int) -> Optional[Quote]:
        """Get quote by ID."""
        result = await db.execute(
            select(Quote).where(Quote.quote_id == quote_id)
        )
        return result.scalar_one_or_none()
    
    @staticmethod
    async def get_for_policy(db: AsyncSession, policy_id: int) -> List[Quote]:
        """Get all quotes associated with a policy."""
        result = await db.execute(
            select(Quote)
            .where(Quote.policy_id == policy_id)
            .order_by(Quote.quoted_premium)
        )
        return list(result.scalars().all())
    
    @staticmethod
    async def get_pending(db: AsyncSession) -> List[Quote]:
        """Get pending quotes that need presentation."""
        result = await db.execute(
            select(Quote)
            .where(Quote.quote_status == "pending")
            .order_by(Quote.created_at)
        )
        return list(result.scalars().all())


# ============ Task Repository ============

class TaskRepository:
    """Repository for task operations."""
    
    @staticmethod
    async def get_all(
        db: AsyncSession,
        status: Optional[str] = None,
        priority: Optional[str] = None,
        task_type: Optional[str] = None,
        limit: int = 100
    ) -> List[Task]:
        """Get all tasks with optional filters."""
        query = select(Task)
        
        conditions = []
        if status:
            conditions.append(Task.status == status)
        if priority:
            conditions.append(Task.priority_level == priority)
        if task_type:
            conditions.append(Task.task_type == task_type)
        
        if conditions:
            query = query.where(and_(*conditions))
        
        result = await db.execute(query.order_by(Task.due_date).limit(limit))
        return list(result.scalars().all())
    
    @staticmethod
    async def get_by_id(db: AsyncSession, task_id: int) -> Optional[Task]:
        """Get task by ID."""
        result = await db.execute(
            select(Task).where(Task.task_id == task_id)
        )
        return result.scalar_one_or_none()
    
    @staticmethod
    async def get_pending_renewals(db: AsyncSession) -> List[Task]:
        """Get pending renewal tasks."""
        result = await db.execute(
            select(Task)
            .where(
                and_(
                    Task.task_type == "renewal",
                    Task.status.in_(["pending", "in_progress"])
                )
            )
            .order_by(Task.due_date)
        )
        return list(result.scalars().all())
    
    @staticmethod
    async def get_overdue(db: AsyncSession) -> List[Task]:
        """Get overdue tasks."""
        result = await db.execute(
            select(Task)
            .where(
                and_(
                    Task.due_date < date.today(),
                    Task.status.in_(["pending", "in_progress"])
                )
            )
            .order_by(Task.due_date)
        )
        return list(result.scalars().all())


# ============ Claim Repository ============

class ClaimRepository:
    """Repository for claim operations."""
    
    @staticmethod
    async def get_all(
        db: AsyncSession,
        policy_id: Optional[int] = None,
        status: Optional[str] = None,
        limit: int = 100
    ) -> List[Claim]:
        """Get all claims with optional filters."""
        query = select(Claim)
        
        conditions = []
        if policy_id:
            conditions.append(Claim.policy_id == policy_id)
        if status:
            conditions.append(Claim.claim_status == status)
        
        if conditions:
            query = query.where(and_(*conditions))
        
        result = await db.execute(query.order_by(Claim.created_at.desc()).limit(limit))
        return list(result.scalars().all())
    
    @staticmethod
    async def get_by_id(db: AsyncSession, claim_id: int) -> Optional[Claim]:
        """Get claim by ID."""
        result = await db.execute(
            select(Claim).where(Claim.claim_id == claim_id)
        )
        return result.scalar_one_or_none()
    
    @staticmethod
    async def get_by_policy(db: AsyncSession, policy_id: int) -> List[Claim]:
        """Get all claims for a policy."""
        result = await db.execute(
            select(Claim)
            .where(Claim.policy_id == policy_id)
            .order_by(Claim.date_of_loss.desc())
        )
        return list(result.scalars().all())
    
    @staticmethod
    async def get_open_claims(db: AsyncSession) -> List[Claim]:
        """Get all open/active claims."""
        result = await db.execute(
            select(Claim)
            .where(Claim.claim_status.in_(["reported", "investigating"]))
            .order_by(Claim.reported_date)
        )
        return list(result.scalars().all())


# ============ Cross-Sell Opportunity Repository ============

class CrossSellRepository:
    """Repository for cross-sell opportunity operations."""
    
    @staticmethod
    async def get_all(
        db: AsyncSession,
        client_id: Optional[int] = None,
        status: Optional[str] = None,
        limit: int = 100
    ) -> List[CrossSellOpportunity]:
        """Get all cross-sell opportunities."""
        query = select(CrossSellOpportunity)
        
        conditions = []
        if client_id:
            conditions.append(CrossSellOpportunity.client_id == client_id)
        if status:
            conditions.append(CrossSellOpportunity.status == status)
        
        if conditions:
            query = query.where(and_(*conditions))
        
        result = await db.execute(
            query.order_by(CrossSellOpportunity.confidence_score.desc()).limit(limit)
        )
        return list(result.scalars().all())
    
    @staticmethod
    async def get_by_client(db: AsyncSession, client_id: int) -> List[CrossSellOpportunity]:
        """Get opportunities for a specific client."""
        result = await db.execute(
            select(CrossSellOpportunity)
            .where(CrossSellOpportunity.client_id == client_id)
            .order_by(CrossSellOpportunity.confidence_score.desc())
        )
        return list(result.scalars().all())
    
    @staticmethod
    async def get_identified(db: AsyncSession) -> List[CrossSellOpportunity]:
        """Get newly identified opportunities (not yet presented)."""
        result = await db.execute(
            select(CrossSellOpportunity)
            .where(CrossSellOpportunity.status == "identified")
            .order_by(CrossSellOpportunity.estimated_premium.desc())
        )
        return list(result.scalars().all())


# ============ Market Rate Repository ============

class MarketRateRepository:
    """Repository for market rate operations."""
    
    @staticmethod
    async def get_rates(
        db: AsyncSession,
        carrier_id: Optional[int] = None,
        product_category: Optional[str] = None,
        risk_profile: Optional[str] = None
    ) -> List[MarketRate]:
        """Get market rates with optional filters."""
        query = select(MarketRate)
        
        conditions = [
            or_(
                MarketRate.expiration_date >= date.today(),
                MarketRate.expiration_date.is_(None)
            )
        ]
        
        if carrier_id:
            conditions.append(MarketRate.carrier_id == carrier_id)
        if product_category:
            conditions.append(MarketRate.product_category == product_category)
        if risk_profile:
            conditions.append(MarketRate.risk_profile == risk_profile)
        
        result = await db.execute(
            query.where(and_(*conditions)).order_by(MarketRate.base_rate)
        )
        return list(result.scalars().all())
    
    @staticmethod
    async def get_competitive_rates(
        db: AsyncSession,
        product_category: str,
        risk_profile: str = "medium"
    ) -> List[Dict[str, Any]]:
        """Get competitive rate comparison across carriers."""
        result = await db.execute(
            select(MarketRate, Carrier)
            .join(Carrier, MarketRate.carrier_id == Carrier.carrier_id)
            .where(
                and_(
                    MarketRate.product_category == product_category,
                    MarketRate.risk_profile == risk_profile,
                    or_(
                        MarketRate.expiration_date >= date.today(),
                        MarketRate.expiration_date.is_(None)
                    )
                )
            )
            .order_by(MarketRate.base_rate)
        )
        
        return [
            {
                "carrier_name": carrier.carrier_name,
                "carrier_code": carrier.carrier_code,
                "rating": carrier.rating,
                "base_rate": float(rate.base_rate) if rate.base_rate else None,
                "rate_factor": float(rate.rate_factor) if rate.rate_factor else None,
            }
            for rate, carrier in result.all()
        ]
