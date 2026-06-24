"""Triage specialist agent builder.

The triage agent is the start agent of the handoff workflow. Instructions are
loaded verbatim from :data:`backend.agents.config.AGENT_CONFIGS` (key
``"triage"``) so prompt content stays in a single canonical location.
"""
from __future__ import annotations

from agents.config import AGENT_CONFIGS


def build_triage_agent(chat_client, mcp_tool):
    """Return the Triage :class:`agent_framework.Agent` wired with the MCP tool."""
    from agent_framework import Agent

    cfg = AGENT_CONFIGS["triage"]
    return Agent(
        chat_client,
        cfg["instructions"],
        name="Triage",
        description=cfg["description"],
        tools=mcp_tool,
        # Required by HandoffBuilder.build() so local history stays consistent
        # with the service across handoff tool-call short-circuits.
        require_per_service_call_history_persistence=True,
    )
