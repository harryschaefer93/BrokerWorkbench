"""
Database connection management.
Supports SQLite (development) and Azure SQL (production) via environment variable.

SQLite (dev): Two separate databases — transactional_data.db and master_data.db.
  Schemas are mapped away via schema_translate_map so models' schema= is ignored.

Azure SQL (prod): Single database with two schemas — master_data.* and txn.*.
  Both sessions share one engine; schema-qualified table names handle separation.

Usage:
    from db.connection import get_db, get_master_db
    
    @app.get("/items")
    async def get_items(db: AsyncSession = Depends(get_db)):
        result = await db.execute(select(Item))
        return result.scalars().all()
"""

import os
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import StaticPool

from db.models import MASTER_SCHEMA, TXN_SCHEMA

# Load environment variables
load_dotenv()

# ── Helpers ───────────────────────────────────────────────────────────

def _is_mssql(url: str) -> bool:
    return url.startswith("mssql")


def _ensure_async_dialect(url: str) -> str:
    """Convert mssql+pyodbc:// to mssql+aioodbc:// for async engine compatibility.
    Also fix authentication mode for Azure Container Apps (ActiveDirectoryMsi)."""
    if url.startswith("mssql+pyodbc"):
        url = url.replace("mssql+pyodbc", "mssql+aioodbc", 1)
    # Fix auth mode: ActiveDirectoryDefault isn't supported by all ODBC driver versions
    if "ActiveDirectoryDefault" in url:
        url = url.replace("ActiveDirectoryDefault", "ActiveDirectoryMsi")
    # For MSI auth, append managed identity client ID
    if "ActiveDirectoryMsi" in url:
        client_id = os.getenv("AZURE_CLIENT_ID")
        if client_id and "UID=" not in url:
            url += f"&UID={client_id}"
    return url


def _build_odbc_connection_string(sqlalchemy_url: str) -> str | None:
    """Extract ODBC params from a mssql+aioodbc:// SQLAlchemy URL and build
    a raw DSN-less ODBC connection string.  Returns None for non-MSSQL URLs.

    This bypasses SQLAlchemy's dialect which injects 'Integrated Security=SSPI'
    when no username is present in the URL authority section."""
    if not sqlalchemy_url.startswith("mssql"):
        return None

    from urllib.parse import urlparse, parse_qs

    parsed = urlparse(sqlalchemy_url)
    server = parsed.hostname or ""
    port = parsed.port or 1433
    database = (parsed.path or "").lstrip("/")

    # Start with server/database
    parts = [
        f"Server={server},{port}",
        f"Database={database}",
    ]

    # Add all query-string params (driver, Encrypt, Authentication, UID, etc.)
    for key, values in parse_qs(parsed.query).items():
        parts.append(f"{key}={values[0]}")

    return ";".join(parts)


def get_database_url() -> str:
    """
    Get database URL from environment or default to SQLite.
    
    For development: Uses transactional_data.db (policies, quotes, claims, etc.)
    For production: Set DATABASE_URL environment variable for Azure SQL
    """
    env_url = os.getenv("DATABASE_URL")
    if env_url:
        return env_url
    
    # Default to SQLite transactional database
    project_root = Path(__file__).parent.parent.parent
    db_path = project_root / "data" / "db" / "transactional_data.db"
    return f"sqlite+aiosqlite:///{db_path}"


def get_master_database_url() -> str:
    """
    Get master database URL (carriers, clients master data, product lines, market rates).
    For Azure SQL this returns the same DATABASE_URL (single DB, different schema).
    """
    env_url = os.getenv("DATABASE_URL")
    # If Azure SQL, master data lives in the same database under master_data schema
    if env_url and _is_mssql(env_url):
        return env_url

    env_url = os.getenv("MASTER_DATABASE_URL")
    if env_url:
        return env_url
    
    project_root = Path(__file__).parent.parent.parent
    db_path = project_root / "data" / "db" / "master_data.db"
    return f"sqlite+aiosqlite:///{db_path}"


# ── Engine creation ───────────────────────────────────────────────────

DATABASE_URL = _ensure_async_dialect(get_database_url())
MASTER_DATABASE_URL = _ensure_async_dialect(get_master_database_url())

IS_AZURE_SQL = _is_mssql(DATABASE_URL)

engine_kwargs = {
    "echo": os.getenv("SQL_ECHO", "false").lower() == "true",
}

if IS_AZURE_SQL:
    # Azure SQL: single engine, schemas are real SQL Server schemas
    # Build a raw ODBC connection string to avoid SQLAlchemy injecting
    # 'Integrated Security=SSPI' (which conflicts with ActiveDirectoryMsi auth)
    _odbc_dsn = _build_odbc_connection_string(DATABASE_URL)
    if _odbc_dsn:
        engine_kwargs["connect_args"] = {"dsn": _odbc_dsn}
    engine = create_async_engine(DATABASE_URL, **engine_kwargs)
    master_engine = engine  # same engine, different schema in the models

else:
    # SQLite: two separate engines; strip schema names via schema_translate_map
    sqlite_translate_map = {MASTER_SCHEMA: None, TXN_SCHEMA: None}

    engine_kwargs["connect_args"] = {"check_same_thread": False}
    engine_kwargs["poolclass"] = StaticPool

    engine = create_async_engine(
        DATABASE_URL,
        execution_options={"schema_translate_map": sqlite_translate_map},
        **engine_kwargs,
    )

    master_engine_kwargs = engine_kwargs.copy()
    master_engine = create_async_engine(
        MASTER_DATABASE_URL,
        execution_options={"schema_translate_map": sqlite_translate_map},
        **master_engine_kwargs,
    )

# Session factories
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False
)

MasterAsyncSessionLocal = async_sessionmaker(
    bind=master_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False
)


async def get_db() -> AsyncSession:
    """
    Dependency that provides a database session.
    Use with FastAPI Depends():
    
        @app.get("/policies")
        async def get_policies(db: AsyncSession = Depends(get_db)):
            ...
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def get_master_db() -> AsyncSession:
    """
    Dependency that provides a master database session (read-only reference data).
    Use for carriers, product lines, market rates lookups.
    """
    async with MasterAsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


# Health check function
async def check_db_connection() -> dict:
    """Check if database connections are working."""
    from sqlalchemy import text
    
    status = {"transactional": False, "master": False}
    
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
            status["transactional"] = True
    except Exception as e:
        status["transactional_error"] = str(e)
    
    try:
        async with MasterAsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
            status["master"] = True
    except Exception as e:
        status["master_error"] = str(e)
    
    return status
