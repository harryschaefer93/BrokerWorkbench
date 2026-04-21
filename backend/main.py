"""
Insurance Broker Workbench API

FastAPI backend providing:
- Policy CRUD operations
- Client management
- Carrier management  
- Renewal tracking and prioritization
- AI Agent interactions (Phase 2)

Run with: uvicorn main:app --reload
Docs available at: http://localhost:8000/docs
"""
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware

# Original routers (mock data)
from routers import policies, clients, carriers, renewals

# v2 routers (SQLite database via SQLAlchemy)
from routers import policies_v2, clients_v2, carriers_v2, renewals_v2

# AI Agent router (Phase 2)
from routers import agents

# Initialize FastAPI app
app = FastAPI(
    title="Insurance Broker Workbench API",
    description="""
Backend API for the Insurance Broker Workbench - Strategic Non-Accelerate 3 Hackathon

## API Versions
- **v1 (default)**: `/api/...` - Uses in-memory mock data
- **v2**: `/api/v2/...` - Uses SQLite databases (ready for Azure SQL swap)
- **Agents**: `/api/agent/...` - AI-powered analysis and recommendations

## Data Sources (v2)
- **Master DB**: Carriers, Clients, Product Lines, Market Rates
- **Transactional DB**: Policies, Quotes, Claims, Tasks

## AI Agents
- **Quote Comparison**: Compare rates across carriers
- **Cross-Sell**: Identify coverage gaps and opportunities  
- **Claims Impact**: Analyze renewal pricing impact
    """,
    version="0.2.0",
    docs_url="/docs",
    redoc_url="/redoc",
    redirect_slashes=False,
)

# Configure CORS — restrict origins in production, allow all in dev
_cors_origins_env = os.getenv("CORS_ALLOWED_ORIGINS", "")
if _cors_origins_env:
    _allowed_origins = [o.strip() for o in _cors_origins_env.split(",") if o.strip()]
else:
    # Default: permissive for local development only
    _allowed_origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include v1 routers (mock data - for backward compatibility)
app.include_router(policies.router)
app.include_router(clients.router)
app.include_router(carriers.router)
app.include_router(renewals.router)

# Include v2 routers (SQLite/SQLAlchemy - production ready)
app.include_router(policies_v2.router)
app.include_router(clients_v2.router)
app.include_router(carriers_v2.router)
app.include_router(renewals_v2.router)

# Include AI Agent router
app.include_router(agents.router)


@app.get("/")
async def root():
    """API root - returns basic info and links to documentation."""
    return {
        "name": "Insurance Broker Workbench API",
        "version": "0.2.0",
        "status": "running",
        "docs": "/docs",
        "endpoints": {
            "v1_mock_data": {
                "policies": "/api/policies",
                "clients": "/api/clients",
                "carriers": "/api/carriers",
                "renewals": "/api/renewals"
            },
            "v2_sqlite_db": {
                "policies": "/api/v2/policies",
                "clients": "/api/v2/clients",
                "carriers": "/api/v2/carriers",
                "renewals": "/api/v2/renewals"
            },
            "agents": {
                "chat": "/api/agent/chat",
                "coverage_analysis": "/api/agent/analyze/coverage",
                "claims_analysis": "/api/agent/analyze/claims",
                "quote_comparison": "/api/agent/compare/quotes",
                "opportunities": "/api/agent/opportunities",
                "high_risk_clients": "/api/agent/high-risk-clients"
            }
        },
        "note": "Use v2 endpoints for SQLite database (Azure SQL ready). Use agent endpoints for AI-powered analysis."
    }


@app.get("/health")
async def health_check():
    """Health check endpoint for monitoring."""
    from db.connection import check_db_connection
    
    db_status = await check_db_connection()
    
    return {
        "status": "healthy" if all(db_status.values()) else "degraded",
        "databases": db_status
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
