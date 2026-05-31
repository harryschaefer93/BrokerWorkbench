"""Grant SC SQL access to deployed MIs via clientId-derived SID.

Azure SQL matches the AAD token's appid claim against the SID stored on the
DB principal. For managed identities the SID MUST come from the MI's
clientId (application ID), NOT objectId. See repo memory
`/memories/repo/deployment-notes.md` for the full story.

Grants:
  - backend MI: db_datareader + db_datawriter + db_ddladmin on the whole DB
  - mcp MI:     SELECT on master_data + txn schemas (read-only tool surface)

Run from repo root with venv active:
    python scripts/grant_sc_mi_sql.py
"""
from __future__ import annotations

import asyncio
import os
import struct
import sys
import uuid
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))
sys.path.insert(0, str(REPO_ROOT))

SERVER = "sql-brokerworkbench-dev-wnwtqzj2xcdts.database.windows.net"
DATABASE = "sqldb-brokerworkbench-dev"
SQL_COPT_SS_ACCESS_TOKEN = 1256

# (mi_name, clientId, role/grant kind)
MIS = [
    (
        "id-backend-brokerworkbench-dev",
        "f2c7fc18-0fab-4367-99e4-f36c4916d713",
        "rw_full",
    ),
    (
        "id-mcp-brokerworkbench-dev",
        "ce697d1a-0c0b-4e12-9a72-85288c0f7966",
        "ro_schemas",
    ),
]


def _client_id_to_sid(client_id: str) -> str:
    """clientId UUID -> 0x-prefixed bytes_le hex (Azure SQL SID format)."""
    return "0x" + uuid.UUID(client_id).bytes_le.hex().upper()


def _token_bytes() -> bytes:
    from azure.identity import AzureCliCredential

    cred = AzureCliCredential()
    tok = cred.get_token("https://database.windows.net/.default").token
    utf16 = tok.encode("utf-16-le")
    return struct.pack("<I", len(utf16)) + utf16


def _make_grant_sql(mi_name: str, client_id: str, kind: str) -> list[str]:
    sid = _client_id_to_sid(client_id)
    drop = f"IF EXISTS (SELECT 1 FROM sys.database_principals WHERE name = N'{mi_name}') DROP USER [{mi_name}];"
    create = f"CREATE USER [{mi_name}] WITH DEFAULT_SCHEMA=[dbo], SID={sid}, TYPE=E;"
    stmts = [drop, create]
    if kind == "rw_full":
        stmts.extend([
            f"ALTER ROLE db_datareader ADD MEMBER [{mi_name}];",
            f"ALTER ROLE db_datawriter ADD MEMBER [{mi_name}];",
            f"ALTER ROLE db_ddladmin ADD MEMBER [{mi_name}];",
        ])
    elif kind == "ro_schemas":
        stmts.extend([
            f"ALTER ROLE db_datareader ADD MEMBER [{mi_name}];",
            f"GRANT SELECT ON SCHEMA::master_data TO [{mi_name}];",
            f"GRANT SELECT ON SCHEMA::txn TO [{mi_name}];",
        ])
    else:
        raise ValueError(f"unknown kind: {kind}")
    return stmts


async def main() -> int:
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    token = _token_bytes()
    odbc = (
        "Driver={ODBC Driver 18 for SQL Server};"
        f"Server={SERVER},1433;Database={DATABASE};"
        "Encrypt=yes;TrustServerCertificate=no;"
    )
    url = f"mssql+aioodbc:///?odbc_connect={odbc.replace('=', '%3D').replace(';', '%3B')}"
    engine = create_async_engine(
        url,
        connect_args={"attrs_before": {SQL_COPT_SS_ACCESS_TOKEN: token}},
    )

    try:
        async with engine.begin() as conn:
            for mi_name, client_id, kind in MIS:
                print(f"\n--- {mi_name} (SID={_client_id_to_sid(client_id)}, kind={kind}) ---")
                for stmt in _make_grant_sql(mi_name, client_id, kind):
                    print(f"  exec: {stmt[:80]}{'...' if len(stmt) > 80 else ''}")
                    await conn.execute(text(stmt))
        print("\nDONE.")
        return 0
    finally:
        await engine.dispose()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
