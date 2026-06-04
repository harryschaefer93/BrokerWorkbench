# BrokerWorkbench — History

> Archive of completed task tables and debug logs from the original
> `BRIEF.md` project manifest (Feb/Mar 2026) and the
> `docs/FIELDDAY_PLAN.md` rearchitecture plan. Kept for context only.
> The active source of truth is now [`BRIEF.md`](../BRIEF.md).

---

## ✅ Completed work (cumulative through May 2026)

| Task | Owner | Date | Notes |
|------|-------|------|-------|
| UI Wireframe (HTML) | Paras | Feb 2026 | Original design in `/frontend/index.html` |
| Database Schema Design | Paras | Feb 2026 | 2-tier: Master, Transactional |
| Use Cases Documentation | Team | Feb 3, 2026 | Consolidated into README.md |
| GitHub Repo Setup | Harry | Feb 3, 2026 | Connected to InsuranceHackathon repo |
| README Creation | Harry | Feb 3, 2026 | Project overview and architecture |
| FastAPI Backend Setup | Harry | Feb 4, 2026 | `/backend` folder with full project structure |
| Policy API (CRUD) | Harry | Feb 4, 2026 | Full CRUD + renewal info endpoint |
| Client API (CRUD) | Harry | Feb 4, 2026 | Full CRUD + search + policy summary |
| Carrier API (CRUD) | Harry | Feb 4, 2026 | Full CRUD + carriers by policy type |
| Renewal Tracking Service | Harry | Feb 4, 2026 | Priority scoring, urgency levels, dashboard |
| Mock Data Layer | Harry | Feb 4, 2026 | 8 carriers, 5 clients, 10 policies |
| Frontend ↔ API Integration | Harry | Feb 4, 2026 | UI wired to live API endpoints |
| SQLite Database Setup | Paras | Feb 4, 2026 | `/data/db/` — Master + Transactional DBs with seed data |
| Database ER Diagram | Paras | Feb 4, 2026 | Interactive HTML diagram in `/data/db/` |
| Database Test Suite | Paras | Feb 4, 2026 | `test_databases.py` with validation tests |
| SQLAlchemy Database Integration | Harry | Feb 4, 2026 | v2 API endpoints using SQLite via SQLAlchemy |
| AI Agents Infrastructure | Harry | Feb 4, 2026 | `/backend/agents/` with tools and 3 agents |
| Agent API Endpoints | Harry | Feb 4, 2026 | `/api/agent/*` — chat, analysis, quotes |
| Azure Container Apps Infrastructure | Harry | Feb 5, 2026 | `/infra/` — Container Apps, SQL, App Insights |
| Frontend Dockerfile | Harry | Feb 5, 2026 | nginx container for static files |
| Backend Dockerfile | Harry | Feb 5, 2026 | Python/FastAPI container with ODBC support |
| Docker Compose | Harry | Feb 5, 2026 | Local dev: `docker-compose up --build` |
| API URL Injection | Harry | Feb 5, 2026 | Frontend auto-detects backend URL |
| Resizable AI Chat Panel | Harry | Feb 6, 2026 | Drag-to-resize (280px–900px), persists in localStorage |
| Chat Clear/Refresh Button | Harry | Feb 6, 2026 | One-click chat reset with fade animation |
| Example Prompt Suggestions | Harry | Feb 6, 2026 | 4 clickable prompts: Claims, Cross-sell, Quotes, Renewals |
| Smart Response Formatting | Harry | Feb 6, 2026 | Tables, lists, urgency badges, currency highlighting |
| Clickable Follow-up Suggestions | Harry | Feb 6, 2026 | Agent responses parsed for numbered items → clickable pills |
| React Frontend Migration | Harry | Feb 7, 2026 | `/frontend-react/` — Full React 18 + TypeScript + Vite migration |
| Shadcn/ui + Tailwind CSS | Harry | Feb 7, 2026 | Modern component library with custom theming |
| Framer Motion Animations | Harry | Feb 7, 2026 | Smooth transitions, hover effects, loading states |
| Recharts Data Visualization | Harry | Feb 7, 2026 | Renewal trends, policy distribution charts |
| Unique AI Agent Avatars | Harry | Feb 7, 2026 | Distinct icons/colors per agent (Claims/Cross-sell/Quote) |
| Improved Markdown Rendering | Harry | Feb 7, 2026 | react-markdown + typography for cleaner chat responses |
| Smart Suggestion Pills | Harry | Feb 7, 2026 | Contextual follow-up suggestions from agent responses |
| Azure CLI credential chain | Harry | Mar 2, 2026 | `ChainedTokenCredential` (EnvironmentCredential → AzureCliCredential) with `~/.azure` volume mount |
| Agent auth diagnostic endpoint | Harry | Mar 2, 2026 | `GET /api/agent/health` |
| nginx WebSocket header fix | Harry | Mar 2, 2026 | `Connection: upgrade` only on real WebSockets; added `map $http_upgrade $connection_upgrade` |
| GET fallback for agent chat | Harry | Mar 2, 2026 | `GET /api/agent/chat?message=...&agent=...` for proxy-blocked environments |
| Frontend POST→GET auto-fallback | Harry | Mar 2, 2026 | `useChat` retries as GET when POST returns 401/405 (Zscaler workaround) |
| ACA first live deployment | Harry | Mar 2, 2026 | Both `broker-frontend` and `broker-backend` images running in ACA |
| ACR image naming fix | Harry | Mar 2, 2026 | Corrected image tags to `broker-frontend`/`broker-backend` |
| AcrPull RBAC grant | Harry | Mar 2, 2026 | Granted `AcrPull` to both frontend and backend MIs on the ACR |
| Dockerfile `USER nginx` removal | Harry | Mar 2, 2026 | nginx can't bind port 80 as non-root in ACA |
| API_BACKEND_URL env var | Harry | Mar 2, 2026 | nginx proxies `/api` to backend FQDN |
| nginx Host header fix | Harry | Mar 2, 2026 | `proxy_set_header Host $proxy_host` for ACA host-based routing |
| nginx SNI fix | Harry | Mar 2, 2026 | `proxy_ssl_server_name on;` for TLS handshake hostname |
| Backend `minReplicas: 1` | Harry | Mar 2, 2026 | Eliminate cold-start 502s on first AI chat request |
| AI Foundry env vars configured | Harry | Mar 2, 2026 | `AZURE_AI_FOUNDRY_ENDPOINT`, `AZURE_AI_MODEL_DEPLOYMENT`, `AZURE_CLIENT_ID` |
| Cognitive Services OpenAI User role | Harry | Mar 2, 2026 | Granted to backend MI |
| Async agents | Harry | Mar 2, 2026 | All 3 agents switched from sync to `AsyncAzureOpenAI` |
| SSE streaming endpoint | Harry | Mar 2, 2026 | `POST /api/agent/chat/stream` — `status`/`token`/`done`/`error` events |
| Frontend SSE streaming | Harry | Mar 2, 2026 | `useChat` `ReadableStream` parser; in-place token patching |
| AIChatPanel streaming UI | Harry | Mar 2, 2026 | Tool-call status line + blinking cursor on active message |
| Path A swedencentral gpt-5 deployment | Harry | May 2026 | Commit `a635db8` |
| Path B sub-step 2 — Agent Framework handoff | Harry | May 2026 | Commit `0828483` |
| Path B sub-step 3 part 1 — `/api/agent/chat/handoff/stream` endpoint + UI preview toggle | Harry | May 2026 | Commit `df3691d` |
| Path B sub-step 3.2.b — SC Foundry + MCP + import fixes | Harry | May 2026 | Commit `b3fd2c2` |
| gpt-5 SDK fix — `max_completion_tokens`, drop `temperature` | Harry | May 2026 | Commit `fa32223` |
| SQL AAD admin reassigned to FDPO + bicepparam pinned | Harry | May 2026 | Commit `0af2e78` |
| DB grant + schema + seed loaded; v2 CRUD routers GREEN | Harry | May 2026 | `data/db/grant_sql_access.sql` + `azure_sql_full_setup.sql` |
| Polish bundle — ID alias normalization + page title + qa-log gitignore | Harry | May 2026 | Commit `be9fd9e` |

