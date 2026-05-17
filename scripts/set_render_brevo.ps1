# Push BREVO_API_KEY from .env to Render (requires RENDER_API_KEY).
# Usage:
#   $env:RENDER_API_KEY = "rnd_..."
#   .\scripts\set_render_brevo.ps1

$ErrorActionPreference = "Stop"
$Root = Split-Path $PSScriptRoot -Parent
$envFile = Join-Path $Root ".env"
$renderKey = $env:RENDER_API_KEY
if (-not $renderKey) {
    Write-Error "Set `$env:RENDER_API_KEY first (Render Dashboard -> Account Settings -> API Keys)"
}

function Read-DotEnv($path) {
    $vars = @{}
    Get-Content $path | ForEach-Object {
        $line = $_.Trim()
        if (-not $line -or $line.StartsWith("#")) { return }
        $idx = $line.IndexOf("=")
        if ($idx -lt 1) { return }
        $vars[$line.Substring(0, $idx).Trim()] = $line.Substring($idx + 1).Trim()
    }
    return $vars
}

$local = Read-DotEnv $envFile
$brevo = $local["BREVO_API_KEY"]
if (-not $brevo -or -not $brevo.StartsWith("xkeysib-")) {
    Write-Error "BREVO_API_KEY (xkeysib-) not found in .env"
}

$serviceName = if ($env:RENDER_SERVICE_NAME) { $env:RENDER_SERVICE_NAME } else { "sports-outdoors" }
$serviceId = $env:RENDER_SERVICE_ID
$headers = @{ Authorization = "Bearer $renderKey"; Accept = "application/json" }

if (-not $serviceId) {
    $list = Invoke-RestMethod -Uri "https://api.render.com/v1/services?limit=50" -Headers $headers
    foreach ($item in $list) {
        if ($item.service.name -eq $serviceName) {
            $serviceId = $item.service.id
            break
        }
    }
}
if (-not $serviceId) { Write-Error "Service '$serviceName' not found" }

# Fetch existing env vars and merge
$existing = Invoke-RestMethod -Uri "https://api.render.com/v1/services/$serviceId/env-vars" -Headers $headers
$map = @{}
foreach ($row in $existing) {
    $map[$row.envVar.key] = $row.envVar.value
}
$map["BREVO_API_KEY"] = $brevo
$map["MAIL_FAIL_OPEN"] = "false"
if (-not $map["FLASK_ENV"]) { $map["FLASK_ENV"] = "production" }

$body = @($map.Keys | ForEach-Object { @{ key = $_; value = [string]$map[$_] } })
Invoke-RestMethod `
    -Uri "https://api.render.com/v1/services/$serviceId/env-vars" `
    -Headers @{ Authorization = "Bearer $renderKey"; "Content-Type" = "application/json"; Accept = "application/json" } `
    -Method Put `
    -Body ($body | ConvertTo-Json -Depth 5)

Write-Host "Updated BREVO_API_KEY on Render service $serviceName ($serviceId)." -ForegroundColor Green
Write-Host "Trigger Manual Deploy in Render dashboard."
