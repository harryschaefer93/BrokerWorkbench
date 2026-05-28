"""CrossSell specialist agent builder.

Instructions loaded verbatim from ``AGENT_CONFIGS["cross_sell"]``.
"""
from __future__ import annotations

from agents.config import AGENT_CONFIGS


def build_crosssell_agent(chat_client, mcp_tool):
    """Return the CrossSell :class:`agent_framework.Agent`."""
    from agent_framework import Agent

    cfg = AGENT_CONFIGS["cross_sell"]
    return Agent(
        chat_client,
        cfg["instructions"],
        name="CrossSell",
        description=cfg["description"],
        tools=mcp_tool,
        require_per_service_call_history_persistence=True,
    )
