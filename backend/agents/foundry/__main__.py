"""CLI entrypoint for the BrokerWorkbench Foundry handoff workflow.

Usage::

    python -m backend.agents.foundry "Show CLI001 claims history"

Defaults to ``"Show CLI001 claims history"`` when no prompt is supplied.

This entrypoint loads ``.env`` explicitly (the Agent Framework does NOT
auto-load it), then streams workflow events to stdout for quick smoke
testing against a live MCP server + Azure OpenAI deployment.
"""
from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

# Load .env from project root before anything reads env vars.
_env_path = Path(__file__).resolve().parents[3] / ".env"
load_dotenv(_env_path)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("foundry.handoff.cli")

DEFAULT_PROMPT = "Show CLI001 claims history"


async def _run(prompt: str) -> int:
    from .handoff import build_handoff

    workflow, mcp_tool = await build_handoff()
    logger.info("Streaming workflow events for prompt: %r", prompt)

    async with mcp_tool:
        # Workflow.run(message, stream=True) returns a ResponseStream which is
        # async-iterable. Each item is a WorkflowEvent we just print.
        async for event in workflow.run(prompt, stream=True):
            print(event)

    return 0


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    prompt = " ".join(argv).strip() or DEFAULT_PROMPT
    try:
        return asyncio.run(_run(prompt))
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
