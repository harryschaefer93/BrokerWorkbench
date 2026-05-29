"""Diagnostic probe for MCP reachability from the deployed backend.

POST /api/agent/debug/mcp_ping
    Builds the same InstrumentedMCPTool the handoff workflow uses, opens
    the connection (async with), calls `functions()` to force `load_tools`,
    and returns a structured success/failure JSON. Used to diagnose why
    `tool_call` / `tool_result` SSE frames don't appear on the
    `/api/agent/chat/handoff/stream` endpoint.

POST /api/agent/debug/grant_mcp_sql
    One-shot helper that grants the MCP managed identity read access on the
    backend SQL database. Connects to SQL using an AAD access token passed
    via the `X-Sql-Access-Token` header (caller supplies a token for the
    AAD admin). Safe to remove after the grant has been executed.
"""
from __future__ import annotations

import os
import struct
import traceback
from typing import Any
from urllib.parse import parse_qs, urlparse

from fastapi import APIRouter, Header, HTTPException

router = APIRouter(prefix="/api/agent/debug", tags=["AI Agents (Debug)"])


@router.post("/mcp_ping")
async def mcp_ping() -> dict[str, Any]:
    import asyncio

    from agents.foundry.handoff import InstrumentedMCPTool, DEFAULT_MCP_URL

    url = os.getenv("MCP_SERVER_URL", DEFAULT_MCP_URL)
    result: dict[str, Any] = {"mcp_url": url}

    try:
        tool = InstrumentedMCPTool(
            name="brokerworkbench",
            url=url,
            description="MCP ping probe.",
        )
        # Wire an event queue so we can verify the override fires.
        q: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        tool.bind_queue(q)
        async with tool:
            # `functions` is a property that returns the loaded list. It
            # may be empty before load_tools runs, so call it explicitly.
            await tool.load_tools()
            funcs = tool.functions
            names = [getattr(f, "name", repr(f)) for f in funcs]
            result.update(
                {
                    "connect_ok": True,
                    "function_count": len(funcs),
                    "function_names": names[:50],
                }
            )

            # Pick a tool we know the agents use. Falls back to first.
            preferred = next(
                (n for n in names if n in ("list_clients", "get_client", "list_carriers")),
                names[0] if names else None,
            )
            if preferred:
                try:
                    out = await tool.call_tool(preferred)
                    result["sample_call"] = {
                        "tool": preferred,
                        "ok": True,
                        "result_repr": repr(out)[:300],
                    }
                except Exception as ex:  # noqa: BLE001
                    result["sample_call"] = {
                        "tool": preferred,
                        "ok": False,
                        "error_type": type(ex).__name__,
                        "error": str(ex)[:300],
                    }

            # Drain the instrumentation queue — proves whether call_tool
            # override actually fires (independent of whether the inner
            # MCP call succeeded).
            events: list[dict[str, Any]] = []
            while not q.empty():
                events.append(q.get_nowait())
            result["events"] = events
            result["ok"] = True
            return result
    except Exception as ex:  # noqa: BLE001
        result.update(
            {
                "ok": False,
                "error_type": type(ex).__name__,
                "error": str(ex)[:500],
                "traceback": traceback.format_exc(limit=10)[-2000:],
            }
        )
        return result


# SQL Server-specific ODBC option for passing an AAD access token to the driver.
_SQL_COPT_SS_ACCESS_TOKEN = 1256

# MCP container app's user-assigned managed identity. Hard-coded so this
# one-shot endpoint does not need to call Graph (which the SQL server itself
# cannot reach in this environment — see the "SSL connection could not be
# established" error when CREATE USER ... FROM EXTERNAL PROVIDER tries to
# resolve the name via the SQL-server-side Graph lookup).
_MCP_MI_NAME = "id-mcp-brokerworkbench-dev"
_MCP_MI_OBJECT_ID = "ffa97d21-7d17-4451-82e7-30c96856dc70"


def _aad_object_id_to_sql_sid(object_id: str) -> str:
    """Convert an AAD object ID (GUID) into the binary SID hex string that
    Azure SQL expects for `CREATE USER ... WITH TYPE=E, SID=0x...`.

    Azure SQL stores the AAD object ID as a 16-byte SID in mixed-endian form:
    the first three GUID groups are byte-reversed, the last two are big-endian.
    """
    import uuid

    u = uuid.UUID(object_id)
    return "0x" + u.bytes_le.hex().upper()