---

## 🐛 Debug log — March 2, 2026

### Issue: AI Chat returning 401 Unauthorized in the browser

**Symptom:** Clicking any agent prompt (e.g. "Analyze claims impact for
CLI001") in the React UI returned a `401 Unauthorized` with body
`{"detail":"Method Not Allowed"}`. GET requests (dashboard, carriers,
clients) all worked. Only POST `/api/agent/chat` failed.

**Confirmed working:**
- `az account get-access-token` inside the backend container → valid token
- `curl -X POST localhost:8000/api/agent/chat` directly to backend → 200
- `curl -X POST localhost:8080/api/agent/chat` through nginx → 200
- Simulating browser headers with curl (Origin, Referer, sec-fetch-*)
  through nginx → 200
- Backend logs showed only 200s; the browser's POST never appeared in
  nginx access logs

**Root causes:**

| # | Problem | Impact |
|---|---------|--------|
| 1 | **Corporate Zscaler proxy** intercepts POST from Windows browser to localhost → 401 | Browser POST silently blocked before reaching nginx |
| 2 | **Stale Docker image** — frontend running a Feb 28 build | Code changes invisible in browser |
| 3 | **nginx `Connection: upgrade`** set unconditionally on all `/api` requests | Every API call advertised as WebSocket upgrade |

**Fixes:**

1. nginx `map $http_upgrade $connection_upgrade` block.
2. Backend `GET /api/agent/chat` query-param alias.
3. Frontend `useChat` POST→GET auto-fallback on 401/405.
4. Rebuilt both containers.

**Residual concern:** Zscaler continues to block POST to localhost in the
Windows browser. The GET fallback handles this transparently. In ACA (normal
HTTPS, no Zscaler interception) the issue disappears.

---

## 🐛 Debug log — Azure Container Apps first deploy (March 2, 2026)

### Issue: Frontend showing Azure placeholder page after first deploy

| # | Problem | Fix |
|---|---------|-----|
| 1 | Wrong image names — initial deploy used `frontend:latest` / `backend:latest`, Bicep expected `broker-frontend:latest` / `broker-backend:latest` | Rebuild with correct `--image` flags |
| 2 | Missing AcrPull RBAC on both MIs → image pulls silently failed, revision `ActivationFailed` | `az role assignment create --role AcrPull` for both principals |
| 3 | `USER nginx` in Dockerfile — nginx can't bind port 80 as non-root in ACA's restricted security context | Removed `USER nginx` + associated `chown` block |
| 4 | `API_BACKEND_URL` not set — `docker-entrypoint.sh` defaulted to `http://backend:8000` (compose hostname) | `az containerapp update --set-env-vars "API_BACKEND_URL=https://<backend-fqdn>"` |

**Lesson:** Always use `--revision-suffix <unique>` on `az containerapp
update` to force a new revision and clear stuck `ActivationFailed` state.

---

## 🐛 Debug log — ACA proxy + async + streaming (March 2, 2026)

### 1. AI chat 502 when called via browser (not localhost)

| # | Problem | Fix |
|---|---------|-----|
| 1 | nginx forwarded `Host: <frontend-fqdn>` to backend — ACA rejects (expects backend FQDN) | `proxy_set_header Host $proxy_host` |
| 2 | nginx not including backend hostname in TLS SNI during `proxy_pass` — ACA routes by SNI too | `proxy_ssl_server_name on;` |
| 3 | Backend `minReplicas: 0` — cold-start meant nginx received 502 before backend ready | Set `minReplicas: 1` in `main.bicep:76` |

### 2. Agent endpoints errored with "event loop is closed"

**Root cause:** All three agents instantiated synchronous `AzureOpenAI`
inside `async def` handlers. Blocking I/O inside `async def` starves the
uvicorn event loop.

**Fix:** `AzureOpenAI` → `AsyncAzureOpenAI`, added `await` on all `.create()`
calls in `claims_agent.py`, `quote_agent.py`, `crosssell_agent.py`.

### 3. 60–90s UX wait before any chat response appeared

**Root cause:** Entire model response had to finish before anything appeared.
GPT-4.1-mini takes 60–90s for a full tool-calling + response cycle.

**Fix (end-to-end streaming):**
- Backend: `POST /api/agent/chat/stream` returning `StreamingResponse`
  (`text/event-stream`). Tool-calling phase emits named `status` events;
  final answer phase uses `stream=True` and yields each `token` chunk.
- Frontend: `useChat` `ReadableStream` + `TextDecoder` + SSE parser,
  in-place token patching, exposes `isStreaming` + `statusMessage`.
- `AIChatPanel`: `RefreshCw` spinner + status text during tool calls;
  blinking `|` cursor on active assistant message.
