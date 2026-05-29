"""Diagnostic probe for MCP reachability from the deployed backend.

POST /api/agent/debug/mcp_ping
    Builds the same InstrumentedMCPTool the handoff workflow uses, opens
    the connection (async with), calls `functions()` to force `load_tools`,
    and returns a structured success/failure JSON. Used to diagnose why
    `tool_call` / `tool_result` SSE frames don't appear on the
    `/api/agent/chat/handoff/stream` endpoint.

This is intentionally lightweight: no auth, no chat client construction —
only the MCP side. Safe to leave in place; can be removed once the
underlying tool-frame issue is understood.
"""
from __future__ import annotations

import os
import traceback
from typing import Any

from fastapi import APIRouter

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
