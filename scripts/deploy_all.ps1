# ============================================================================
# Broker Workbench - One-shot deploy of the "one brain, three surfaces" agent.
#
# Automates everything that CAN be automated from a laptop / CI runner:
#   1. Runs the offline test suite as a gate.
#   2. Cloud-builds the bot image (az acr build - no local Docker needed)
#      and rolls the bot Container App.
#   3. Cloud-builds the hosted-agent image and publishes a new Foundry
#      hosted-agent version (with REASONING_EFFORT=low baked in).
#
# What this CANNOT do (Microsoft platform boundary): install / sideload the
# Teams app package into M365 Copilot for a user. That stays manual (see
# SIDELOAD.md). The automatable prod alternative is org app-catalog publish
# via Microsoft Graph - left out by design (user opted to keep sideload).
#
# Usage:
#   .\scripts\deploy_all.ps1                  # build + deploy bot AND hosted agent
#   .\scripts\deploy_all.ps1 -Only bot        # bot only
#   .\scripts\deploy_all.ps1 -Only hosted     # hosted agent only
#   .\scripts\deploy_all.ps1 -SkipTests       # skip the pytest gate
# ============================================================================
[CmdletBinding()]
param(
    [ValidateSet("all", "bot", "hosted")]
    [string]$Only = "all",
    [switch]$SkipTests
)

$ErrorActionPreference = "Stop"

# ── Constants (live dev resources) ──
$RG        = "rg-bwbench-sc"
$ACR       = "acrbrokerworkbenchdevwnwtqzj2xcdts"
$ACR_LOGIN = "$ACR.azurecr.io"
$BOT_APP   = "ca-bot-brokerworkbench-dev"
$REPO_ROOT = (Resolve-Path "$PSScriptRoot\..").Path
$STAMP     = Get-Date -Format "yyMMddHHmm"

$doBot    = $Only -in @("all", "bot")
$doHosted = $Only -in @("all", "hosted")

function Step($n, $msg) { Write-Host "`n[$n] $msg" -ForegroundColor Cyan }

# Cloud-build an image in ACR, then confirm success by the (unique) output tag.
# On a Windows cp1252 console the az log streamer can crash with a
# UnicodeEncodeError AFTER the server-side build has already succeeded, so we
# never trust the streaming exit code - we verify the run status by tag.
function Invoke-AcrBuild {
    param([string]$Tag, [string]$Dockerfile, [string]$Context)

    $repo = $Tag.Split(":")[0]
    $imgTag = $Tag.Split(":")[1]
    # --no-logs avoids a Windows cp1252 console crash in the az log streamer.
    az acr build -r $ACR -t $Tag -f $Dockerfile $Context --no-logs -o none 2>$null
    # Confirm the server-side run actually succeeded (don't trust queue-time exit).
    $deadline = (Get-Date).AddMinutes(8)
    while ((Get-Date) -lt $deadline) {
        $status = az acr task list-runs -r $ACR --top 20 `
            --query "[?outputImages[0].tag=='$imgTag' && outputImages[0].repository=='$repo'].status | [0]" `
            -o tsv 2>$null
        if ($status -eq "Succeeded") { return }
        if ($status -in @("Failed", "Canceled", "Error", "Timeout")) {
            Write-Host "  ACR build for $Tag failed (status: '$status')." -ForegroundColor Red
            exit 1
        }
        Start-Sleep -Seconds 5
    }
    Write-Host "  ACR build for $Tag did not complete within 8 min." -ForegroundColor Red
    exit 1
}

# ── Gate: offline tests ──
if (-not $SkipTests) {
    Step "1/4" "Running offline test suite..."
    $py = Join-Path $REPO_ROOT ".venv\Scripts\python.exe"
    if (-not (Test-Path $py)) { $py = "python" }
    & $py -m pytest -q
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  Tests FAILED - aborting deploy." -ForegroundColor Red
        exit 1
    }
    Write-Host "  Tests passed." -ForegroundColor Green
} else {
    Write-Host "`n[1/4] Skipping tests (-SkipTests)." -ForegroundColor Yellow
}

# ── Bot: cloud build + roll the Container App ──
if ($doBot) {
    $botTag   = "streaming-$STAMP"
    $botImage = "${ACR_LOGIN}/broker-bot:$botTag"

    Step "2/4" "Cloud-building bot image $botImage ..."
    Invoke-AcrBuild -Tag "broker-bot:$botTag" -Dockerfile "$REPO_ROOT\bot\Dockerfile" -Context "$REPO_ROOT\bot"

    Write-Host "  Updating $BOT_APP ..." -ForegroundColor DarkGray
    az containerapp update --name $BOT_APP --resource-group $RG --image $botImage -o none
    if ($LASTEXITCODE -ne 0) { Write-Host "  Bot rollout FAILED." -ForegroundColor Red; exit 1 }
    Write-Host "  Bot deployed: $botImage" -ForegroundColor Green
} else {
    Write-Host "`n[2/4] Skipping bot (-Only $Only)." -ForegroundColor Yellow
}

# ── Hosted agent: cloud build + publish new Foundry version ──
if ($doHosted) {
    $haTag   = "sc-$STAMP"
    $haImage = "${ACR_LOGIN}/broker-hosted-agent:$haTag"

    Step "3/4" "Cloud-building hosted-agent image $haImage ..."
    Invoke-AcrBuild -Tag "broker-hosted-agent:$haTag" `
        -Dockerfile "$REPO_ROOT\backend\agents\foundry\hosted\Dockerfile" -Context $REPO_ROOT

    Write-Host "  Publishing new Foundry hosted-agent version..." -ForegroundColor DarkGray
    $py = Join-Path $REPO_ROOT ".venv\Scripts\python.exe"
    if (-not (Test-Path $py)) { $py = "python" }
    $env:HOSTED_AGENT_IMAGE = $haImage
    & $py "$REPO_ROOT\scripts\deploy_hosted_agent.py"
    if ($LASTEXITCODE -ne 0) { Write-Host "  Hosted-agent publish FAILED." -ForegroundColor Red; exit 1 }
    Write-Host "  Hosted agent deployed: $haImage" -ForegroundColor Green
} else {
    Write-Host "`n[3/4] Skipping hosted agent (-Only $Only)." -ForegroundColor Yellow
}

Step "4/4" "Done."
Write-Host "========================================" -ForegroundColor Cyan
Write-Host " Deploy complete." -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Remaining manual step: install/refresh the Teams app package"
Write-Host "  in M365 Copilot (see SIDELOAD.md). Everything else is automated."
