// Broker Workbench - Demo Infrastructure (Streamlined)
// Deploys: ACR, Container App Environment, Frontend & Backend Container Apps,
//          Log Analytics, App Insights, Managed Identities + RBAC
// Skips: Azure SQL (app uses SQLite), AI Foundry (reuses existing), VNet, Key Vault

targetScope = 'resourceGroup'

@description('Base name for all resources')
param baseName string = 'brokerworkbench'

@description('Azure region for all resources')
param location string = resourceGroup().location

@description('Environment name')
@allowed(['dev', 'staging', 'prod'])
param environment string = 'dev'

@description('Container image for the frontend (nginx)')
param frontendContainerImage string = 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest'

@description('Container image for the backend (FastAPI)')
param backendContainerImage string = 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest'

@description('Existing AI Foundry endpoint URL')
param aiFoundryEndpoint string

@description('AI model deployment name on the existing AI Foundry')
param aiModelDeploymentName string = 'gpt-4o'

@description('Resource ID of the existing AI Foundry account (for RBAC)')
param existingAiFoundryResourceId string

param extraTags object = {}

// Variables
var resourceSuffix = '${baseName}-${environment}'
var uniqueSuffix = uniqueString(resourceGroup().id, baseName)
var tags = union({
  project: 'BrokerWorkbench'
  environment: environment
}, extraTags)

var containerAppEnvName = 'cae-${resourceSuffix}'
var frontendAppName = 'ca-frontend-${resourceSuffix}'
var backendAppName = 'ca-backend-${resourceSuffix}'
var appInsightsName = 'appi-${resourceSuffix}'
var logAnalyticsName = 'log-${resourceSuffix}'
var acrName = replace('acr${resourceSuffix}${uniqueSuffix}', '-', '')

// Log Analytics Workspace
resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: logAnalyticsName
  location: location
  tags: tags
  properties: {
    sku: { name: 'PerGB2018' }
    retentionInDays: 30
  }
}

// Application Insights
resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: appInsightsName
  location: location
  kind: 'web'
  tags: tags
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: logAnalytics.id
  }
}

// Azure Container Registry
resource acr 'Microsoft.ContainerRegistry/registries@2023-11-01-preview' = {
  name: acrName
  location: location
  tags: tags
  sku: { name: 'Basic' }
  properties: {
    adminUserEnabled: false
    publicNetworkAccess: 'Enabled'
  }
}

// Managed Identities
resource backendIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: 'id-backend-${resourceSuffix}'
  location: location
  tags: tags
}

resource frontendIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: 'id-frontend-${resourceSuffix}'
  location: location
  tags: tags
}

// RBAC: AcrPull for backend
resource acrPullBackend 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(acr.id, backendIdentity.id, 'acrpull')
  scope: acr
  properties: {
    principalId: backendIdentity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '7f951dda-4ed3-4680-a7ca-43fe172d538d')
  }
}

// RBAC: AcrPull for frontend
resource acrPullFrontend 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(acr.id, frontendIdentity.id, 'acrpull')
  scope: acr
  properties: {
    principalId: frontendIdentity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '7f951dda-4ed3-4680-a7ca-43fe172d538d')
  }
}

// Container App Environment (no VNet for demo simplicity)
resource containerAppEnvironment 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: containerAppEnvName
  location: location
  tags: tags
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logAnalytics.properties.customerId
        sharedKey: logAnalytics.listKeys().primarySharedKey
      }
    }
    workloadProfiles: [
      {
        name: 'Consumption'
        workloadProfileType: 'Consumption'
      }
    ]
  }
}

// Backend Container App
resource backendContainerApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: backendAppName
  location: location
  tags: union(tags, { component: 'backend' })
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${backendIdentity.id}': {}
    }
  }
  dependsOn: [
    acrPullBackend
  ]
  properties: {
    managedEnvironmentId: containerAppEnvironment.id
    configuration: {
      registries: [
        {
          server: acr.properties.loginServer
          identity: backendIdentity.id
        }
      ]
      ingress: {
        external: true
        targetPort: 8000
        transport: 'http'
        allowInsecure: false
        corsPolicy: {
          allowedOrigins: ['*']
          allowedMethods: ['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS']
          allowedHeaders: ['*']
          allowCredentials: false
        }
      }
    }
    template: {
      containers: [
        {
          name: 'backend'
          image: backendContainerImage
          resources: {
            cpu: json('0.5')
            memory: '1Gi'
          }
          env: [
            { name: 'DATABASE_URL', value: 'sqlite+aiosqlite:///./local.db' }
            { name: 'APPLICATIONINSIGHTS_CONNECTION_STRING', value: appInsights.properties.ConnectionString }
            { name: 'ENVIRONMENT', value: environment }
            { name: 'AZURE_CLIENT_ID', value: backendIdentity.properties.clientId }
            { name: 'AZURE_AI_FOUNDRY_ENDPOINT', value: aiFoundryEndpoint }
            { name: 'AZURE_AI_MODEL_DEPLOYMENT', value: aiModelDeploymentName }
          ]
        }
      ]
      scale: {
        minReplicas: 1
        maxReplicas: 1
      }
    }
  }
}

// Frontend Container App
resource frontendContainerApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: frontendAppName
  location: location
  tags: union(tags, { component: 'frontend' })
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${frontendIdentity.id}': {}
    }
  }
  dependsOn: [
    acrPullFrontend
  ]
  properties: {
    managedEnvironmentId: containerAppEnvironment.id
    configuration: {
      registries: [
        {
          server: acr.properties.loginServer
          identity: frontendIdentity.id
        }
      ]
      ingress: {
        external: true
        targetPort: 80
        transport: 'http'
        allowInsecure: false
      }
    }
    template: {
      containers: [
        {
          name: 'frontend'
          image: frontendContainerImage
          resources: {
            cpu: json('0.25')
            memory: '0.5Gi'
          }
          env: [
            {
              name: 'API_BACKEND_URL'
              value: 'https://${backendContainerApp.properties.configuration.ingress.fqdn}'
            }
          ]
        }
      ]
      scale: {
        minReplicas: 1
        maxReplicas: 1
      }
    }
  }
}

// Outputs
@description('Frontend Container App URL')
output frontendUrl string = 'https://${frontendContainerApp.properties.configuration.ingress.fqdn}'

@description('Backend API Container App URL')
output backendUrl string = 'https://${backendContainerApp.properties.configuration.ingress.fqdn}'

@description('ACR login server')
output acrLoginServer string = acr.properties.loginServer

@description('ACR name')
output acrName string = acr.name

@description('Backend managed identity principal ID (for RBAC grants on external resources)')
output backendIdentityPrincipalId string = backendIdentity.properties.principalId

@description('Backend managed identity client ID')
output backendIdentityClientId string = backendIdentity.properties.clientId

@description('Resource names')
output resourceNames object = {
  containerAppEnvironment: containerAppEnvironment.name
  frontendApp: frontendContainerApp.name
  backendApp: backendContainerApp.name
  acr: acr.name
  appInsights: appInsights.name
}
