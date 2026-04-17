using './main.bicep'

// Broker Workbench - Parameter Values (Container Apps Edition)
// Update these values for your deployment

param baseName = 'brokerworkbench'
param environment = 'dev'

// Azure AD admin for SQL Server (MCAPS requires Azure AD-only authentication)
// Get your object ID with: az ad signed-in-user show --query id -o tsv
param sqlAadAdminObjectId = '4b08cd49-64c7-43bf-9fc2-603ca59d5354'
param sqlAadAdminName = 'Harry Schaefer'

// Container images (ACR — after initial deploy, use real images)
// For first-time deploys to a NEW environment, use MCR placeholder:
//   mcr.microsoft.com/azuredocs/containerapps-helloworld:latest
// Then build, push, and update with: az containerapp update --image ...
param frontendContainerImage = 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest'
param backendContainerImage = 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest'

// Additional MCAPS-required tags (cost center, business owner, data classification, etc.)
param extraTags = {
  costCenter: 'hackathon'
  businessOwner: 'hschaefer@microsoft.com'
  dataClassification: 'Internal'
}
