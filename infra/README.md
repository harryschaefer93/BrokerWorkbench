# Broker Workbench - Azure Infrastructure

Bicep templates to deploy the Broker Workbench to **Azure Container Apps** with full MCAPS/MCSB compliance.

---

## Resources Deployed

| Resource | Type | Purpose |
|----------|------|---------|
| **VNet** | `Microsoft.Network/virtualNetworks` | Network isolation (10.0.0.0/16) |
| **Container App Environment** | `Microsoft.App/managedEnvironments` | VNet-integrated hosting |
| **Frontend Container App** | `Microsoft.App/containerApps` | nginx serving React SPA |
| **Backend Container App** | `Microsoft.App/containerApps` | FastAPI Python API |
| **Azure Container Registry** | `Microsoft.ContainerRegistry/registries` | Private image registry |
| **Azure Key Vault** | `Microsoft.KeyVault/vaults` | Secrets management (RBAC-based) |
| **SQL Server** | `Microsoft.Sql/servers` | AAD-only auth, private endpoint |
| **SQL Database** | `Microsoft.Sql/servers/databases` | Application data |
| **SQL Private Endpoint** | `Microsoft.Network/privateEndpoints` | Private SQL connectivity |
| **Private DNS Zone** | `Microsoft.Network/privateDnsZones` | DNS for private endpoint |
| **User-Assigned Managed Identities** | `Microsoft.ManagedIdentity` | Backend + Frontend (RBAC pre-granted) |
| **Application Insights** | `Microsoft.Insights/components` | Telemetry |
| **Log Analytics** | `Microsoft.OperationalInsights/workspaces` | Log storage |
| **Defender for SQL** | Security alert policy | Threat detection |
| **SQL Auditing** | Audit settings | Compliance logging |
| **AI Foundry Account** | `Microsoft.CognitiveServices/accounts` | OpenAI + AI services (standalone Foundry) |
| **AI Foundry Project** | `Microsoft.CognitiveServices/accounts/projects` | Agent project for Broker Workbench |
| **AI Model Deployment** | `Microsoft.CognitiveServices/accounts/deployments` | GPT-4.1 model deployment |

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                        Azure Resource Group                          │
│                                                                      │
│  ┌─────────────────── VNet (10.0.0.0/16) ────────────────────────┐  │
│  │                                                                │  │
│  │  ┌─── snet-container-apps (10.0.0.0/23) ──────────────────┐  │  │
│  │  │  Container App Environment                              │  │  │
│  │  │  ┌──────────────────┐  ┌──────────────────────────┐    │  │  │
│  │  │  │  Frontend (nginx) │  │  Backend (FastAPI)       │    │  │  │
│  │  │  │  Port 80          │  │  Port 8000               │    │  │  │
│  │  │  │  User MI          │  │  User MI + KV Secrets    │    │  │  │
│  │  │  └──────────────────┘  └──────────────────────────┘    │  │  │
│  │  └────────────────────────────────────────────────────────┘  │  │
│  │                                                                │  │
│  │  ┌─── snet-private-endpoints (10.0.2.0/24) ───────────────┐  │  │
│  │  │  SQL Private Endpoint ──▶ SQL Server (public disabled)  │  │  │
│  │  └────────────────────────────────────────────────────────┘  │  │
│  └────────────────────────────────────────────────────────────────┘  │
│                                                                      │
│  ┌──────────────┐ ┌──────────┐ ┌──────────────┐ ┌──────────────┐   │
│  │ ACR          │ │ Key Vault│ │ App Insights │ │ Log Analytics│   │
│  │ (images)     │ │ (secrets)│ │ (telemetry)  │ │ (logs)       │   │
│  └──────────────┘ └──────────┘ └──────────────┘ └──────────────┘   │
└──────────────────────────────────────────────────────────────────────┘
```

---

## Prerequisites

1. **Azure CLI** v2.50+ ([Install](https://docs.microsoft.com/cli/azure/install-azure-cli))
2. **Bicep CLI** (bundled with Azure CLI)
3. **Azure subscription** with Contributor + User Access Administrator roles
4. Resource providers registered:
   - `Microsoft.App`
   - `Microsoft.ContainerService`
   - `Microsoft.Network`
   - `Microsoft.Sql`
   - `Microsoft.KeyVault`
   - `Microsoft.ContainerRegistry`
   - `Microsoft.CognitiveServices`

---

## Deployment Guide

### Step 1: Login and Set Subscription

```bash
# Login to your target tenant
az login --tenant <TENANT_ID>

# Set the subscription
az account set --subscription <SUBSCRIPTION_ID>

