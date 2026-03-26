$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

Write-Host "[1/4] Ensuring .env exists..."
if (!(Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "Created .env from .env.example"
}

Write-Host "[2/4] Creating backend virtual environment..."
Set-Location "$root\backend"
python -m venv .venv

Write-Host "[3/4] Installing backend dependencies..."
& ".\.venv\Scripts\python.exe" -m pip install -r requirements.txt

Write-Host "[4/4] Running backend tests..."
& ".\.venv\Scripts\python.exe" -m pytest -q

Set-Location $root
Write-Host ""
Write-Host "Bootstrap complete."
Write-Host "Start backend with:"
Write-Host "  cd backend"
Write-Host "  .\.venv\Scripts\Activate.ps1"
Write-Host "  `$env:AGENT_ORCH_API_KEY='dev-key'"
Write-Host "  uvicorn app.main:app --reload --port 8000"
