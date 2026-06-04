# Sweden Central migration + Foundry Hosted Agent + automated verification

Closes the Field Day rearchitecture: collapses the dual-region setup into a single Sweden Central stack, ships the Microsoft Agent Framework handoff workflow as a real Foundry Hosted Agent (`brokerworkbench` v5), wires the FastAPI backend as a thin proxy that maps Foundry's OpenAI Responses SSE to our 5+2 frame UI contract, and adds automated verification (eval harness + Playwright e2e + single `verify_all.py` orchestrator).

## What's live

- **`rg-bwbench-sc` in Sweden Central**: SQL (7 carriers / 50 clients / 187 policies / 334 claims), ACR, ACA env, Foundry account with `gpt-5` + `gpt-5-mini` GlobalStandard, Key Vault, App Insights, 3 Container Apps (backend / frontend / mcp), MCP server with external ingress + clientId-derived SID SQL grants.
- **Foundry Hosted Agent** `brokerworkbench` v5 ACTIVE. `agent-framework-foundry-hosting.ResponsesHostServer` wraps the existing `HandoffBuilder` workflow.
- **Backend proxy mode** (`AGENT_BACKEND_MODE=hosted`): translates Foundry `response.output_*` events to our `token` / `routing` / `tool_call` / `tool_result` / `done` frames. Frontend + bot are mode-transparent.
- **Bot** (`broker-bot:sc-v1`) deployed to existing westus2 ACA with `BACKEND_URL` pointing at SC.

## What was deleted

- `backend/agents/{tools,triage_agent,claims_agent,quote_agent,crosssell_agent}.py`
- `backend/services/renewal_tracker.py`
- `backend/data/mock_data.py`
- `backend/routers/{policies,clients,carriers,renewals,agents}.py` (v1)

The MCP server (already SQL-bound) is now the sole tool path. Frontend repointed to `/api/v2/*` with shape adapters in `useApi.ts`.

## Verification (all automated)

| Check | Result |
|---|---|
| `pytest tests/ -q` | 55 passed |
| `pytest -m live tests/eval/` (5 canonical prompts vs hosted) | 5/5 passed |
| `cd tests/e2e && npx playwright test tests/chat.spec.ts` | passed against live SC frontend |
| `python tests/verify_all.py` | single-command demo-readiness |

Eval snapshots committed under `tests/eval/snapshots/`.

## Known issue (carry to next PR)

- **DirectLine bot parity test fails with "bot timed out"**. Bot is reachable + healthy externally; bot endpoint correctly rejects unauth requests with auth errors. But DirectLine -> bot forwarding fails before any request reaches `/api/messages`. Likely Bot Framework auth/forwarding config (SingleTenant + tenant ID mismatch?). Test file at `tests/verify/test_bot_directline.py` is ready to re-run once resolved. Does not block the web + Foundry portal demo path.

## Commits

- `d5d8c01` D7 demolition (delete mock-data stack)
- `e23f8d3` SC Bicep + hosted-agent container + proxy mode
- `0fc7d57` seed + MI grant scripts
- `4cab1a6` hosted agent v5 live in Foundry (FoundryChatClient was the unlock)
- `c0704de` hosted proxy emits full Foundry event vocabulary + eval 5/5 + manifest 1.20
- `215094d` Playwright e2e passes against live SC frontend
- `ab92264` `verify_all.py` orchestrator + DirectLine test + README architecture diagram
- BRIEF.md updated in this PR
