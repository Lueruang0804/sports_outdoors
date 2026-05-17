# Sync .env values to Render (or copy to clipboard for manual paste).
# Usage:
#   $env:RENDER_API_KEY = "rnd_..."   # from https://dashboard.render.com/u/settings#api-keys
#   .\scripts\sync_render_env.ps1
# Optional:
#   $env:RENDER_SERVICE_ID = "srv-..."
#   $env:RENDER_SERVICE_NAME = "sports-outdoors"

$ErrorActionPreference = "Stop"
$Root = Split-Path $PSScriptRoot -Parent

$envFile = Join-Path $Root ".env"
if (-not (Test-Path $envFile)) {
    Write-Error ".env not found at $envFile"
}

function Read-DotEnv($path) {
    $vars = @{}
    Get-Content $path | ForEach-Object {
        $line = $_.Trim()
        if (-not $line -or $line.StartsWith("#")) { return }
        $idx = $line.IndexOf("=")
        if ($idx -lt 1) { return }
        $k = $line.Substring(0, $idx).Trim()
        $v = $line.Substring($idx + 1).Trim()
        $vars[$k] = $v
    }
    return $vars
}

$local = Read-DotEnv $envFile

# Production overrides for Render
$renderVars = [ordered]@{
    FLASK_ENV          = "production"
    PYTHON_VERSION     = "3.12.8"
    MAIL_FAIL_OPEN     = "true"
    MAIL_TIMEOUT       = "8"
    APP_BASE_URL       = "https://sports-outdoors.onrender.com"
    SECRET_KEY         = $local["SECRET_KEY"]
    DATABASE_URL       = $local["DATABASE_URL"]
    MAIL_SERVER        = $local["MAIL_SERVER"]
    MAIL_PORT          = $local["MAIL_PORT"]
    MAIL_USE_TLS       = $local["MAIL_USE_TLS"]
    MAIL_USERNAME      = $local["MAIL_USERNAME"]
    MAIL_PASSWORD      = $local["MAIL_PASSWORD"]
}

if ($local["RESEND_API_KEY"]) {
    $renderVars["RESEND_API_KEY"] = $local["RESEND_API_KEY"]
    if ($local["RESEND_FROM"]) {
        $renderVars["RESEND_FROM"] = $local["RESEND_FROM"]
    } else {
        $renderVars["RESEND_FROM"] = "Sports & Outdoors <onboarding@resend.dev>"
    }
}

$clipboard = ($renderVars.GetEnumerator() | ForEach-Object { "{0}={1}" -f $_.Key, $_.Value }) -join "`n"
Set-Clipboard -Value $clipboard
Write-Host "Copied $($renderVars.Count) env vars to clipboard (paste in Render -> Environment)." -ForegroundColor Green

$apiKey = $env:RENDER_API_KEY
if (-not $apiKey) {
    Write-Host ""
    Write-Host "No RENDER_API_KEY set - manual paste only." -ForegroundColor Yellow
    Write-Host "Get API key: https://dashboard.render.com/u/settings#api-keys"
    Write-Host "Then: `$env:RENDER_API_KEY='rnd_...'; .\scripts\sync_render_env.ps1"
    exit 0
}

$serviceId = $env:RENDER_SERVICE_ID
$serviceName = if ($env:RENDER_SERVICE_NAME) { $env:RENDER_SERVICE_NAME } else { "sports-outdoors" }

if (-not $serviceId) {
    $headers = @{ Authorization = "Bearer $apiKey"; Accept = "application/json" }
    $list = Invoke-RestMethod -Uri "https://api.render.com/v1/services?limit=50" -Headers $headers -Method Get
    foreach ($item in $list) {
        $svc = $item.service
        if ($svc.name -eq $serviceName) {
            $serviceId = $svc.id
            break
        }
    }
}

if (-not $serviceId) {
    Write-Error "Could not find Render service '$serviceName'. Set `$env:RENDER_SERVICE_ID."
}

$headers = @{
    Authorization = "Bearer $apiKey"
    "Content-Type" = "application/json"
    Accept = "application/json"
}

$body = @(
    foreach ($key in $renderVars.Keys) {
        @{ key = $key; value = [string]$renderVars[$key] }
    }
)

Invoke-RestMethod `
    -Uri "https://api.render.com/v1/services/$serviceId/env-vars" `
    -Headers $headers `
    -Method Put `
    -Body ($body | ConvertTo-Json -Depth 5)

Write-Host "Updated Render service $serviceId ($serviceName)." -ForegroundColor Green
Write-Host "Trigger Manual Deploy in Render dashboard to apply."
