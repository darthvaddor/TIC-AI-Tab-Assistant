# PowerShell script to start TabSensei backend
Set-Location $PSScriptRoot\backend
Write-Host "Starting TabSensei Backend Server..." -ForegroundColor Green
Write-Host ""
Write-Host "Make sure Ollama is running on http://localhost:11434" -ForegroundColor Yellow
Write-Host ""
python -m uvicorn agent_server:app --host 0.0.0.0 --port 8000 --reload

