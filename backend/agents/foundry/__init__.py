"""Foundry handoff orchestration package.

Wraps the 4 BrokerWorkbench specialist agents (Triage, Claims, Quote, CrossSell)
into a single Microsoft Agent Framework :class:`HandoffBuilder` workflow that
shares a single MCP tool over the existing MCP server.

This package is orchestration code only — it does NOT package, deploy, or
rewire the FastAPI routers. Phase A sub-step 2.
"""

from .handoff import build_handoff

__all__ = ["build_handoff"]
