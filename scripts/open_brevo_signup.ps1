# Brevo (Sendinblue) — free email API for Render. Verify MAIL_USERNAME as sender once.
Start-Process "https://app.brevo.com/account/register"
Write-Host "After signup:"
Write-Host "  1. Senders & IP -> Add sender -> sportsoutdoor25@gmail.com -> confirm email"
Write-Host "  2. SMTP & API -> API Keys -> Create -> copy xkeysib-..."
Write-Host "  3. Add to .env: BREVO_API_KEY=xkeysib-..."
Write-Host "  4. Run: .\scripts\sync_render_env.ps1  (with RENDER_API_KEY set for auto-sync)"
