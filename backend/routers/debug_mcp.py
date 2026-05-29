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
    from agents.foundry.handoff import InstrumentedMCPTool, DEFAULT_MCP_URL

    url = os.getenv("MCP_SERVER_URL", DEFAULT_MCP_URL)
    result: dict[str, Any] = {"mcp_url": url}

    try:
        tool = InstrumentedMCPTool(
            name="brokerworkbench",
            url=url,
            description="MCP ping probe.",
        )
        async with tool:
            funcs = await tool.functions()
            names = [getattr(f, "name", repr(f)) for f in funcs]
            result.update(
                {
                    "ok": True,
                    "function_count": len(funcs),
                    "function_names": names[:50],
                }
            )
            # Optional: call a known-cheap tool if one exists.
            cheap = next((n for n in names if "ping" in n.lower() or "health" in n.lower()), None)
            if cheap:
                try:
                    pong = await tool.call_tool(cheap)
                    result["sample_call"] = {
                        "tool": cheap,
                        "ok": True,
                        "result_repr": repr(pong)[:300],
                    }
                except Exception as ex:  # noqa: BLE001
                    result["sample_call"] = {
                        "tool": cheap,
                        "ok": False,
                        "error_type": type(ex).__name__,
                        "error": str(ex)[:300],
                    }
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
