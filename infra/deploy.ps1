# ============================================================================
# Broker Workbench - Full Clean Deploy
# Waits for RG deletion to complete, recreates RG, deploys all infrastructure,
# builds and pushes container images, then updates Container Apps.
# 
# Usage: .\deploy.ps1
# ============================================================================

$ErrorActionPreference = "Stop"
$RG = "rg-bwbench-demo"
$LOCATION = "westus2"
$BICEP_FILE = "$PSScriptRoot\main.bicep"
$BICEP_PARAMS = "$PSScriptRoot\main.bicepparam"

# ── Step 1: Wait for RG deletion if it's still deprovisioning ──
Write-Host "`n[1/6] Checking resource group '$RG'..." -ForegroundColor Cyan
$exists = az group exists --name $RG 2>$null
if ($exists -eq "true") {
    $state = az group show --name $RG --query "properties.provisioningState" -o tsv 2>$null
    if ($state -eq "Deleting") {
        Write-Host "  RG is still deprovisioning. Waiting..." -ForegroundColor Yellow
        while ($true) {
            $exists = az group exists --name $RG 2>$null
            if ($exists -eq "false") { break }
            Write-Host "  Still deprovisioning... (checking every 20s)" -ForegroundColor DarkGray
            Start-Sleep -Seconds 20
        }
    } else {
        Write-Host "  RG exists in state '$state'. Deleting first..." -ForegroundColor Yellow
        az group delete --name $RG --yes
    }
}
Write-Host "  Resource group '$RG' is clear." -ForegroundColor Green

# ── Step 2: Create resource group ──
Write-Host "`n[2/6] Creating resource group '$RG' in $LOCATION..." -ForegroundColor Cyan
az group create --name $RG --location $LOCATION `
    --tags project=BrokerWorkbench environment=dev costCenter=hackathon `
    "businessOwner=hschaefer@microsoft.com" dataClassification=Internal `
    -o none
Write-Host "  Resource group created." -ForegroundColor Green

# ── Step 3: Deploy Bicep (all infrastructure) ──
Write-Host "`n[3/6] Deploying Bicep infrastructure (this takes ~10-15 min)..." -ForegroundColor Cyan
$deployment = az deployment group create `
    --resource-group $RG `
    --template-file $BICEP_FILE `
    --parameters $BICEP_PARAMS `
    --parameters skipModelDeployment=true `
    --name "brokerworkbench-$(Get-Date -Format 'yyyyMMdd-HHmmss')" `
    --output json 2>&1

if ($LASTEXITCODE -ne 0) {
    Write-Host "  Deployment FAILED:" -ForegroundColor Red
    Write-Host $deployment
    exit 1
}

$outputs = $deployment | ConvertFrom-Json
$acrLoginServer = $outputs.properties.outputs.acrLoginServer.value
$frontendUrl = $outputs.properties.outputs.frontendUrl.value
$backendUrl = $outputs.properties.outputs.backendUrl.value
$aiFoundryEndpoint = $outputs.properties.outputs.aiFoundryEndpoint.value

Write-Host "  Infrastructure deployed successfully!" -ForegroundColor Green
Write-Host "  ACR: $acrLoginServer" -ForegroundColor DarkGray
Write-Host "  AI Foundry: $aiFoundryEndpoint" -ForegroundColor DarkGray

# ── Step 4: Login to ACR ──
Write-Host "`n[4/6] Logging into ACR '$acrLoginServer'..." -ForegroundColor Cyan
az acr login --name $acrLoginServer
Write-Host "  ACR login successful." -ForegroundColor Green

# ── Step 5: Build & push container images ──
Write-Host "`n[5/6] Building and pushing container images..." -ForegroundColor Cyan
$repoRoot = (Resolve-Path "$PSScriptRoot\..").Path

Write-Host "  Building backend..." -ForegroundColor DarkGray
docker build -t "${acrLoginServer}/broker-backend:latest" "$repoRoot\backend"
docker push "${acrLoginServer}/broker-backend:latest"

Write-Host "  Building frontend..." -ForegroundColor DarkGray
docker build -t "${acrLoginServer}/broker-frontend:latest" "$repoRoot\frontend-react"
docker push "${acrLoginServer}/broker-frontend:latest"

Write-Host "  Images pushed." -ForegroundColor Green

# ── Step 6: Update Container Apps with real images ──
Write-Host "`n[6/6] Updating Container Apps with real images..." -ForegroundColor Cyan

az containerapp update `
    --name "ca-backend-brokerworkbench-dev" `
    --resource-group $RG `
    --image "${acrLoginServer}/broker-backend:latest" `
    -o none

az containerapp update `
    --name "ca-frontend-brokerworkbench-dev" `
    --resource-group $RG `
    --image "${acrLoginServer}/broker-frontend:latest" `
    -o none

Write-Host "  Container Apps updated." -ForegroundColor Green

# ── Summary ──
Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host " Deployment Complete!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Frontend:   $frontendUrl"
Write-Host "  Backend:    $backendUrl"
Write-Host "  AI Foundry: $aiFoundryEndpoint"
Write-Host "  ACR:        $acrLoginServer"
Write-Host "========================================`n" -ForegroundColor Cyan
