// Broker Workbench - Azure Infrastructure (Container Apps Edition)
// Deploys: VNet, ACR, Key Vault, Container App Environment, Frontend & Backend
// Container Apps, Azure SQL with Private Endpoint, App Insights, Defender for SQL

targetScope = 'resourceGroup'

// Parameters

@description('Base name for all resources (will be used as prefix)')
param baseName string = 'brokerworkbench'

@description('Azure region for all resources')
param location string = resourceGroup().location

@description('Environment name (dev, staging, prod)')
@allowed(['dev', 'staging', 'prod'])
param environment string = 'dev'

@description('Azure AD admin object ID for SQL Server')
param sqlAadAdminObjectId string

@description('Azure AD admin display name for SQL Server')
param sqlAadAdminName string = 'SQL Admin'

@description('Container image for the frontend (nginx)')
param frontendContainerImage string

@description('Container image for the backend (FastAPI)')
param backendContainerImage string

@description('Additional tags required by your organization (e.g. cost center, owner)')
param extraTags object = {}

@description('Globally unique name for the Azure AI Foundry account (Cognitive Services AIServices kind)')
param aiFoundryName string = 'ai-${baseName}-${environment}'

@description('Name for the AI Foundry project (child of the Foundry account)')
param aiProjectName string = '${baseName}-agents'

@description('OpenAI model to deploy in the Foundry account')
param aiModelDeploymentName string = 'gpt-4.1'

@description('OpenAI model name to deploy')
param aiModelName string = 'gpt-4.1'

@description('OpenAI model version')
param aiModelVersion string = '2025-04-14'

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
var sqlServerName = 'sql-${resourceSuffix}-${uniqueSuffix}'
var sqlDatabaseName = 'sqldb-${resourceSuffix}'
var appInsightsName = 'appi-${resourceSuffix}'
var logAnalyticsName = 'log-${resourceSuffix}'
var vnetName = 'vnet-${resourceSuffix}'
var acrName = replace('acr${resourceSuffix}${uniqueSuffix}', '-', '')
var keyVaultName = 'kv-${take(resourceSuffix, 10)}-${take(uniqueSuffix, 6)}'

var sqlSkuMap = {
  dev: { name: 'Basic', tier: 'Basic', capacity: 5 }
  staging: { name: 'S0', tier: 'Standard', capacity: 10 }
  prod: { name: 'S1', tier: 'Standard', capacity: 20 }
}

var containerScaleMap = {
  dev: { minReplicas: 1, maxReplicas: 1 }
  staging: { minReplicas: 1, maxReplicas: 3 }
  prod: { minReplicas: 2, maxReplicas: 10 }
}

// Networking

resource vnet 'Microsoft.Network/virtualNetworks@2024-01-01' = {
  name: vnetName
  location: location
  tags: tags
  properties: {
    addressSpace: {
      addressPrefixes: ['10.0.0.0/16']
    }
  }
}

resource subnetContainerApps 'Microsoft.Network/virtualNetworks/subnets@2024-01-01' = {
  parent: vnet
  name: 'snet-container-apps'
  properties: {
    addressPrefix: '10.0.0.0/23'
    delegations: [
      {
        name: 'Microsoft.App.environments'
        properties: {
          serviceName: 'Microsoft.App/environments'
        }
      }
    ]
  }
}

resource subnetPrivateEndpoints 'Microsoft.Network/virtualNetworks/subnets@2024-01-01' = {
  parent: vnet
  name: 'snet-private-endpoints'
  dependsOn: [subnetContainerApps]
  properties: {
    addressPrefix: '10.0.2.0/24'
  }
}

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

// Application Insights (public network access disabled for compliance)

resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: appInsightsName
  location: location
  kind: 'web'
  tags: tags
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: logAnalytics.id
    publicNetworkAccessForIngestion: 'Disabled'
    publicNetworkAccessForQuery: 'Disabled'
  }
}

