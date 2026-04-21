// =============================================================================
// bot.bicep — Deploys Teams bot as a Container App alongside existing
// BrokerWorkbench infrastructure. Deployable independently.
//
// Usage:
//   az deployment group create \
//     --resource-group rg-bwbench-demo \
//     --template-file infra/bot.bicep \
//     --parameters microsoftAppId='<APP_ID>' microsoftAppPassword='<SECRET>' tenantId='<TENANT_ID>'
// =============================================================================

targetScope = 'resourceGroup'

// ── Parameters ───────────────────────────────────────────────────────────────

@description('Microsoft App ID for the bot (from Entra App Registration)')
param microsoftAppId string

@description('Microsoft App Password/Secret for the bot')
@secure()
param microsoftAppPassword string

@description('Tenant ID for the bot registration')
param tenantId string = subscription().tenantId

@description('Full container image reference (e.g. myacr.azurecr.io/broker-bot:v1)')
param botContainerImage string

@description('Name of the existing ACR')
param acrName string = 'acrbrokerworkbenchdev2qdxa3smrnc7a'

@description('Name of the existing Container App Environment')
param containerAppEnvName string = 'cae-brokerworkbench-dev'

@description('FQDN of the existing backend Container App')
param backendFqdn string = 'ca-backend-brokerworkbench-dev.thankfulpond-970c315d.westus2.azurecontainerapps.io'

@description('Base name for resource naming')
param baseName string = 'brokerworkbench'

@description('Environment label (dev, staging, prod)')
param environment string = 'dev'

@description('Azure region — defaults to resource group location')
param location string = resourceGroup().location

// ── Variables ────────────────────────────────────────────────────────────────

var resourceSuffix = '${baseName}-${environment}'
var tags = {
  project: 'BrokerWorkbench'
  environment: environment
}

// Built-in role definition IDs
var acrPullRoleId = '7f951dda-4ed3-4680-a7ca-43fe172d538d' // AcrPull

// ── Existing Resources (referenced, NOT redeployed) ──────────────────────────

// Existing Azure Container Registry — the bot image is pulled from here
resource acr 'Microsoft.ContainerRegistry/registries@2023-07-01' existing = {
  name: acrName
}

// Existing Container App Environment shared with frontend/backend
resource containerAppEnv 'Microsoft.App/managedEnvironments@2024-03-01' existing = {
  name: containerAppEnvName
}

// ── 1. User-Assigned Managed Identity ────────────────────────────────────────
// Used by the bot Container App to pull images from ACR via RBAC (no keys).

resource botIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: 'id-bot-${resourceSuffix}'
  location: location
  tags: tags
}

// Grant AcrPull so the Container App can pull images from the existing ACR
resource acrPullRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(acr.id, botIdentity.id, acrPullRoleId)
  scope: acr
  properties: {
    principalId: botIdentity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', acrPullRoleId)
  }
}

// ── 2. Azure Bot Service ─────────────────────────────────────────────────────
// Registers the bot with Azure Bot Framework so it can be reached via Teams.

resource botService 'Microsoft.BotService/botServices@2022-09-15' = {
  name: 'bot-${resourceSuffix}'
  location: 'global' // Bot Service is a global resource
  kind: 'azurebot'
  sku: {
    name: 'F0' // Free tier — sufficient for demo/POC
  }
  tags: tags
  properties: {
    displayName: 'BrokerWorkbench Bot'
    endpoint: 'https://${botContainerApp.properties.configuration.ingress.fqdn}/api/messages'
    msaAppId: microsoftAppId
    msaAppType: 'SingleTenant'
    msaAppTenantId: tenantId
  }
}

// Enable the Microsoft Teams channel on the bot
resource teamsChannel 'Microsoft.BotService/botServices/channels@2022-09-15' = {
  parent: botService
  name: 'MsTeamsChannel'
  location: 'global'
  properties: {
    channelName: 'MsTeamsChannel'
    properties: {
      isEnabled: true
    }
  }
}

// ── 3. Bot Container App ─────────────────────────────────────────────────────
// Runs the bot application in the shared Container App Environment.
// MICROSOFT_APP_PASSWORD is stored as a Container App secret (never in plain env vars).

resource botContainerApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: 'ca-bot-${resourceSuffix}'
  location: location
  tags: tags
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${botIdentity.id}': {}
    }
  }
  properties: {
    managedEnvironmentId: containerAppEnv.id
    configuration: {
      // Use managed identity to pull from ACR — no admin credentials needed
      registries: [
        {
          server: acr.properties.loginServer
          identity: botIdentity.id
        }
      ]
      ingress: {
        external: true
        targetPort: 3978
        transport: 'auto'
        allowInsecure: false
      }
      secrets: [
        {
          name: 'microsoft-app-password'
          value: microsoftAppPassword
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'broker-bot'
          image: botContainerImage
          resources: {
            cpu: json('0.25')
            memory: '0.5Gi'
          }
          env: [
            {
              name: 'MICROSOFT_APP_ID'
              value: microsoftAppId
            }
            {
              name: 'MICROSOFT_APP_PASSWORD'
              secretRef: 'microsoft-app-password'
            }
            {
              name: 'BACKEND_URL'
              value: 'https://${backendFqdn}'
            }
            {
              name: 'BOT_PORT'
              value: '3978'
            }
          ]
          probes: [
            {
              type: 'Liveness'
              httpGet: {
                path: '/health'
                port: 3978
              }
              initialDelaySeconds: 10
              periodSeconds: 30
            }
          ]
        }
      ]
      scale: {
        minReplicas: 1
        maxReplicas: 1 // Single replica for dev — scale up for prod
      }
    }
  }
  dependsOn: [
    acrPullRoleAssignment // Ensure RBAC is in place before the app tries to pull
  ]
}

// ── Outputs ──────────────────────────────────────────────────────────────────

@description('FQDN of the bot Container App')
output botContainerAppFqdn string = botContainerApp.properties.configuration.ingress.fqdn

@description('Full messaging endpoint URL for the bot')
output botMessagingEndpoint string = 'https://${botContainerApp.properties.configuration.ingress.fqdn}/api/messages'

@description('Bot Service resource name')
output botAppName string = botService.name

@description('Managed Identity client ID — use for any downstream RBAC grants')
output botIdentityClientId string = botIdentity.properties.clientId

@description('Managed Identity principal ID')
output botIdentityPrincipalId string = botIdentity.properties.principalId
