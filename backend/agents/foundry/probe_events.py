"""One-shot probe: dump every WorkflowEvent type/executor/data repr for a single
canonical prompt, plus dir(mcp_tool) to find the tool-invocation hook.

Run inside the backend container (which has env wiring + internal MCP access):

    az containerapp exec -g rg-bwbench-sc -n ca-backend-brokerworkbench-dev \
        --command "python -m agents.foundry.probe_events"
"""
from __future__ import annotations

import asyncio
import logging
import sys

logging.basicConfig(level=logging.WARNING)

PROMPT = "Show CLI001 claims history"


async def _run() -> int:
    from .handoff import build_handoff

    workflow, mcp_tool, _tool_queue = await build_handoff()

    print("=== dir(mcp_tool) ===")
    print([m for m in dir(mcp_tool) if not m.startswith("_")])
    print("=== dir(type(mcp_tool)) ===")
    print([m for m in dir(type(mcp_tool)) if not m.startswith("_")])
    print("=== type(mcp_tool) ===", type(mcp_tool).__mro__)
    print()

    async with mcp_tool:
        # After enter: MCP session populated — re-introspect for call hooks.
        print("=== post-enter dir(mcp_tool) ===")
        print([m for m in dir(mcp_tool) if not m.startswith("_")])
        print()

        i = 0
        async for event in workflow.run(PROMPT, stream=True):
            i += 1
            ev_type = getattr(event, "type", type(event).__name__)
            executor_id = getattr(event, "executor_id", None)
            data = getattr(event, "data", None)
            data_repr = repr(data)
            if len(data_repr) > 240:
                data_repr = data_repr[:240] + "...<trunc>"
            print(f"[{i:03d}] type={ev_type!r} executor={executor_id!r} data_type={type(data).__name__} data={data_repr}")
            if i > 250:
                print("(truncating after 250 events)")
                break

    return 0


def main() -> int:
    return asyncio.run(_run())


if __name__ == "__main__":
    sys.exit(main())
