# Teams + M365 Copilot sideload — BrokerWorkbench bot

This document walks through sideloading the Bot Framework bot into Teams
personal chat and the M365 Copilot agents pane (the C4 acceptance step).
The artifact is `bot/BrokerWorkbench-Bot.zip`, rebuilt from
`bot/teams-manifest/` whenever the manifest or icons change.

The bot itself is deployed to Azure Container Apps and registered with Bot
Service `bot-brokerworkbench-dev` (msaAppId
`ce8f24bc-4c90-42c4-aa82-3cccad46d22f`, SingleTenant). Sideload is purely an
M365 client-side step — no Azure changes required.

---

## What's in the zip

```
BrokerWorkbench-Bot.zip
├── manifest.json      # v1.20, includes copilotAgents.customEngineAgents[]
├── color.png          # 192x192
└── outline.png        # 32x32
```

Rebuild after any manifest edit:

```pwsh
cd bot\teams-manifest
# Optional: regen icons via gen_icons.py
cd ..
Compress-Archive -Path teams-manifest\manifest.json,teams-manifest\color.png,teams-manifest\outline.png -DestinationPath BrokerWorkbench-Bot.zip -Force
```

---

## Pre-flight

1. Verify the bot is reachable end-to-end via DirectLine. The fastest gate
   is the workflow's `verify` job (or `py -3.11 -m pytest -m live
   tests/verify/test_bot_directline.py`). Both must pass for the bot to
   work in Teams or Copilot.
2. Confirm your Microsoft 365 account has:
   - **Custom app upload** permission in Teams admin (org-wide or scoped to
     your user). Without this you'll see "this app cannot be added".
   - **M365 Copilot license** assigned (E5 Copilot, Copilot Pro, etc.). The
     Copilot agents pane only appears for licensed users.

---

## Sideload 1 — Teams personal chat

1. Open Teams → **Apps** (left rail).
2. **Manage your apps** → **Upload an app** → **Upload a custom app**.
3. Select `bot/BrokerWorkbench-Bot.zip`.
4. Pick **Add** when prompted; choose the **Personal** scope.
5. Open the chat and try:
   - `Show CLI001 claims history`
   - `Compare carrier quotes for CLI002`
   - `Cross-sell opportunities for CLI003`
   - `Upcoming renewals`
6. Expected: typing indicator appears immediately, then an Adaptive Card
   with the agent response within ~10-30 seconds (Foundry latency).

If you see the typing indicator but never get a card, check the bot logs:

```bash
az containerapp logs show -g rg-bwbench-sc -n ca-bot-brokerworkbench-dev --tail 100 --follow
```

---

## Sideload 2 — M365 Copilot agents

1. Open https://copilot.microsoft.com (or the Copilot app in Teams).
2. **Agents** → **+ Add agent** → **Upload an agent**.
3. Select the same `BrokerWorkbench-Bot.zip`.
4. After upload, the BrokerWorkbench agent appears in your **Agents** pane.
5. Pin it, open it, and try the same prompts as Teams.

The M365 Copilot surface uses `copilotAgents.customEngineAgents[]` from the
manifest to route messages to the same Bot Service endpoint. There's no
duplicate Azure resource — Teams and Copilot share the bot.

---

## Known gaps

| # | Item | Status |
|---|---|---|
| C3 | `StreamingResponse` activities (token-by-token in Copilot) | Not yet implemented. Current bot sends one final Adaptive Card. Preview feature; deferred. |
| C4 | Sideload verification (this doc) | Manual step. No automated test — the closest automated proxy is the DirectLine parity test in `verify`. |

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| "This app cannot be added" | Custom app upload disabled by Teams admin | Ask tenant admin to allow custom apps for your user |
| Bot replies "I'm sorry, something went wrong" | Backend or Foundry upstream error | Check backend logs `az containerapp logs show -g rg-bwbench-sc -n ca-backend-brokerworkbench-dev` |
| No reply, no typing indicator | DirectLine routing failed (Bot Service can't reach `/api/messages`) | Re-run DirectLine probe `py -3.11 scratch\dl_probe.py`; check Bot Service endpoint matches SC ACA FQDN |
| 401 from Bot Service | App password rotated; MSI vs MSA mismatch | Re-check `BROKER_MICROSOFT_APP_PASSWORD` secret in the bot Container App; should match the Bot registration's password |
| Card renders but no agent answer | `_call_backend` got no SSE frames | Check that backend `/api/agent/chat/handoff/stream` is reachable from the bot container (private vs public FQDN) |
