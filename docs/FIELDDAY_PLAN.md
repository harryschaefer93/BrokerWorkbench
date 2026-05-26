# Field Day Rearchitecture Plan

> **Goal:** Showcase "one brain, three surfaces" for Field Day — a single
> Microsoft Agent Framework agent hosted in Azure AI Foundry Agent Service,
> consuming MCP tools, surfaced through the React web workbench, Microsoft
> Teams, and **M365 Copilot** (as a custom engine agent — not Copilot Studio).

**Timebox:** 1 week
**Owner:** Harry
**Target branch:** `fieldday`

---

## TL;DR

Migrate the home-rolled triage→specialist agents to a single
**Microsoft Agent Framework** `ChatAgent` hosted in **Foundry Agent Service**,
consuming a new **MCP server** that wraps existing tools. The same agent
powers:

1. The React web app (via FastAPI thin proxy preserving SSE)
2. Microsoft Teams (via the existing Bot Framework bot)
3. **M365 Copilot** (via the **same bot**, declared as a *custom engine agent*
   in the Teams manifest's `copilotAgents` block)

No Copilot Studio. No new bot. One additional manifest section unlocks the
third surface.

---

## Target Architecture

```text
                ┌──────────────────────────────────────┐
                │  Microsoft Agent Framework ChatAgent │
                │  hosted in Foundry Agent Service     │
                │  (single persistent agent_id)        │
                └──────────────────────────────────────┘
                                ▲           ▲
              Agent Framework SDK│           │ MCP
       ┌────────────────┬───────┘           │
       │                │                   │
  FastAPI SSE       Bot Framework bot       │
       │           ┌────────┴────────┐      │
   React web    Teams chat    M365 Copilot  │
                              (custom        │
                               engine agent) │
                                             │
                                  ┌──────────┴──────────┐
                                  │  MCP Server         │
                                  │  (wraps tools.py)   │
                                  └─────────────────────┘
```

---

## Decisions (locked in)

| # | Decision | Rationale |
|---|----------|-----------|
| 1 | Microsoft Agent Framework (Python) replaces home-rolled agents | Unified successor to SK/AutoGen; first-class Foundry integration |
| 2 | Foundry Agent Service hosts the agent (persistent `agent_id`) | "Hosted in Foundry" is the demo headline |
| 3 | Standalone MCP server wraps existing `backend/agents/tools.py` | Trendy in 2026; demo-worthy on its own; clean separation |
| 4 | Existing Bot Framework bot serves BOTH Teams AND M365 Copilot | Custom-engine-agent pattern reuses the same endpoint |
| 5 | Web app keeps FastAPI as thin proxy (not direct browser→Foundry) | Preserves SSE UX, keeps tokens off the client |
| 6 | Single Agent Framework agent with merged prompt (not multi-agent) | Most stable Foundry pattern in week-one; multi-agent handoff is v2 |

---

## Phases

### Phase A — Foundation (Days 1–2)

1. **MCP server** — new `mcp_server/` directory using `fastmcp` or the
   `modelcontextprotocol` Python SDK. Wraps the 9 existing tool functions
   in [`backend/agents/tools.py`](../backend/agents/tools.py). Deploy as
   its own Container App.
2. **Agent Framework agent** — single `ChatAgent`
   (`agent-framework[azure-ai]`) with a merged system prompt covering
   triage + claims + crosssell + quote behavior. Intent routing happens
   *inside* the prompt, eliminating the current extra classifier round-trip.
3. **Foundry hosting** — register as a persistent Foundry Agent Service
   agent; lock `FOUNDRY_AGENT_ID` into env. Wire the MCP server as an
   `MCPStreamableHTTPTool` on the agent.

### Phase B — Web migration (Day 2–3) — *depends on A*

4. Rewrite `_stream_agent` in [`backend/routers/agents.py`](../backend/routers/agents.py)
   to delegate to the Foundry agent via Agent Framework SDK,
   **preserving the SSE `status` / `token` / `done` event shape** so the
   React UI stays untouched.
5. **Multi-turn** — map web `conversation_id` ↔ Foundry `thread_id`;
   persist `thread_id` in `localStorage` from `useChat` in
   [`frontend-react/src/hooks/useApi.ts`](../frontend-react/src/hooks/useApi.ts).

### Phase C — Teams + M365 Copilot (Days 3–4) — *depends on A; parallel with B*

6. Rewrite [`bot/bot.py`](../bot/bot.py) `_call_backend` to call the
   Foundry agent directly via SDK (drops the httpx proxy back to FastAPI).
   Reuse `card_formatter` for Adaptive Cards.
7. Update [`bot/teams-manifest/manifest.json`](../bot/teams-manifest/manifest.json)
   to schema 1.20+ and add the `copilotAgents.customEngineAgents[]` block.
   **This is the single manifest change that surfaces the same bot inside
   M365 Copilot's "Agents" pane.**
8. Add Bot Framework `StreamingResponse` activities so the agent streams
   *inside* M365 Copilot, not just at-end.
9. Repackage `bot/BrokerWorkbench-Bot.zip` and sideload; verify the agent
   appears for the user in M365 Copilot.

### Phase D — Demo polish (Day 5)

10. **"What just happened" trace panel** — render Foundry run-steps
    (tool name, args, latency) under each web answer using the
    existing SSE `status` events.
11. **Seed data uplift** — generate 50 clients / 200 policies / realistic
    claims via a one-time script callable as an MCP tool.
12. Diagram refresh (3 surfaces → 1 Foundry agent → MCP), backup demo
    video, three-surface rehearsal script.

---

## Files affected

| Area | File | Change |
|------|------|--------|
| Agents | `backend/agents/triage_agent.py`, `claims_agent.py`, `crosssell_agent.py`, `quote_agent.py` | Replace with single `backend/agents/foundry_agent.py` using Agent Framework |
| Tools | `backend/agents/tools.py` | Keep function bodies; rewrap in `mcp_server/server.py` |
| MCP | `mcp_server/` *(new)* | New directory + `Dockerfile` |
| Router | `backend/routers/agents.py` | `_stream_agent` becomes thin Foundry SDK call preserving SSE shape |
| Bot | `bot/bot.py` | `_call_backend` → direct Foundry SDK call; add streaming activity support |
| Bot manifest | `bot/teams-manifest/manifest.json` | Schema 1.20+, add `copilotAgents.customEngineAgents[]` |
| Infra | `infra/main.bicep` | MCP server Container App + `Azure AI User` RBAC for bot/backend MIs on the Foundry project |
| Web | `frontend-react/src/hooks/useApi.ts` | Persist `thread_id` in `localStorage` |
| Web | `frontend-react/src/components/chat/AIChatPanel.tsx` | Collapsible run-steps trace panel |

---

## Verification

1. `mcp inspect` against the MCP server returns all 9 tools with correct schemas.
2. Foundry portal: create a thread, send "Show CLI001 claims history", confirm
   tool calls appear in run steps.
3. **Web:** ask "claims impact for CLI001" → SSE streams token-by-token,
   trace panel shows `get_client_info` → `get_claims_history` →
   `get_loss_ratio_trend` calls.
4. **Teams (personal chat):** same prompt returns identical Adaptive Card content.
5. **M365 Copilot:** agent visible in agents pane, same prompt streams,
   follow-up suggestions render.
6. App Insights: query confirms all 3 surfaces hit the same `agent_id`.

---

## Risks / Open Items

| # | Risk | Mitigation |
|---|------|-----------|
| 1 | M365 Copilot license required on demo tenant for Phase C | Confirm Day 1 on `@microsoft.com` tenant. Fallback: demo Phase C in Teams personal chat only. |
| 2 | Streaming in M365 Copilot custom engine agents is preview — some renderers may show only final reply | Build with `StreamingResponse`; rehearse a non-streamed fallback. |
| 3 | MCP tool support in Foundry Agent Service is preview | Fallback: register the MCP server's REST surface as an OpenAPI tool on the agent (one config change, same backend). |
| 4 | Single-agent collapse may lose specialist nuance | Specialist behavior moves into prompt sections gated by intent classification *inside* the system prompt. If quality regresses, fall back to Agent Framework handoff orchestration (v2, ~+1 day). |

---

## Out of scope for the week

- Retiring the v1 mock routers (still wired; harmless)
- Cosmos/Redis-backed conversation state (in-memory is fine for demo)
- Full Azure SQL path (SQLite continues to back the MCP tools)
- GitHub Actions CI/CD for ACR build + Container App update
- Playwright smoke test for nginx caching regressions
