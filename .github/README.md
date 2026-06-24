# GitHub Actions CI/CD — OIDC setup

This repo's `.github/workflows/deploy.yml` deploys to Azure on every push to
`fieldday`. It authenticates via **OIDC federated identity** (no client
secrets in GitHub) per FDPO policy.

This document captures the one-time setup needed before the workflow can run.

---

## What gets deployed

| Component | Container App | Resource group | Region |
|---|---|---|---|
| Backend (FastAPI) | `ca-backend-brokerworkbench-dev` | `rg-bwbench-sc` | swedencentral |
| Frontend (nginx + React) | `ca-frontend-brokerworkbench-dev` | `rg-bwbench-sc` | swedencentral |
| MCP server | `ca-mcp-brokerworkbench-dev` | `rg-bwbench-sc` | swedencentral |
| Teams bot | `ca-bot-brokerworkbench-dev` | `rg-bwbench-sc` | swedencentral |

Each component only rebuilds when its source path changes (path filter on the
`detect` job). Manual `workflow_dispatch` can force any subset.

After all builds, the `verify` job runs:

- backend `/health` reachable
- frontend root reachable
- `pytest -m live tests/verify/test_bot_directline.py` (DirectLine parity)

---

## One-time setup

### 1. Create a user-assigned managed identity

```bash
az identity create \
  -g rg-bwbench-sc \
  -n id-github-actions-deploy \
  -l swedencentral
```

Capture the `clientId`, `principalId`, and `tenantId` from the output.

### 2. Grant RBAC

The identity needs:

- **AcrPush** on the SC ACR `acrbrokerworkbenchdevwnwtqzj2xcdts` (all
  components)
- **Contributor** on `rg-bwbench-sc`
- **Reader** on the bot resource (for `az bot directline show` in verify)
- **Cognitive Services User** on the SC Foundry (optional, for future
  agent verifications)

```bash
SUB=$(az account show --query id -o tsv)
MI_PRINCIPAL=$(az identity show -g rg-bwbench-sc -n id-github-actions-deploy --query principalId -o tsv)

# ACR push — SC (all components)
az role assignment create \
  --assignee-object-id "$MI_PRINCIPAL" \
  --assignee-principal-type ServicePrincipal \
  --role AcrPush \
  --scope /subscriptions/$SUB/resourceGroups/rg-bwbench-sc/providers/Microsoft.ContainerRegistry/registries/acrbrokerworkbenchdevwnwtqzj2xcdts

# Container Apps Contributor on the SC RG
az role assignment create \
  --assignee-object-id "$MI_PRINCIPAL" \
  --assignee-principal-type ServicePrincipal \
  --role Contributor \
  --scope /subscriptions/$SUB/resourceGroups/rg-bwbench-sc
```

### 3. Add the federated credential for GitHub

Replace `<OWNER>/<REPO>` and adjust the `subject` to match the branches /
environments you want to trust.

```bash
MI_NAME=id-github-actions-deploy
RG=rg-bwbench-sc

# Trust pushes to the fieldday branch
az identity federated-credential create \
  --identity-name $MI_NAME -g $RG \
  --name github-fieldday-branch \
  --issuer https://token.actions.githubusercontent.com \
  --subject "repo:<OWNER>/<REPO>:ref:refs/heads/fieldday" \
  --audiences api://AzureADTokenExchange

# Trust the deploy environment (for workflow_dispatch + protection rules)
az identity federated-credential create \
  --identity-name $MI_NAME -g $RG \
  --name github-env-brokerworkbench-dev \
  --issuer https://token.actions.githubusercontent.com \
  --subject "repo:<OWNER>/<REPO>:environment:brokerworkbench-dev" \
  --audiences api://AzureADTokenExchange
```

### 4. Add GitHub repository secrets + environment

In the GitHub repo settings:

1. **Settings → Environments → New environment** named `brokerworkbench-dev`.
   Optionally require reviewers before deploys run.
2. **Settings → Secrets and variables → Actions** — add these as
   **environment secrets** on `brokerworkbench-dev`:

| Name | Value |
|---|---|
| `AZURE_CLIENT_ID` | `clientId` of `id-github-actions-deploy` |
| `AZURE_TENANT_ID` | `44e26be6-f73b-4438-8335-205b417d5b4d` |
| `AZURE_SUBSCRIPTION_ID` | `ed0f42ef-a8e0-4052-a074-8e50c093cedf` |

These are **non-secret** identifiers — they're just kept in environment
secrets for tidiness and to bind them to the protected environment.

### 5. Confirm the workflow runs

Push any change under `backend/`, `frontend-react/`, `bot/`, or `mcp_server/`
on the `fieldday` branch. The matching component job should fire, build the
image with a `<short-sha>` and `fieldday` tag, and roll the Container App.

---

## Notes

- **Image tag strategy**: each component gets two tags per run — the
  immutable `<git-sha-7>` (used for the actual update) plus the floating
  `fieldday` tag (handy for manual rollbacks: `az containerapp update --image
  acrbrokerworkbenchdevwnwtqzj2xcdts.azurecr.io/broker-backend:fieldday`).
- **`--image`-only update is safe** — preserves env vars, secret refs,
  probes, resources. The full-PATCH trap (see
  `/memories/repo/deployment-notes.md`) only bites when you also pass
  `--container-name` / `--set-env-vars` / `--cpu` / `--memory` etc.
- **No SP secrets**: the workflow has `permissions: id-token: write` and
  uses `azure/login@v2` with `client-id` / `tenant-id` / `subscription-id`
  only. No `client-secret` or `creds` blob — that's the FDPO no-keys
  guarantee.

---

## Pre-existing workflow

`.github/workflows/test.yml` already runs pytest + Playwright on every push.
It does NOT touch Azure and needs no OIDC setup.
