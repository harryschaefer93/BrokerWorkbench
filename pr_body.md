## Summary
Fixes broken MCP-to-Azure-SQL authentication and ships a clean `broker-backend:phasec` image without the transient one-shot debug router.

## Root cause
Azure SQL matches the AAD token's `appid` claim against the SID stored on the database principal. For **managed identities** the SID must be derived from the MI's **clientId** (application ID), not its objectId. The MCP container's MI had been provisioned with an objectId-derived SID, so its user existed in `sys.database_principals` but never matched incoming tokens, producing `Login failed for user '<token-identified principal>'` (pyodbc 28000) on every SQL-hitting tool call.

## Fix
- Re-created the SQL principal for `id-mcp-brokerworkbench-dev` with the **clientId-derived** SID `0x4243155F25AB7A409330AE757334436A` (from clientId `5f154342-ab25-407a-9330-ae757334436a`).
- Granted `db_datareader` plus `SELECT` on schemas `master_data` and `txn`.
- Removed the transient one-shot grant router (`backend/routers/debug_mcp.py`) before a public-facing build.
- Re-built and re-deployed backend as `broker-backend:phasec`.
- Bumped `infra/main.bicepparam` so subsequent Bicep deployments don't roll back the image tag.
- Hardened `.gitignore` against ad-hoc Azure REST / diagnostic scratch dumps at the repo root.

## Validation
- `/health` reports `transactional:true, master:true`.
- Debug routes confirmed 404 (`/api/agent/debug/grant_mcp_sql`, `/api/agent/debug/mcp_ping`).
- Smoke matrix across all 4 chat agents on the new revision (`--phasec`):
  - **triage**: 5 tool_call / 5 tool_result, 1 transient TCP `08S01` (agent self-retried OK)
  - **crosssell**: 3/3 ok
  - **quote**: 5/5 ok
  - **claims**: 2/2 ok
  - **zero pyodbc 28000 / Login-failed errors** across all runs

## Files
- `backend/main.py` \u2014 removed debug router import + include
- `backend/routers/debug_mcp.py` \u2014 deleted (purpose served)
- `infra/main.bicepparam` \u2014 `:phaseb` \u2192 `:phasec`
- `.gitignore` \u2014 added `qa*.txt` and root-level `*.json` / `*.txt` / `*.tar.gz` scratch ignores

## Follow-ups (out of scope)
- MCP `sql-connection-string` secret already normalized to `Authentication=ActiveDirectoryDefault` (matches backend; runtime appends UID from `AZURE_CLIENT_ID` env).
- Gotchas captured in repo memory `/memories/repo/deployment-notes.md`.