# Verify
az account show --query "{tenant:tenantId, subscription:name}" -o table
```

### Step 2: Register Resource Providers (first-time only)

```bash
az provider register --namespace Microsoft.App --wait
az provider register --namespace Microsoft.ContainerService --wait
az provider register --namespace Microsoft.Network --wait
az provider register --namespace Microsoft.Sql --wait
az provider register --namespace Microsoft.KeyVault --wait
az provider register --namespace Microsoft.ContainerRegistry --wait
az provider register --namespace Microsoft.CognitiveServices --wait
```

### Step 3: Get Your AAD Object ID

```bash
az ad signed-in-user show --query "{objectId:id, displayName:displayName}" -o table
```

### Step 4: Update Parameters

Edit `main.bicepparam`:

```bicep
param sqlAadAdminObjectId = '<YOUR_AAD_OBJECT_ID>'   // from Step 3
param sqlAadAdminName = '<YOUR_DISPLAY_NAME>'          // from Step 3

param extraTags = {
  costCenter: '<YOUR_COST_CENTER>'
  businessOwner: '<YOUR_EMAIL>'
  dataClassification: 'Internal'
}
```

Leave container images as the MCR placeholder for the initial deploy -- they'll be updated after ACR exists:

```bicep
param frontendContainerImage = 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest'
param backendContainerImage = 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest'
```

### Step 5: Create Resource Group and Deploy

```bash
# Create resource group
az group create --name rg-brokerworkbench-dev --location eastus

# Deploy infrastructure
az deployment group create \
  --resource-group rg-brokerworkbench-dev \
  --template-file infra/main.bicep \
  --parameters infra/main.bicepparam \
  --name bw-deploy-$(date +%Y%m%d%H%M%S)
```

This takes ~5-8 minutes. Monitor progress with:

```bash
az deployment operation group list \
  --resource-group rg-brokerworkbench-dev \
  --name <DEPLOYMENT_NAME> \
  --query "[].{resource:properties.targetResource.resourceName, state:properties.provisioningState}" \
  -o table
```

### Step 6: Get Deployment Outputs

```bash
az deployment group show \
  --resource-group rg-brokerworkbench-dev \
  --name <DEPLOYMENT_NAME> \
  --query properties.outputs -o json
```

Key outputs:
- `acrLoginServer` -- ACR endpoint for pushing images
- `frontendUrl` -- Frontend app URL
- `backendUrl` -- Backend API URL
- `sqlServerFqdn` -- SQL Server hostname
- `resourceNames` -- All resource names

### Step 7: Build and Push Container Images to ACR

```bash
# Get the ACR name from outputs (or resource group)
ACR_NAME=$(az acr list -g rg-brokerworkbench-dev --query "[0].name" -o tsv)

# Build and push backend (from project root)
az acr build -r $ACR_NAME -t broker-backend:latest -f backend/Dockerfile ./backend

# Build and push frontend
az acr build -r $ACR_NAME -t broker-frontend:latest -f frontend-react/Dockerfile ./frontend-react
```

### Step 8: Update Container Apps with Real Images

```bash
ACR_SERVER=$(az acr show -n $ACR_NAME --query loginServer -o tsv)

# Update backend
az containerapp update \
  --resource-group rg-brokerworkbench-dev \
  --name ca-backend-brokerworkbench-dev \
  --image "${ACR_SERVER}/broker-backend:latest"

# Update frontend
az containerapp update \
  --resource-group rg-brokerworkbench-dev \
  --name ca-frontend-brokerworkbench-dev \
  --image "${ACR_SERVER}/broker-frontend:latest"
```

### Step 9: Verify Deployment

```bash
# Check backend health
BACKEND_URL=$(az containerapp show -g rg-brokerworkbench-dev -n ca-backend-brokerworkbench-dev --query properties.configuration.ingress.fqdn -o tsv)
curl -s "https://${BACKEND_URL}/health" | jq .

# Check frontend
FRONTEND_URL=$(az containerapp show -g rg-brokerworkbench-dev -n ca-frontend-brokerworkbench-dev --query properties.configuration.ingress.fqdn -o tsv)
echo "Frontend: https://${FRONTEND_URL}"
```

---

## Post-Deployment Configuration

### 1. Azure AI Foundry (deployed automatically)

The Bicep template deploys an **Azure AI Foundry** account (Cognitive Services `AIServices` kind) with:
- A project named `brokerworkbench-agents`
- A `gpt-4.1` model deployment (GlobalStandard SKU)
- RBAC: backend managed identity granted **Azure AI User** role

The `AZURE_AI_FOUNDRY_PROJECT_CONNECTION_STRING` and `AZURE_AI_FOUNDRY_ENDPOINT` env vars are wired automatically into the backend Container App. **No manual portal steps required.**

To verify:

```bash
# Check the project endpoint from deployment outputs
az deployment group show \
  --resource-group rg-brokerworkbench-dev \
  --name <DEPLOYMENT_NAME> \
  --query properties.outputs.aiFoundryProjectEndpoint.value -o tsv
