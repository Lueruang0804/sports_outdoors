# Brevo (Sendinblue) — free email API for Render. Verify MAIL_USERNAME as sender once.
Start-Process "https://app.brevo.com/account/register"
Write-Host "After signup:"
Write-Host "  1. Senders & IP -> Add sender -> sportsoutdoor25@gmail.com -> confirm email"
Write-Host "  2. SMTP & API -> API Keys -> Generate a new API key -> copy xkeysib-... (NOT xsmtpsib-)"
Write-Host "  3. Add to .env: BREVO_API_KEY=xkeysib-...  (required for Render)"
Start-Process "https://app.brevo.com/settings/keys/api"
Write-Host "  4. Run: .\scripts\sync_render_env.ps1  (with RENDER_API_KEY set for auto-sync)"
