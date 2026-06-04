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
import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware

# SQL-backed routers (Azure SQL via SQLAlchemy; SQLite for local dev)
from routers import policies_v2, clients_v2, carriers_v2, renewals_v2

# AI Agent handoff router — Microsoft Agent Framework HandoffBuilder over MCP tools
from routers import agents_handoff

# ─── Azure Monitor / OpenTelemetry ─────────────────────────────────────────
_ai_conn = os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING", "").strip()
_ai_enabled = False
if _ai_conn:
    os.environ.setdefault("OTEL_SERVICE_NAME", "backend")
    try:
        from azure.monitor.opentelemetry import configure_azure_monitor
        configure_azure_monitor(connection_string=_ai_conn)
        _ai_enabled = True
        logging.getLogger(__name__).warning(
            "AZMON_INIT_OK service=%s", os.environ["OTEL_SERVICE_NAME"]
        )
    except Exception as exc:  # noqa: BLE001 — telemetry must never break startup
        logging.getLogger(__name__).warning("AZMON_INIT_FAIL: %s", exc)

# ─── Agent backend mode guard ──────────────────────────────────────────────
# Prod ALWAYS runs `AGENT_BACKEND_MODE=hosted` so the backend is a thin SSE
# proxy to the Foundry hosted agent (single agent serving all 3 surfaces:
# M365 Copilot, Teams, Web). Any other value means local-mode legacy code is
# serving traffic — valid for dev only. See docs/architecture.md.
_agent_mode = os.getenv("AGENT_BACKEND_MODE", "fastapi").strip().lower()
if _agent_mode != "hosted":
    logging.getLogger(__name__).warning(
        "AGENT_BACKEND_MODE=%s — NOT 'hosted'. Prod expects 'hosted' (proxy "
        "to Foundry hosted agent). Local-mode legacy orchestration code is "
        "serving traffic. See docs/architecture.md.", _agent_mode,
    )

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

# Explicit FastAPI instrumentation — auto-detect via configure_azure_monitor
# only patches future FastAPI instances reliably when entry-point load order
# aligns; instrumenting the live app instance is always safe.
if _ai_enabled:
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        FastAPIInstrumentor.instrument_app(app)
        logging.getLogger(__name__).warning("AZMON_FASTAPI_OK")
    except Exception as exc:  # noqa: BLE001
        logging.getLogger(__name__).warning("AZMON_FASTAPI_FAIL: %s", exc)

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

# Include SQL-backed routers
app.include_router(policies_v2.router)
app.include_router(clients_v2.router)
app.include_router(carriers_v2.router)
app.include_router(renewals_v2.router)

# Include AI Agent handoff router (single chat endpoint: /api/agent/chat/handoff/stream)
app.include_router(agents_handoff.router)


# ─── Foundry hosted-agent keepalive ────────────────────────────────────────
# The hosted Foundry runtime auto-deprovisions session compute after 15 min
# idle (per https://learn.microsoft.com/azure/foundry/agents/concepts/hosted-agents).
# Cold-start can exceed the platform's 15s internal timeout → HTTP 500
# server_error before the request reaches the agent container. Ping every
# 10 min during business hours to keep at least one warm sandbox available
# for the M365 / Teams / Web surfaces.
@app.on_event("startup")
async def _start_hosted_agent_keepalive() -> None:
    import asyncio
    import httpx
    from azure.identity.aio import DefaultAzureCredential

    endpoint = os.getenv("HOSTED_AGENT_ENDPOINT", "").strip()
    if not endpoint:
        logging.getLogger(__name__).info(
            "KEEPALIVE_SKIP: HOSTED_AGENT_ENDPOINT not set"
        )
        return

    interval_seconds = int(os.getenv("HOSTED_AGENT_KEEPALIVE_SECONDS", "600"))
    log = logging.getLogger(__name__)

    async def _ping_loop() -> None:
        # Token audience for Foundry agent endpoint.
        cred = DefaultAzureCredential()
        await asyncio.sleep(30)  # Let the app finish booting before first ping.
        while True:
            try:
                token = (await cred.get_token("https://ai.azure.com/.default")).token
                async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, read=60.0)) as client:
                    r = await client.post(
                        endpoint,
                        headers={
                            "Authorization": f"Bearer {token}",
                            "Content-Type": "application/json",
                        },
                        json={
                            "model": "brokerworkbench",
                            "input": "keepalive",
                            "stream": False,
                        },
                    )
                if r.status_code == 200:
                    log.info("KEEPALIVE_OK status=200")
                else:
                    log.warning(
                        "KEEPALIVE_NON200 status=%s body=%s",
                        r.status_code, r.text[:200],
                    )
            except Exception as exc:  # noqa: BLE001 — keepalive must never break the app
                log.warning("KEEPALIVE_FAIL: %s", exc)
            await asyncio.sleep(interval_seconds)

    asyncio.create_task(_ping_loop())
    logging.getLogger(__name__).warning(
        "KEEPALIVE_STARTED endpoint=%s interval=%ss",
        endpoint.split("?")[0],
        interval_seconds,
    )


@app.get("/")
async def root():
    """API root - returns basic info and links to documentation."""
    return {
        "name": "Insurance Broker Workbench API",
        "version": "0.2.0",
        "status": "running",
        "docs": "/docs",
        "endpoints": {
            "data_v2": {
                "policies": "/api/v2/policies",
                "clients": "/api/v2/clients",
                "carriers": "/api/v2/carriers",
                "renewals": "/api/v2/renewals",
            },
            "agents": {
                "chat_stream": "/api/agent/chat/handoff/stream",
            },
        },
        "note": "All data endpoints are SQL-backed (Azure SQL / SQLite). Chat is served by the Microsoft Agent Framework handoff workflow over MCP tools.",
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
