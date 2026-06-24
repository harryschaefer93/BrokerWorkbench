"""End-to-end verification orchestrator for the BrokerWorkbench SC stack.

Runs every automated check in order, collects pass/fail, prints summary.
Designed to be the single command a demo operator runs before opening
the laptop:

    $env:BROKER_BACKEND_URL  = "https://ca-backend-...azurecontainerapps.io"
    $env:BROKER_FRONTEND_URL = "https://ca-frontend-...azurecontainerapps.io"
    python tests/verify_all.py

Checks (each marked PASS / FAIL / SKIP):
    1. Backend /health                                  (HTTP + DB)
    2. v2 data endpoints                                (clients/policies/renewals)
    3. Hosted agent version status                      (Foundry control plane)
    4. Eval harness  (pytest tests/eval/ -m live)       (5 canonical prompts)
    5. Playwright e2e (npx playwright test)             (web chat)

DirectLine bot parity is omitted from the default run \u2014 see
tests/verify/test_bot_directline.py for the standalone test and the
known-issue note: Bot Service forwarding fails with timeout despite the
bot being reachable / healthy from outside. Need Bot Framework auth
trace to resolve; not a blocker for the web + Foundry portal demo.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import httpx

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BACKEND = (
    "https://ca-backend-brokerworkbench-dev."
    "kinddune-112ddddc.swedencentral.azurecontainerapps.io"
)
DEFAULT_FRONTEND = (
    "https://ca-frontend-brokerworkbench-dev."
    "kinddune-112ddddc.swedencentral.azurecontainerapps.io"
)
HOSTED_VERSION_URL = (
    "https://ai-brokerworkbench-dev-wnwtqz.cognitiveservices.azure.com"
    "/api/projects/brokerworkbench-agents/agents/brokerworkbench/versions/5?api-version=v1"
)


def _print(name: str, status: str, detail: str = "") -> None:
    color = {"PASS": "\033[32m", "FAIL": "\033[31m", "SKIP": "\033[33m"}.get(status, "")
    reset = "\033[0m" if color else ""
    print(f"  {color}{status:<4}{reset}  {name}{'  -- ' + detail if detail else ''}")


def _check_backend_health(backend: str) -> bool:
    try:
        r = httpx.get(f"{backend}/health", timeout=15)
        data = r.json()
        ok = r.status_code == 200 and data.get("status") == "healthy"
        _print("backend /health", "PASS" if ok else "FAIL", f"{data}")
        return ok
    except Exception as exc:  # noqa: BLE001
        _print("backend /health", "FAIL", str(exc)[:120])
        return False


def _check_v2_data(backend: str) -> bool:
    paths = [
        ("/api/v2/clients/?limit=1", lambda d: len(d) >= 1),
        ("/api/v2/policies/?limit=1", lambda d: len(d) >= 1),
        (
            "/api/v2/renewals/dashboard",
            lambda d: d.get("summary", {}).get("total_renewals", 0) > 0,
        ),
    ]
    all_ok = True
    for path, check in paths:
        try:
            r = httpx.get(f"{backend}{path}", timeout=15)
            ok = r.status_code == 200 and check(r.json())
            _print(f"v2 GET {path}", "PASS" if ok else "FAIL", f"HTTP {r.status_code}")
            all_ok = all_ok and ok
        except Exception as exc:  # noqa: BLE001
            _print(f"v2 GET {path}", "FAIL", str(exc)[:120])
            all_ok = False
    return all_ok


def _check_hosted_agent() -> bool:
    try:
        tok = subprocess.check_output(
            ["az.cmd" if os.name == "nt" else "az",
             "account", "get-access-token",
             "--resource", "https://ai.azure.com",
             "--query", "accessToken", "-o", "tsv"],
            text=True,
        ).strip()
        r = httpx.get(
            HOSTED_VERSION_URL,
            headers={"Authorization": f"Bearer {tok}"},
            timeout=15,
        )
        info = r.json()
        ok = info.get("status") == "active"
        _print("hosted agent v5 status", "PASS" if ok else "FAIL", info.get("status", "?"))
        return ok
    except Exception as exc:  # noqa: BLE001
        _print("hosted agent v5 status", "FAIL", str(exc)[:120])
        return False


def _check_eval_harness(backend: str) -> bool:
    env = {**os.environ, "BROKER_BACKEND_URL": backend}
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/eval/", "-m", "live", "-q"],
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=1800,
    )
    last = proc.stdout.strip().splitlines()[-1] if proc.stdout else "(no output)"
    ok = proc.returncode == 0
    _print("eval harness (5 prompts)", "PASS" if ok else "FAIL", last[:120])
    return ok


def _check_playwright_e2e(frontend: str) -> bool:
    e2e_dir = REPO_ROOT / "tests" / "e2e"
    if not (e2e_dir / "node_modules").exists():
        _print("playwright e2e", "SKIP", "node_modules missing; run `npm install` in tests/e2e/")
        return True  # not a failure
    env = {**os.environ, "BROKER_FRONTEND_URL": frontend}
    proc = subprocess.run(
        ["npx", "playwright", "test", "tests/chat.spec.ts", "--reporter=list"],
        cwd=str(e2e_dir),
        env=env,
        capture_output=True,
        text=True,
        timeout=600,
        shell=os.name == "nt",
    )
    ok = proc.returncode == 0
    summary = "passed" if ok else proc.stdout.strip().splitlines()[-1][:120]
    _print("playwright e2e (chat.spec.ts)", "PASS" if ok else "FAIL", summary)
    return ok


def main() -> int:
    backend = os.environ.get("BROKER_BACKEND_URL", DEFAULT_BACKEND).rstrip("/")
    frontend = os.environ.get("BROKER_FRONTEND_URL", DEFAULT_FRONTEND).rstrip("/")

    print(f"\nBrokerWorkbench verify_all  ({time.strftime('%Y-%m-%d %H:%M:%S')})")
    print(f"  backend : {backend}")
    print(f"  frontend: {frontend}")
    print()

    results = [
        _check_backend_health(backend),
        _check_v2_data(backend),
        _check_hosted_agent(),
        _check_eval_harness(backend),
        _check_playwright_e2e(frontend),
    ]

    passed = sum(1 for r in results if r)
    total = len(results)
    print(f"\n{passed}/{total} checks passed.")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
