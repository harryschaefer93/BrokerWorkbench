"""
Broker Workbench MCP server entrypoint.

Boots a FastMCP app exposing the 10 broker-domain tools (defined in
`mcp_server.tools`) over the streamable-http transport so the Foundry
Agent Service `MCPStreamableHTTPTool` can consume them.

Run locally:
    python -m mcp_server.server
Default URL:
    http://localhost:8001/mcp
"""

from __future__ import annotations

import os

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

from mcp_server.tools import register_tools

load_dotenv()


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
    mcp.run(transport="streamable-http")
