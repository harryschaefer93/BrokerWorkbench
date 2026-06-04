using './main.bicep'

// Broker Workbench - Parameter Values (Container Apps Edition)
// Update these values for your deployment

param baseName = 'brokerworkbench'
param environment = 'dev'

// Azure AD admin for SQL Server (MCAPS requires Azure AD-only authentication)
// Get your object ID with: az ad signed-in-user show --query id -o tsv
param sqlAadAdminObjectId = '30e86b03-ad92-4bbd-a570-0996a23d746d'
param sqlAadAdminName = 'admin@MngEnvMCAP822852.onmicrosoft.com'

// Container images
// Initial SC deploy: use MCR placeholders so the deployment succeeds before our ACR exists.
// After ACR is created and images pushed, update these to real ACR FQDN + tag and re-deploy.
param frontendContainerImage = 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest'
param backendContainerImage = 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest'
param mcpContainerImage = 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest'

// Additional MCAPS-required tags (cost center, business owner, data classification, etc.)
param extraTags = {
  costCenter: 'hackathon'
  businessOwner: 'hschaefer@microsoft.com'
  dataClassification: 'Internal'
}