// Azure Container Registry (MCAPS requires approved private registry)

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

// Azure Key Vault (secrets store)

resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: keyVaultName
  location: location
  tags: tags
  properties: {
    sku: { family: 'A', name: 'standard' }
    tenantId: tenant().tenantId
    enableRbacAuthorization: true
    enableSoftDelete: true
    softDeleteRetentionInDays: 7
    enablePurgeProtection: true
    publicNetworkAccess: 'Enabled'
    networkAcls: {
      defaultAction: 'Allow'
      bypass: 'AzureServices'
    }
  }
}

// ── Azure AI Foundry (Cognitive Services AIServices with project management) ──

resource aiFoundry 'Microsoft.CognitiveServices/accounts@2025-04-01-preview' = {
  name: aiFoundryName
  location: location
  tags: union(tags, { component: 'ai' })
  identity: {
    type: 'SystemAssigned'
  }
  sku: {
    name: 'S0'
  }
  kind: 'AIServices'
  properties: {
    allowProjectManagement: true
    customSubDomainName: aiFoundryName
    disableLocalAuth: true
    publicNetworkAccess: 'Enabled'
  }
}

resource aiProject 'Microsoft.CognitiveServices/accounts/projects@2025-04-01-preview' = {
  parent: aiFoundry
  name: aiProjectName
  location: location
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    description: 'Broker Workbench AI agents project'
    displayName: 'Broker Workbench Agents'
  }
}

resource aiModelDeployment 'Microsoft.CognitiveServices/accounts/deployments@2025-04-01-preview' = {
  parent: aiFoundry
  name: aiModelDeploymentName
  sku: {
    capacity: 1
    name: 'GlobalStandard'
  }
  properties: {
    model: {
      name: aiModelName
      format: 'OpenAI'
      version: aiModelVersion
    }
  }
}

// User-Assigned Managed Identity (created before container apps so RBAC can propagate)

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

// RBAC: Backend identity gets AcrPull on ACR (granted BEFORE container app creation)

resource acrPullBackend 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(acr.id, backendIdentity.id, 'acrpull')
  scope: acr
  properties: {
    principalId: backendIdentity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '7f951dda-4ed3-4680-a7ca-43fe172d538d')
  }
}

// RBAC: Frontend identity gets AcrPull on ACR

resource acrPullFrontend 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(acr.id, frontendIdentity.id, 'acrpull')
  scope: acr
  properties: {
    principalId: frontendIdentity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '7f951dda-4ed3-4680-a7ca-43fe172d538d')
  }
}

// RBAC: Backend identity gets Key Vault Secrets User

resource kvSecretsUserBackend 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(keyVault.id, backendIdentity.id, 'kvsecrets')
  scope: keyVault
  properties: {
    principalId: backendIdentity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '4633458b-17de-408a-b874-0445c86b69e6')
  }
}

// RBAC: Backend identity gets Azure AI User on the AI Foundry account
// Role: Azure AI User (53ca6127-db72-4b80-b1b0-d745d6d5456d) — grants data-plane access

resource aiUserBackend 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(aiFoundry.id, backendIdentity.id, 'azure-ai-user')
  scope: aiFoundry
  properties: {
    principalId: backendIdentity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '53ca6127-db72-4b80-b1b0-d745d6d5456d')
  }
}

// RBAC: AI Foundry project system-assigned identity gets Azure AI User on the parent account

resource aiUserProject 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(aiFoundry.id, aiProject.id, 'azure-ai-user-project')
  scope: aiFoundry
  properties: {
    principalId: aiProject.identity.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '53ca6127-db72-4b80-b1b0-d745d6d5456d')
  }
}

// Key Vault secrets

resource kvSecretSqlConn 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: keyVault
  name: 'sql-connection-string'
  properties: {
    value: 'mssql+aioodbc://${sqlServer.properties.fullyQualifiedDomainName}:1433/${sqlDatabaseName}?driver=ODBC+Driver+18+for+SQL+Server&Encrypt=yes&TrustServerCertificate=no&Authentication=ActiveDirectoryDefault'
  }
}

