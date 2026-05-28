"""Claims specialist agent builder.

Instructions loaded verbatim from ``AGENT_CONFIGS["claims_impact"]``.
"""
from __future__ import annotations

from agents.config import AGENT_CONFIGS


def build_claims_agent(chat_client, mcp_tool):
    """Return the Claims :class:`agent_framework.Agent`."""
    from agent_framework import Agent

    cfg = AGENT_CONFIGS["claims_impact"]
    return Agent(
        chat_client,
        cfg["instructions"],
        name="Claims",
        description=cfg["description"],
        tools=mcp_tool,
        require_per_service_call_history_persistence=True,
    )