_GRANT_SQL_STATEMENTS = [
    (
        f"CREATE USER [{_MCP_MI_NAME}] WITH TYPE = E, SID = {{SID}}, DEFAULT_SCHEMA = dbo",
        "create_user",
    ),
    (
        f"ALTER ROLE db_datareader ADD MEMBER [{_MCP_MI_NAME}]",
        "add_datareader",
    ),
    (
        f"GRANT SELECT ON SCHEMA::master_data TO [{_MCP_MI_NAME}]",
        "grant_master_data",
    ),
    (
        f"GRANT SELECT ON SCHEMA::txn TO [{_MCP_MI_NAME}]",
        "grant_txn",
    ),
]


def _server_db_from_url(url: str) -> tuple[str, int, str]:
    parsed = urlparse(url)
    server = parsed.hostname or ""
    port = parsed.port or 1433
    database = (parsed.path or "").lstrip("/")
    return server, port, database


def _odbc_dsn_for_token(url: str) -> str:
    """Build a DSN-less ODBC connection string with NO authentication keywords
    (auth is supplied via SQL_COPT_SS_ACCESS_TOKEN)."""
    server, port, database = _server_db_from_url(url)
    parsed_query = urlparse(url).query
    driver_clause = "Driver={ODBC Driver 18 for SQL Server}"
    for key, values in parse_qs(parsed_query).items():
        if key.lower() == "driver":
            driver_clause = f"Driver={{{values[0].replace('+', ' ')}}}"
            break
    return ";".join(
        [
            driver_clause,
            f"Server={server},{port}",
            f"Database={database}",
            "Encrypt=yes",
            "TrustServerCertificate=no",
            "Connection Timeout=30",
        ]
    )


@router.post("/grant_mcp_sql")
async def grant_mcp_sql(
    x_sql_access_token: str = Header(..., alias="X-Sql-Access-Token"),
) -> dict[str, Any]:
    """Run the T-SQL grant statements against the backend's SQL database
    using a caller-supplied AAD access token. Caller must be a SQL principal
    with permission to create users (typically the AAD admin).
    """
    db_url = os.getenv("DATABASE_URL", "")
    if not db_url.startswith("mssql"):
        raise HTTPException(400, "DATABASE_URL is not an Azure SQL connection")

    try:
        import pyodbc  # type: ignore
    except ImportError as ex:
        raise HTTPException(500, f"pyodbc not installed: {ex}") from ex

    dsn = _odbc_dsn_for_token(db_url)
    server, _, database = _server_db_from_url(db_url)

    # SQL Server expects the access token packed as: 4-byte LE length,
    # then the UTF-16-LE encoded token bytes.
    token_utf16 = x_sql_access_token.encode("utf-16-le")
    token_struct = struct.pack(f"<I{len(token_utf16)}s", len(token_utf16), token_utf16)

    statements: list[dict[str, Any]] = []
    connect_ok = False
    overall_ok = True
    sid_hex = _aad_object_id_to_sql_sid(_MCP_MI_OBJECT_ID)
    try:
        # pyodbc connect is sync; this endpoint is rare so we run inline.
        conn = pyodbc.connect(dsn, attrs_before={_SQL_COPT_SS_ACCESS_TOKEN: token_struct})
        connect_ok = True
        conn.autocommit = True
        cursor = conn.cursor()
        for sql_template, key in _GRANT_SQL_STATEMENTS:
            sql = sql_template.replace("{SID}", sid_hex)
            try:
                cursor.execute(sql)
                statements.append({"key": key, "ok": True})
            except Exception as ex:  # noqa: BLE001
                msg = str(ex)
                # "User already exists" or "is already a member" are non-fatal.
                already = any(
                    needle in msg
                    for needle in (
                        "already exists",
                        "is already a member",
                        "15023",  # user already exists
                    )
                )
                statements.append(
                    {
                        "key": key,
                        "ok": already,
                        "error": msg[:400],
                        "already_exists": already,
                    }
                )
                if not already:
                    overall_ok = False
        cursor.close()
        conn.close()
    except Exception as ex:  # noqa: BLE001
        return {
            "ok": False,
            "connect_ok": connect_ok,
            "server": server,
            "database": database,
            "error_type": type(ex).__name__,
            "error": str(ex)[:500],
            "traceback": traceback.format_exc(limit=10)[-2000:],
            "statements": statements,
        }

    return {
        "ok": overall_ok,
        "connect_ok": True,
        "server": server,
        "database": database,
        "statements": statements,
    }