resource kvSecretAppInsights 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: keyVault
  name: 'appinsights-connection-string'
  properties: {
    value: appInsights.properties.ConnectionString
  }
}

// Container App Environment (VNet-integrated)

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
    vnetConfiguration: {
      infrastructureSubnetId: subnetContainerApps.id
      internal: false
    }
    zoneRedundant: environment == 'prod'
    workloadProfiles: [
      {
        name: 'Consumption'
        workloadProfileType: 'Consumption'
      }
    ]
  }
}

// Backend Container App (FastAPI) with user-assigned managed identity

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
    kvSecretsUserBackend
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
          allowedOrigins: union(
            ['https://${frontendAppName}.${containerAppEnvironment.properties.defaultDomain}'],
            environment == 'dev' ? ['http://localhost:3000', 'http://127.0.0.1:5500'] : []
          )
          allowedMethods: ['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS']
          allowedHeaders: ['*']
          allowCredentials: true
        }
      }
      secrets: [
        {
          name: 'sql-connection-string'
          keyVaultUrl: kvSecretSqlConn.properties.secretUri
          identity: backendIdentity.id
        }
        {
          name: 'appinsights-connection-string'
          keyVaultUrl: kvSecretAppInsights.properties.secretUri
          identity: backendIdentity.id
        }
      ]
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
            { name: 'DATABASE_URL', secretRef: 'sql-connection-string' }
            { name: 'APPLICATIONINSIGHTS_CONNECTION_STRING', secretRef: 'appinsights-connection-string' }
            { name: 'ENVIRONMENT', value: environment }
            { name: 'AZURE_CLIENT_ID', value: backendIdentity.properties.clientId }
            { name: 'AZURE_AI_FOUNDRY_PROJECT_CONNECTION_STRING', value: '${aiFoundry.properties.endpoint}/api/projects/${aiProjectName}' }
            { name: 'AZURE_AI_FOUNDRY_ENDPOINT', value: aiFoundry.properties.endpoint }
            { name: 'AZURE_AI_MODEL_DEPLOYMENT', value: aiModelDeploymentName }
          ]
        }
      ]
      scale: {
        minReplicas: containerScaleMap[environment].minReplicas
        maxReplicas: containerScaleMap[environment].maxReplicas
        rules: [
          {
            name: 'http-scaling'
            http: { metadata: { concurrentRequests: '10' } }
          }
        ]
      }
    }
  }
}

// Frontend Container App (nginx) with user-assigned managed identity

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
        minReplicas: containerScaleMap[environment].minReplicas
        maxReplicas: containerScaleMap[environment].maxReplicas
        rules: [
          {
            name: 'http-scaling'
            http: { metadata: { concurrentRequests: '50' } }
          }
        ]
      }
    }
  }
}

// Azure SQL Server (AAD-only auth, public access disabled)

resource sqlServer 'Microsoft.Sql/servers@2023-08-01-preview' = {
  name: sqlServerName
  location: location
  tags: tags
  properties: {
    version: '12.0'
    minimalTlsVersion: '1.2'
    publicNetworkAccess: 'Disabled'
    administrators: {
      administratorType: 'ActiveDirectory'
      principalType: 'User'
      login: sqlAadAdminName
      sid: sqlAadAdminObjectId
      tenantId: tenant().tenantId
      azureADOnlyAuthentication: true
    }
  }
}

// Azure SQL Database

resource sqlDatabase 'Microsoft.Sql/servers/databases@2023-08-01-preview' = {
  parent: sqlServer
  name: sqlDatabaseName
  location: location
  tags: tags
  sku: {
    name: sqlSkuMap[environment].name
    tier: sqlSkuMap[environment].tier
    capacity: sqlSkuMap[environment].capacity
  }
  properties: {
    collation: 'SQL_Latin1_General_CP1_CI_AS'
    maxSizeBytes: 2147483648
    zoneRedundant: environment == 'prod'
  }
}