```

### 2. Initialize SQL Database

The backend's managed identity needs SQL access. Connect via the Azure Portal Query Editor or `sqlcmd` through the private endpoint **as the AAD admin**:

```bash
# Run the grant script (creates user, roles, schemas)
# Option A: Azure Portal > SQL Database > Query Editor > paste contents of:
#   data/db/grant_sql_access.sql
#
# Option B: sqlcmd (if you have private endpoint access)
sqlcmd -S sql-brokerworkbench-dev-<suffix>.database.windows.net \
  -d sqldb-brokerworkbench-dev \
  -G --authentication-method=ActiveDirectoryDefault \
  -i data/db/grant_sql_access.sql
```

Then seed the tables:

```bash
# From project root
python data/db/database_setup.py --target azure-sql

# Or just create schema (no seed data):
python data/db/database_setup.py --target azure-sql --schema-only
```

---

## Environment-Specific Configuration

| Environment | Container Scale | SQL SKU | Zone Redundant |
|-------------|-----------------|---------|----------------|
| `dev` | 0-1 (scale to zero) | Basic (5 DTU) | No |
| `staging` | 1-3 | S0 (10 DTU) | No |
| `prod` | 2-10 | S1 (20 DTU) | Yes |

```bash
# Deploy to a different environment
az deployment group create \
  --resource-group rg-brokerworkbench-staging \
  --template-file infra/main.bicep \
  --parameters infra/main.bicepparam \
  --parameters environment=staging
```

---

## Updating / Redeploying

### Push a New Image

```bash
ACR_NAME=$(az acr list -g rg-brokerworkbench-dev --query "[0].name" -o tsv)

# Rebuild and push
az acr build -r $ACR_NAME -t broker-backend:latest -f backend/Dockerfile ./backend

# Restart the container app to pick up the new image
az containerapp revision restart \
  --resource-group rg-brokerworkbench-dev \
  --name ca-backend-brokerworkbench-dev
```

### Re-run Bicep (idempotent)

Infrastructure changes can be re-applied safely:

```bash
az deployment group create \
  --resource-group rg-brokerworkbench-dev \
  --template-file infra/main.bicep \
  --parameters infra/main.bicepparam
```

---

## Security & Compliance (MCAPS/MCSB)

| Control | Implementation |
|---------|---------------|
| AAD-only SQL auth | `azureADOnlyAuthentication: true`, no SQL passwords |
| Private networking | SQL via Private Endpoint, VNet-integrated Container Apps |
| Managed Identity | User-assigned MI for ACR pull + Key Vault access |
| Secrets in Key Vault | SQL conn string + App Insights key stored in KV |
| No admin user on ACR | `adminUserEnabled: false`, RBAC-based pull |
| TLS 1.2 minimum | SQL `minimalTlsVersion: '1.2'` |
| Defender for SQL | Security alert policy enabled |
| SQL Auditing | Azure Monitor target enabled |
| Non-root containers | Frontend runs as `nginx` user |
| No sensitive outputs | Connection strings excluded from Bicep outputs |
| Resource tagging | Cost center, owner, data classification tags |

---

## Cost Optimization

Container Apps in `dev` scale to zero -- **no traffic = ~$0** (aside from SQL Basic ~$5/mo, Log Analytics, etc.).

First request after scale-down has a ~2-3 second cold start.

---

## Troubleshooting

### Container App revision stuck / timed out

```bash
# Check revision status
az containerapp revision list -g rg-brokerworkbench-dev -n ca-backend-brokerworkbench-dev -o table

# Check logs
az containerapp logs show -g rg-brokerworkbench-dev -n ca-backend-brokerworkbench-dev --type system
```

### RBAC not propagated yet

If Key Vault or ACR access fails right after deploy, RBAC role assignments can take 1-5 minutes to propagate. Wait and restart:

```bash
az containerapp revision restart -g rg-brokerworkbench-dev -n ca-backend-brokerworkbench-dev
```

### Deployment errors

```bash
# List failed operations
az deployment operation group list \
  --resource-group rg-brokerworkbench-dev \
  --name <DEPLOYMENT_NAME> \
  --query "[?properties.provisioningState=='Failed']" -o json
```

---

## File Structure

```
infra/
├── main.bicep          # Complete infrastructure template (~530 lines)
├── main.bicepparam     # Parameter values (edit before deploy)
└── README.md           # This file
```

---

## Useful Links

- [Azure Container Apps Docs](https://learn.microsoft.com/azure/container-apps/)
- [Bicep Documentation](https://learn.microsoft.com/azure/azure-resource-manager/bicep/)
- [Azure Key Vault](https://learn.microsoft.com/azure/key-vault/)
- [Azure SQL Private Link](https://learn.microsoft.com/azure/azure-sql/database/private-endpoint-overview)
- [MCAPS Governance Policies](https://aka.ms/mcaps-policies)
- [Azure AI Foundry](https://ai.azure.com)
