"""
DB session helper + ID conversion utilities for the MCP server.

Reuses the engine/session factories from `backend.db.connection` so the
MCP server and backend share one configuration surface (DATABASE_URL,
MASTER_DATABASE_URL, ODBC fix-ups, schema_translate_map, etc.).

ID convention for the agent-facing API:
    Client    "CLI001" <-> int 1
    Policy    "POL001" <-> int 1
    Carrier   "CAR001" <-> int 1
The DB itself stores ints; only the agent sees the prefixed strings so
that prompts and traces stay human-readable.
"""

from __future__ import annotations

import os
import re
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

# Make backend/ importable so `from db.connection import ...` (which is how
# the backend code addresses itself) works whether we run on the host (cwd
# is the repo root) or inside the container (Dockerfile sets PYTHONPATH).
_REPO_ROOT = Path(__file__).resolve().parent.parent
_BACKEND_DIR = _REPO_ROOT / "backend"
if _BACKEND_DIR.exists() and str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

# Reuse the backend's session factories directly — single source of truth.
from db.connection import (  # noqa: E402
    AsyncSessionLocal,
    MasterAsyncSessionLocal,
)


# ── Session helpers ───────────────────────────────────────────────────

@asynccontextmanager
async def get_session() -> AsyncIterator[AsyncSession]:
    """Async context manager yielding a transactional (txn schema) session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


@asynccontextmanager
async def get_master_session() -> AsyncIterator[AsyncSession]:
    """Async context manager yielding a master-data session."""
    async with MasterAsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


# ── ID conversion ─────────────────────────────────────────────────────

_PREFIX_RE = re.compile(r"^([A-Za-z]+)?0*(\d+)$")


def _prefix_to_int(value: str, prefix: str) -> int:
    if value is None:
        raise ValueError(f"Invalid {prefix} id: None")
    s = str(value).strip()
    if not s:
        raise ValueError(f"Invalid {prefix} id: empty")
    # Accept bare ints as strings too
    if s.isdigit():
        return int(s)
    m = _PREFIX_RE.match(s)
    if not m:
        raise ValueError(
            f"Invalid {prefix} id: {value!r} (expected e.g. '{prefix}001' or an integer)"
        )
    found_prefix, digits = m.group(1), m.group(2)
    if found_prefix and found_prefix.upper() != prefix.upper():
        raise ValueError(
            f"Invalid {prefix} id: {value!r} (prefix should be {prefix!r})"
        )
    return int(digits)


def _int_to_prefix(value: int, prefix: str) -> str:
    return f"{prefix}{int(value):03d}"


def cli_to_int(client_id: str) -> int:
    return _prefix_to_int(client_id, "CLI")


def int_to_cli(client_id: int) -> str:
    return _int_to_prefix(client_id, "CLI")


def pol_to_int(policy_id: str) -> int:
    return _prefix_to_int(policy_id, "POL")


def int_to_pol(policy_id: int) -> str:
    return _int_to_prefix(policy_id, "POL")


def carrier_to_int(carrier_id: str) -> int:
    return _prefix_to_int(carrier_id, "CAR")


def int_to_carrier(carrier_id: int) -> str:
    return _int_to_prefix(carrier_id, "CAR")
