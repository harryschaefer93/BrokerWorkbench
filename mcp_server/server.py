"""
Broker Workbench MCP server entrypoint.

Boots a FastMCP app exposing the broker-domain tools (defined in
`mcp_server.tools` — 10 granular + 4 composite) over the streamable-http
transport so the Foundry Agent Service `MCPStreamableHTTPTool` can
consume them.

Run locally:
    python -m mcp_server.server
Default URL:
    http://localhost:8001/mcp
"""

from __future__ import annotations

import logging
import os

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

from mcp_server.tools import register_tools

load_dotenv()

# ─── Azure Monitor / OpenTelemetry ─────────────────────────────────────────
_ai_conn = os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING", "").strip()
_ai_enabled = False
if _ai_conn:
    os.environ.setdefault("OTEL_SERVICE_NAME", "mcp")
    try:
        from azure.monitor.opentelemetry import configure_azure_monitor
        configure_azure_monitor(connection_string=_ai_conn)
        _ai_enabled = True
        logging.getLogger(__name__).warning(
            "AZMON_INIT_OK service=%s", os.environ["OTEL_SERVICE_NAME"]
        )
    except Exception as exc:  # noqa: BLE001 — telemetry must never break startup
        logging.getLogger(__name__).warning("AZMON_INIT_FAIL: %s", exc)


def build_app() -> FastMCP:
    host = os.getenv("MCP_HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8001"))
    mcp = FastMCP(
        "broker-workbench-mcp",
        instructions=(
            "Tools for the BrokerWorkbench Field Day demo: clients, "
            "policies, carriers, claims, market rates. IDs use CLI001 / "
            "POL001 / CAR001 string format on input and output."
        ),
        host=host,
        port=port,
    )
    register_tools(mcp)
    return mcp


mcp = build_app()


if __name__ == "__main__":
    if _ai_enabled:
        try:
            import uvicorn
            asgi_app = mcp.streamable_http_app()
            try:
                from opentelemetry.instrumentation.asgi import OpenTelemetryMiddleware
                asgi_app = OpenTelemetryMiddleware(asgi_app)
                logging.getLogger(__name__).warning("AZMON_ASGI_OK")
            except Exception as exc:  # noqa: BLE001
                logging.getLogger(__name__).warning("AZMON_ASGI_FAIL: %s", exc)
            host = os.getenv("MCP_HOST", "0.0.0.0")
            port = int(os.getenv("PORT", "8001"))
            uvicorn.run(asgi_app, host=host, port=port)
        except Exception as exc:  # noqa: BLE001
            logging.getLogger(__name__).warning("AZMON_UVICORN_FAIL: %s — falling back", exc)
            mcp.run(transport="streamable-http")
    else:
        mcp.run(transport="streamable-http")
