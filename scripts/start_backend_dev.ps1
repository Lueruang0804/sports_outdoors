# Start Flask for mobile dev (listens on 0.0.0.0:5000 — reachable from phone on same Wi-Fi).
# Run from ecommerce_system:
#   .\scripts\start_backend_dev.ps1

$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$mobileCommon = Join-Path (Split-Path -Parent $root) "ecommerce_mobile_app\scripts\wireless-dev-common.ps1"
if (Test-Path $mobileCommon) {
  . $mobileCommon
  $ip = Get-PrimaryLanIPv4
  if ($ip) {
    Write-Host "Phone API URL (use in Flutter): http://${ip}:5000"
    Ensure-FlaskFirewallRule -Port 5000 | Out-Null
  }
}

Write-Host "Starting Flask on 0.0.0.0:5000 ..."
Write-Host "Press Ctrl+C to stop."
Write-Host ""

python run.py
