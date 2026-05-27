# Field Day Rearchitecture Plan

> **Goal:** Showcase "one brain, three surfaces" for Field Day — a Microsoft
> Agent Framework multi-agent system packaged as a **Hosted agent** in Azure
> AI Foundry Agent Service, consuming MCP tools, surfaced through the React
> web workbench, Microsoft Teams, and **M365 Copilot** (as a custom engine
> agent — not Copilot Studio).

**Timebox:** 1 week
**Owner:** Harry
**Target branch:** `fieldday`

> **2026-05-27 update — Decision #6 reversed.** Previous plan was a single
> merged `ChatAgent`. MS Learn research confirmed Foundry Agent Service
> first-class supports multi-agent via three patterns: **Workflow agents**
> (preview), **Hosted agents** (preview), and **A2A tool** for prompt agents.
> Selected: **Path B — Hosted agent containing Agent Framework handoff
> orchestration of 4 specialists.** See [Decision #6](#decisions-locked-in)
> and [Phase A](#phase-a--foundation-days-12) for the full pivot.

---

## TL;DR

Replace the home-rolled triage→specialist agents with a **Microsoft Agent
Framework handoff orchestration** of 4 specialist `ChatAgent`s (triage,
claims, quote, crosssell), packaged as a single container and deployed to
**Foundry Agent Service as a Hosted agent (preview)**. The hosted agent
exposes the **Responses protocol**, consumes a new **MCP server** that wraps
existing tools, and powers:

1. The React web app (via FastAPI thin proxy preserving SSE)
2. Microsoft Teams (via the existing Bot Framework bot — platform auto-bridges
   Responses → Activity)
3. **M365 Copilot** (via the **same bot**, declared as a *custom engine agent*
   in the Teams manifest's `copilotAgents` block)

No Copilot Studio. No new bot. One additional manifest section unlocks the
third surface.

---

## Target Architecture

```text
          ┌────────────────────────────────────────────────────┐
          │  Foundry Agent Service — Hosted agent (preview)    │
          │  ┌──────────────────────────────────────────────┐  │
          │  │  Agent Framework Handoff Orchestration       │  │
          │  │  ┌─────────┐  hands off to ┌─────────────┐   │  │
          │  │  │ Triage  │──────────────►│ Claims      │   │  │
          │  │  │ (entry) │──────────────►│ Quote       │   │  │
          │  │  └─────────┘──────────────►│ CrossSell   │   │  │
          │  │                            └─────────────┘   │  │
          │  └──────────────────────────────────────────────┘  │
          │  Responses protocol  ·  per-agent Entra identity   │
          └────────────────────────────────────────────────────┘
                       ▲                        ▲
            OpenAI-compatible                   │ MCP
              Responses SDK                     │
         ┌──────────┴──────────┐                │
         │                     │                │
    FastAPI SSE          Bot Framework bot      │
         │            ┌────────┴────────┐       │
     React web     Teams chat    M365 Copilot   │
                                (custom         │
                                 engine agent)  │
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
| 6 | **Agent Framework handoff orchestration of 4 specialists, packaged as a Foundry Hosted agent (preview)** | Keeps specialist personalities + Foundry-hosted headline. MS Learn confirms Hosted agents support custom orchestration including multi-agent. Alternative paths (Workflow agents YAML, A2A tool) documented but not chosen. See [Decision #6 rationale](#decision-6-rationale-path-b). |

---

## Decision #6 rationale (Path B)

Four Foundry-hosted multi-agent paths were considered. Trade-offs:

| Path | Pattern | Foundry-hosted | Specialists kept | Effort | Preview risk | Verdict |
|------|---------|----------------|------------------|--------|--------------|---------|
| Single merged ChatAgent (original plan) | Prompt agent | ✅ | ❌ (merged prompt) | baseline | low | rejected — loses specialist clarity |
| **A — Workflow agents** | Declarative YAML/visual | ✅ | ✅ | +2 days | **preview** | strong, but YAML authoring effort high |
| **B — Hosted agent + handoff (selected)** | Container with Agent Framework | ✅ | ✅ | +1 day | **preview** | **most code reuse, demos Agent Framework AND Foundry** |
| C — Prompt agents + A2A tool | 4 prompt agents, 1 main delegates | ✅ | ✅ | +1.5 days | low | coordination lives in prompts — closer to single agent that delegates |

Why Path B wins for Field Day:

- **Specialist code is reusable** — handoff orchestration uses real Python `ChatAgent` objects, so the existing triage/claims/quote/crosssell prompt content survives.
- **Two headlines for the price of one** — "Microsoft Agent Framework" AND "Foundry Agent Service Hosted agents (preview)" in the same demo.
- **A2A protocol available** — Hosted agents support A2A natively if we later want to split sub-agents into independent endpoints.
- **Observability built-in** — App Insights is auto-wired by the platform, so tool calls + handoffs are visible in the existing trace panel design.

Docs: [Hosted agents concept](https://learn.microsoft.com/azure/foundry/agents/concepts/hosted-agents) · [Agent Framework handoff orchestration](https://learn.microsoft.com/agent-framework/workflows/orchestrations/handoff)

---

## Phases

### Phase A — Foundation (Days 1–2)

1. **MCP server** — new `mcp_server/` directory using `fastmcp` or the
   `modelcontextprotocol` Python SDK. Wraps the existing tool functions
   in [`backend/agents/tools.py`](../backend/agents/tools.py). Deploy as
   its own Container App. *(Sub-step 1 — in progress on the fieldday branch.)*
2. **Agent Framework handoff orchestration** — under `backend/agents/foundry/`,
   four specialist `ChatAgent`s (triage, claims, quote, crosssell) sharing the
   same `AzureAIChatClient` and the MCP server's tool set. Triage is the entry
   agent; it hands off to claims/quote/crosssell based on intent. Implemented
   with `agent-framework[azure-ai]` handoff workflow. Specialist prompt
   content is migrated from the existing files — no merged super-prompt.
3. **Foundry Hosted agent packaging** — wrap the handoff orchestration in a
   container that exposes the **Responses protocol** via
   `azure-ai-agents-protocols-responses` (or equivalent). Define `agent.yaml`
   with container image, env vars (`AZURE_AI_FOUNDRY_ENDPOINT`,
   `AZURE_AI_MODEL_DEPLOYMENT`, `MCP_SERVER_URL`), CPU/memory (start 1 vCPU /
   2 GiB), and protocol declaration. Deploy via `azd` so Foundry auto-assigns
   the per-agent Entra ID and Foundry User RBAC at account scope. Lock
   `FOUNDRY_HOSTED_AGENT_NAME` into env.

### Phase B — Web migration (Day 2–3) — *depends on A*

4. Rewrite `_stream_agent` in [`backend/routers/agents.py`](../backend/routers/agents.py)
   to call the Hosted agent's **Responses endpoint** using any
   OpenAI-compatible SDK,
   **preserving the SSE `status` / `token` / `done` event shape** so the
   React UI stays untouched. Surface handoff events as `status` updates
   ("Handing off to Claims specialist…").
5. **Multi-turn** — map web `conversation_id` ↔ Hosted agent **conversation
   ID** (platform-managed); persist it in `localStorage` from `useChat` in
   [`frontend-react/src/hooks/useApi.ts`](../frontend-react/src/hooks/useApi.ts).

### Phase C — Teams + M365 Copilot (Days 3–4) — *depends on A; parallel with B*

6. Rewrite [`bot/bot.py`](../bot/bot.py) `_call_backend` to call the
   Hosted agent's Responses endpoint directly (drops the httpx proxy back
   to FastAPI). Reuse `card_formatter` for Adaptive Cards. Platform
   auto-bridges Responses → Activity for Teams channel delivery.
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
| Agents | `backend/agents/triage_agent.py`, `claims_agent.py`, `crosssell_agent.py`, `quote_agent.py` | **Delete.** Specialist prompts migrate into `backend/agents/foundry/specialists/{triage,claims,quote,crosssell}.py` as Agent Framework `ChatAgent`s. |
| Orchestration | `backend/agents/foundry/handoff.py` *(new)* | Agent Framework handoff workflow wiring the 4 specialists; triage as entry. |
| Hosted agent | `backend/agents/foundry/server.py` *(new)* | Container entrypoint exposing the Responses protocol; consumed by Foundry Hosted agent runtime. |
| Hosted agent | `backend/agents/foundry/Dockerfile` *(new)* | Container image for ACR push + Hosted agent deploy. |
| Hosted agent | `backend/agents/foundry/agent.yaml` *(new)* | Hosted agent manifest: image ref, env vars, CPU/memory, protocol declaration. |
| Tools | `backend/agents/tools.py` | Keep function bodies; rewrap in `mcp_server/server.py`. |
| MCP | `mcp_server/` *(new — in progress)* | New directory + `Dockerfile`. |
| Router | `backend/routers/agents.py` | `_stream_agent` becomes thin Responses-API call preserving SSE shape; surfaces handoff events as `status` updates. |
| Bot | `bot/bot.py` | `_call_backend` → direct Responses API call; add streaming activity support. |
| Bot manifest | `bot/teams-manifest/manifest.json` | Schema 1.20+, add `copilotAgents.customEngineAgents[]`. |
| Infra | `infra/main.bicep` | MCP server Container App + ACR for Hosted agent images + **Foundry User** RBAC for bot/backend MIs at account scope. |
| Web | `frontend-react/src/hooks/useApi.ts` | Persist Responses `conversation_id` in `localStorage`. |
| Web | `frontend-react/src/components/chat/AIChatPanel.tsx` | Collapsible run-steps trace panel showing handoffs + tool calls. |

---

## Verification

1. `mcp inspect` against the MCP server returns all 10 tools with correct schemas.
2. Foundry portal: Hosted agent appears under **Agents**, status = healthy,
   Responses endpoint reachable, dedicated Entra identity assigned.
3. Foundry portal: create a conversation, send "Show CLI001 claims history",
   confirm **handoff** from triage → claims appears in run steps, followed by
   MCP tool calls.
4. **Web:** ask "claims impact for CLI001" → SSE streams token-by-token,
   trace panel shows the handoff plus `get_client_info` → `get_claims_history`
   → `get_loss_ratio_trend` calls.
5. **Teams (personal chat):** same prompt returns identical Adaptive Card content.
6. **M365 Copilot:** agent visible in agents pane, same prompt streams,
   follow-up suggestions render.
7. App Insights: query confirms all 3 surfaces hit the same Hosted agent
   endpoint and trace IDs correlate handoffs across surfaces.

---

## Risks / Open Items

| # | Risk | Mitigation |
|---|------|-----------|
| 1 | M365 Copilot license required on demo tenant for Phase C | Confirm Day 1 on `@microsoft.com` tenant. Fallback: demo Phase C in Teams personal chat only. |
| 2 | Streaming in M365 Copilot custom engine agents is preview — some renderers may show only final reply | Build with `StreamingResponse`; rehearse a non-streamed fallback. |
| 3 | MCP tool support in Foundry Agent Service is preview | Fallback: register the MCP server's REST surface as an OpenAPI tool on the agent (one config change, same backend). |
| 4 | **Hosted agents are preview** — SLA-free, regional availability limits, schema may shift | Confirm `swedencentral` is in the Hosted agents preview region list before Phase A wraps. Fallback: deploy the same container to a separate Container App and have the React/bot call its Responses endpoint directly — Foundry portal loses the Hosted-agent badge but demo still works. |
| 5 | Agent Framework handoff orchestration quality may regress vs. current Python triage classifier | Smoke-test the same 5 canonical Field Day prompts that pass today against the new orchestration before Phase B begins. Fallback: tighten triage system prompt or fall back to A2A pattern (Path C). |
| 6 | Foundry User RBAC role rename in progress (was Azure AI User) | Use role ID in Bicep, not name; works under both rename states. |

---

## Out of scope for the week

- Retiring the v1 mock routers (still wired; harmless)
- Cosmos/Redis-backed conversation state (in-memory is fine for demo)
- Full Azure SQL path (SQLite continues to back the MCP tools)
- GitHub Actions CI/CD for ACR build + Container App update
- Playwright smoke test for nginx caching regressions
