# PowerShell script to run Supply Watch (Healthcare Supply Chain Intelligence)
# Usage: .\scripts\run.ps1

$ErrorActionPreference = "Stop"
$ROOT_DIR = (Resolve-Path "$PSScriptRoot\..").Path

Write-Host "== Healthcare Supply Chain Intelligence ==" -ForegroundColor Cyan
Write-Host "Project root: $ROOT_DIR"

# 1. Generate data if it doesn't exist yet
if (-not (Test-Path "$ROOT_DIR\data\medicines.csv")) {
    Write-Host "-- Generating synthetic dataset..." -ForegroundColor Yellow
    python "$ROOT_DIR\data\generate_data.py"
}

# 2. Sync / migrate to MySQL if configured
Write-Host "-- Verifying MySQL database status..." -ForegroundColor Cyan
python "$ROOT_DIR\scripts\migrate_to_mysql.py"

# 3. Start the FastAPI backend
Write-Host "-- Starting FastAPI backend on http://localhost:8000 (docs at /docs)" -ForegroundColor Green
$backendProcess = Start-Process python -ArgumentList "-m uvicorn main:app --host 127.0.0.1 --port 8000" -WorkingDirectory "$ROOT_DIR\backend" -PassThru

# 4. Serve the frontend as static files
Write-Host "-- Serving frontend on http://localhost:5500" -ForegroundColor Green
$frontendProcess = Start-Process python -ArgumentList "-m http.server 5500 --bind 127.0.0.1" -WorkingDirectory "$ROOT_DIR\frontend" -PassThru

Write-Host ""
Write-Host "Backend:  http://localhost:8000/docs" -ForegroundColor Cyan
Write-Host "Frontend: http://localhost:5500" -ForegroundColor Cyan
Write-Host ""
Write-Host "Both servers are running in background processes."
Write-Host "Press Ctrl+C or close this window to exit."

try {
    # Keep script open and wait
    Wait-Process -Id $backendProcess.Id, $frontendProcess.Id
} finally {
    Stop-Process -Id $backendProcess.Id -ErrorAction SilentlyContinue
    Stop-Process -Id $frontendProcess.Id -ErrorAction SilentlyContinue
}
