# Copy Resend + mail env lines for Render Dashboard (Environment tab).
$Root = Split-Path $PSScriptRoot -Parent
$envFile = Join-Path $Root ".env"
if (-not (Test-Path $envFile)) { Write-Error ".env not found" }

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
if (-not $local["RESEND_API_KEY"]) {
    Write-Error "Add RESEND_API_KEY to .env first."
}

$lines = @(
    "RESEND_API_KEY=$($local['RESEND_API_KEY'])",
    "RESEND_FROM=$($local['RESEND_FROM'])",
    "MAIL_FAIL_OPEN=false",
    "FLASK_ENV=production"
)
$text = $lines -join "`n"
$out = Join-Path $Root "render-resend-paste.txt"
Set-Content -Path $out -Value $text -Encoding UTF8
Set-Clipboard -Value $text

Write-Host "Copied to clipboard and wrote: $out" -ForegroundColor Green
Write-Host ""
Write-Host "Render -> sports-outdoors -> Environment -> Add Environment Variable" -ForegroundColor Cyan
Write-Host "Paste each line (or use sync_render_env.ps1 with RENDER_API_KEY for full sync)."
Write-Host ""
Start-Process "https://dashboard.render.com"
