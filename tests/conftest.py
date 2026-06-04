"""
Shared pytest fixtures for the BrokerWorkbench test suite.

Responsibilities:
- Set sensible default DB env vars (SQLite under data/db/) before anything imports
  the backend's db.connection module.
- Seed the DB once per session via ``python -m data.seed.setup --reseed``.
- Boot the MCP server (``python -m mcp_server.server``) on a free port in a
  subprocess and tear it down at session end.
- Expose ``mcp_session`` fixture: a zero-arg factory that returns a fresh
  ``open_mcp_session(url)`` async context manager bound to the live server.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator

import pytest

# ── Bootstrap ─────────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).resolve().parents[1]

# Ensure repo root + backend/ are importable even when pytest is invoked from
# an unusual cwd. (pytest.ini also sets pythonpath but be defensive.)
for p in (REPO_ROOT, REPO_ROOT / "backend"):
    sp = str(p)
    if sp not in sys.path:
        sys.path.insert(0, sp)

# Default DB env to local SQLite files under data/db/ if the user hasn't set
# anything. This MUST happen before any backend.db.* import.
_DB_DIR = REPO_ROOT / "data" / "db"
_DB_DIR.mkdir(parents=True, exist_ok=True)
os.environ.setdefault(
    "DATABASE_URL",
    f"sqlite+aiosqlite:///{(_DB_DIR / 'transactional_data.db').as_posix()}",
)
os.environ.setdefault(
    "MASTER_DATABASE_URL",
    f"sqlite+aiosqlite:///{(_DB_DIR / 'master_data.db').as_posix()}",
)


# ── Helpers ───────────────────────────────────────────────────────────


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _wait_for_mcp(url: str, timeout: float = 15.0) -> None:
    """Poll the MCP endpoint until the server responds (any HTTP status counts).

    FastMCP's streamable-http transport rejects bare GETs with 4xx, which still
    proves the server is alive and routing — exactly what we need.
    """
    deadline = time.monotonic() + timeout
    last_err: Exception | None = None
    while time.monotonic() < deadline:
        try:
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=1.0) as resp:
                resp.read()
                return
        except urllib.error.HTTPError as e:
            # Any HTTP response = server is up and accepting connections.
            if e.code < 500:
                return
            last_err = e
        except (urllib.error.URLError, ConnectionError, OSError) as e:
            last_err = e
        time.sleep(0.2)
    raise RuntimeError(f"MCP server at {url} did not become ready: {last_err!r}")


# ── Session fixtures ──────────────────────────────────────────────────


@pytest.fixture(scope="session")
def seeded_db() -> bool:
    """Run the seed loader once per session. Idempotent: --reseed wipes + reloads."""
    env = {**os.environ}
    result = subprocess.run(
        [sys.executable, "-m", "data.seed.setup", "--reseed"],
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"Seeder failed (rc={result.returncode}):\n"
            f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
        )
    return True


@pytest.fixture(scope="session")
def mcp_server_url(seeded_db: bool, tmp_path_factory: pytest.TempPathFactory) -> Any:
    """Boot mcp_server.server in a subprocess on a free port; yield its /mcp URL.

    Server stdout/stderr is redirected to a temp log file (not a pipe) so the
    OS pipe buffer can't fill up and deadlock the server after many requests.
    """
    port = _find_free_port()
    env = {**os.environ, "PORT": str(port), "MCP_HOST": "127.0.0.1"}
    log_path = tmp_path_factory.mktemp("mcp") / "server.log"
    log_fh = open(log_path, "w", encoding="utf-8")
    proc = subprocess.Popen(
        [sys.executable, "-m", "mcp_server.server"],
        cwd=str(REPO_ROOT),
        env=env,
        stdout=log_fh,
        stderr=subprocess.STDOUT,
    )
    url = f"http://127.0.0.1:{port}/mcp"
    try:
        try:
            _wait_for_mcp(url, timeout=20.0)
        except Exception:
            try:
                proc.terminate()
                proc.wait(timeout=3)
            except Exception:
                pass
            log_fh.close()
            log_text = log_path.read_text(encoding="utf-8", errors="replace")
            raise RuntimeError(
                f"MCP server failed to start. Subprocess output:\n{log_text}"
            )
        yield url
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=3)
        try:
            log_fh.close()
        except Exception:
            pass


# ── MCP client helper ─────────────────────────────────────────────────


@asynccontextmanager
async def open_mcp_session(url: str) -> AsyncIterator[Any]:
    """Open + initialize an MCP ClientSession against the live server URL."""
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    async with streamablehttp_client(url) as (read, write, _get_session_id):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield session


@pytest.fixture
def mcp_session(mcp_server_url: str):
    """Returns a zero-arg factory that yields a fresh ``open_mcp_session(url)``
    async context manager. Tests should use it as::

        async def test_x(mcp_session):
            async with mcp_session() as client:
                ...

    Setup and teardown of the MCP streams must happen inside the same task,
    so the session is opened inline in the test body rather than pre-injected
    by an async fixture (anyio cancel scopes are task-bound and break under
    pytest-asyncio's separate-task finalizer).
    """
    def _factory():
        return open_mcp_session(mcp_server_url)
    return _factory


# ── Result parsing helper ─────────────────────────────────────────────


def tool_result(result: Any) -> Any:
    """Normalize a FastMCP CallToolResult into the underlying Python value.

    FastMCP returns dict tools as ``structuredContent`` (a dict), and list-returning
    tools as ``structuredContent = {"result": [...]}`` plus a JSON text content
    block. This helper hides that asymmetry.
    """
    sc = getattr(result, "structuredContent", None)
    if sc is not None:
        if isinstance(sc, dict) and set(sc.keys()) == {"result"}:
            return sc["result"]
        return sc
    # Fallback: parse JSON from text content blocks.
    parts = getattr(result, "content", None) or []
    text = "".join(getattr(p, "text", "") for p in parts)
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text
