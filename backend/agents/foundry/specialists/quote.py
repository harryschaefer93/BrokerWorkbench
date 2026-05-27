"""Quote specialist agent builder.

Instructions loaded verbatim from ``AGENT_CONFIGS["quote_comparison"]``.
"""
from __future__ import annotations

from backend.agents.config import AGENT_CONFIGS


def build_quote_agent(chat_client, mcp_tool):
    """Return the Quote :class:`agent_framework.Agent`."""
    from agent_framework import Agent

    cfg = AGENT_CONFIGS["quote_comparison"]
    return Agent(
        chat_client,
        cfg["instructions"],
        name="Quote",
        description=cfg["description"],
        tools=mcp_tool,
        require_per_service_call_history_persistence=True,
    )
