# BrokerWorkbench E2E Smoke Tests

Minimal Playwright scaffold that confirms the React frontend loads on
`http://localhost:8080` without console errors. Used both by developers
locally and by the GitHub Actions `e2e-smoke` job.

## First-time setup

```bash
cd tests/e2e
npm install
npx playwright install chromium
```

> The browser binary download is intentionally **not** committed and is
> not done as part of `npm install` — run `npx playwright install chromium`
> once per machine (and once in CI; the workflow handles that for you).

## Run the smoke test

Ensure the frontend is serving on `http://localhost:8080`. Easiest paths:

```bash
# Option A — docker-compose (also boots backend + MCP server)
docker-compose up --build

# Option B — built bundle via `serve` (matches what CI does)
cd frontend-react && npm install && npm run build
npx serve -l 8080 dist
```

Then:

```bash
cd tests/e2e
npx playwright test
```

Reports land in `playwright-report/`; open with `npm run report`.

## Behavior when the frontend is down

The smoke spec self-skips with a clear reason if `http://localhost:8080`
is unreachable, so it won't false-positive in environments where the UI
isn't booted.
