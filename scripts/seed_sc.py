"""One-shot SC SQL seeder using az CLI access token.

Bypasses the production connection.py auth rewriting (which forces
ActiveDirectoryMsi) by:
  1. Pulling a bearer token via `AzureCliCredential` for the SQL data plane scope.
  2. Building aioodbc engines with `attrs_before={1256: token_struct}` (the
     SQL_COPT_SS_ACCESS_TOKEN OLE DB attribute).
  3. Monkey-patching `backend.db.connection.engine`, `master_engine`,
     `AsyncSessionLocal`, `MasterAsyncSessionLocal` BEFORE importing the
     seed module so all downstream queries go through the patched engines.

Run from repo root with venv active:
    python scripts/seed_sc.py --reseed
"""
from __future__ import annotations

import argparse
import asyncio
import os
import struct
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
# Repo root must come BEFORE backend/ so `import data.seed` resolves to the
# workspace-root data/ package, not the empty backend/data/ shadow.
sys.path.insert(0, str(REPO_ROOT / "backend"))
sys.path.insert(0, str(REPO_ROOT))


SERVER_FQDN = (
    os.environ.get("SC_SQL_SERVER")
    or "sql-brokerworkbench-dev-wnwtqzj2xcdts.database.windows.net"
)
DATABASE = os.environ.get("SC_SQL_DATABASE", "sqldb-brokerworkbench-dev")


def _build_odbc(server: str, database: str) -> str:
    return (
        "Driver={ODBC Driver 18 for SQL Server};"
        f"Server={server},1433;"
        f"Database={database};"
        "Encrypt=yes;TrustServerCertificate=no;"
    )


def _token_bytes() -> bytes:
    """Pack an Entra token as the pyodbc SQL_COPT_SS_ACCESS_TOKEN expects."""
    from azure.identity import AzureCliCredential

    cred = AzureCliCredential()
    tok = cred.get_token("https://database.windows.net/.default").token
    utf16 = tok.encode("utf-16-le")
    return struct.pack("<I", len(utf16)) + utf16


SQL_COPT_SS_ACCESS_TOKEN = 1256


def _patch_connection() -> None:
    """Replace the engines in backend.db.connection with token-auth engines."""
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    token = _token_bytes()
    odbc = _build_odbc(SERVER_FQDN, DATABASE)
    url = f"mssql+aioodbc:///?odbc_connect={odbc.replace('=', '%3D').replace(';', '%3B')}"

    def _connect_args():
        return {"attrs_before": {SQL_COPT_SS_ACCESS_TOKEN: token}}

    # Build the engine for the single SC DB (master + txn schemas both live here).
    engine = create_async_engine(
        url,
        connect_args=_connect_args(),
        pool_pre_ping=True,
    )

    # Override the module's globals BEFORE seed imports anything.
    import backend.db.connection as conn  # noqa: WPS433

    conn.engine = engine
    conn.master_engine = engine
    conn.AsyncSessionLocal = async_sessionmaker(
        engine, expire_on_commit=False, class_=conn.AsyncSession
    )
    conn.MasterAsyncSessionLocal = async_sessionmaker(
        engine, expire_on_commit=False, class_=conn.AsyncSession
    )
    # Force the IS_AZURE_SQL flag so the seed code takes the Azure SQL path.
    conn.IS_AZURE_SQL = True


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reseed", action="store_true")
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()

    _patch_connection()

    # Azure SQL: ensure the schemas exist before create_all (SQLAlchemy
    # doesn't auto-create schemas, only tables within them).
    from sqlalchemy import text  # noqa: WPS433
    import backend.db.connection as conn
    from backend.db.models import Base  # noqa: WPS433

    async with conn.engine.begin() as raw:
        for schema in ("master_data", "txn"):
            await raw.execute(
                text(
                    f"IF NOT EXISTS (SELECT * FROM sys.schemas WHERE name = N'{schema}') "
                    f"EXEC('CREATE SCHEMA [{schema}]')"
                )
            )
        # Create all tables now while we have an open connection.
        await raw.run_sync(Base.metadata.create_all)
        # Verify
        result = await raw.execute(
            text(
                "SELECT TABLE_SCHEMA, TABLE_NAME FROM INFORMATION_SCHEMA.TABLES "
                "WHERE TABLE_SCHEMA IN ('master_data', 'txn') ORDER BY TABLE_SCHEMA, TABLE_NAME"
            )
        )
        rows = result.all()
        print(f"Tables in master_data + txn schemas ({len(rows)}):")
        for r in rows:
            print(f"  {r[0]}.{r[1]}")

    # Now import + run the seed.
    from data.seed import setup as seed_mod  # noqa: WPS433

    for attr in ("AsyncSessionLocal", "MasterAsyncSessionLocal", "engine", "master_engine", "IS_AZURE_SQL"):
        setattr(seed_mod, attr, getattr(conn, attr))

    return await seed_mod._run(args)


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