// SQL Private Endpoint + DNS

resource sqlPrivateEndpoint 'Microsoft.Network/privateEndpoints@2024-01-01' = {
  name: 'pe-${sqlServerName}'
  location: location
  tags: tags
  properties: {
    subnet: { id: subnetPrivateEndpoints.id }
    privateLinkServiceConnections: [
      {
        name: 'pe-${sqlServerName}'
        properties: {
          privateLinkServiceId: sqlServer.id
          groupIds: ['sqlServer']
        }
      }
    ]
  }
}

resource privateDnsZoneSql 'Microsoft.Network/privateDnsZones@2024-06-01' = {
  name: 'privatelink${az.environment().suffixes.sqlServerHostname}'
  location: 'global'
  tags: tags
}

resource privateDnsZoneSqlLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2024-06-01' = {
  parent: privateDnsZoneSql
  name: '${vnetName}-link'
  location: 'global'
  properties: {
    virtualNetwork: { id: vnet.id }
    registrationEnabled: false
  }
}

resource privateDnsZoneGroupSql 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2024-01-01' = {
  parent: sqlPrivateEndpoint
  name: 'default'
  properties: {
    privateDnsZoneConfigs: [
      {
        name: 'sqlServer'
        properties: { privateDnsZoneId: privateDnsZoneSql.id }
      }
    ]
  }
}

// Microsoft Defender for SQL

resource sqlSecurityAlertPolicy 'Microsoft.Sql/servers/securityAlertPolicies@2023-08-01-preview' = {
  parent: sqlServer
  name: 'Default'
  properties: { state: 'Enabled' }
}

// SQL Server auditing

resource sqlAuditingSettings 'Microsoft.Sql/servers/auditingSettings@2023-08-01-preview' = {
  parent: sqlServer
  name: 'default'
  properties: {
    state: 'Enabled'
    isAzureMonitorTargetEnabled: true
  }
}

// SQL Database diagnostic settings

resource sqlDiagnosticSettings 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  name: 'sql-diagnostics'
  scope: sqlDatabase
  properties: {
    workspaceId: logAnalytics.id
    logs: [{ categoryGroup: 'allLogs', enabled: true }]
    metrics: [{ category: 'Basic', enabled: true }]
  }
}

// Outputs

@description('Frontend Container App URL')
output frontendUrl string = 'https://${frontendContainerApp.properties.configuration.ingress.fqdn}'

@description('Backend API Container App URL')
output backendUrl string = 'https://${backendContainerApp.properties.configuration.ingress.fqdn}'

@description('SQL Server fully qualified domain name')
output sqlServerFqdn string = sqlServer.properties.fullyQualifiedDomainName

@description('SQL Database name')
output sqlDatabaseName string = sqlDatabase.name

@description('ACR login server')
output acrLoginServer string = acr.properties.loginServer

@description('Container App Environment default domain')
output containerAppEnvDomain string = containerAppEnvironment.properties.defaultDomain

@description('Azure AI Foundry account endpoint')
output aiFoundryEndpoint string = aiFoundry.properties.endpoint

@description('Azure AI Foundry project endpoint (for SDK connection)')
output aiFoundryProjectEndpoint string = '${aiFoundry.properties.endpoint}/api/projects/${aiProjectName}'

@description('Resource names for reference')
output resourceNames object = {
  containerAppEnvironment: containerAppEnvironment.name
  frontendApp: frontendContainerApp.name
  backendApp: backendContainerApp.name
  sqlServer: sqlServer.name
  sqlDatabase: sqlDatabase.name
  appInsights: appInsights.name
  acr: acr.name
  keyVault: keyVault.name
  vnet: vnet.name
  aiFoundry: aiFoundry.name
  aiProject: aiProject.name
}
