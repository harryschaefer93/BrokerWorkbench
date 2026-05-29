using './main.bicep'

// Broker Workbench - Parameter Values (Container Apps Edition)
// Update these values for your deployment

param baseName = 'brokerworkbench'
param environment = 'dev'

// Azure AD admin for SQL Server (MCAPS requires Azure AD-only authentication)
// Get your object ID with: az ad signed-in-user show --query id -o tsv
param sqlAadAdminObjectId = '30e86b03-ad92-4bbd-a570-0996a23d746d'
param sqlAadAdminName = 'admin@MngEnvMCAP822852.onmicrosoft.com'

// Container images (ACR — after initial deploy, use real images)
// For first-time deploys to a NEW environment, use MCR placeholder:
//   mcr.microsoft.com/azuredocs/containerapps-helloworld:latest
// Then build, push, and update with: az containerapp update --image ...
param frontendContainerImage = 'acrbrokerworkbenchdev2qdxa3smrnc7a.azurecr.io/broker-frontend:v8'
param backendContainerImage = 'acrbrokerworkbenchdev2qdxa3smrnc7a.azurecr.io/broker-backend:phaseb'
param mcpContainerImage = 'acrbrokerworkbenchdev2qdxa3smrnc7a.azurecr.io/broker-mcp:handoff-df3691d'

// Additional MCAPS-required tags (cost center, business owner, data classification, etc.)
param extraTags = {
  costCenter: 'hackathon'
  businessOwner: 'hschaefer@microsoft.com'
  dataClassification: 'Internal'
}
