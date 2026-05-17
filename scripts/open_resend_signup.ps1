# Opens Resend signup + docs (get API key, then add RESEND_API_KEY to .env and run sync_render_env.ps1)
Start-Process "https://resend.com/signup"
Start-Process "https://resend.com/docs/api-reference/emails/send-email"
Write-Host "After signup: API Keys -> create key -> add to .env as RESEND_API_KEY=re_..."
Write-Host "Then run: .\scripts\sync_render_env.ps1"
