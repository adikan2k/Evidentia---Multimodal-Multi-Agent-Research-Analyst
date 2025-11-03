# Evidentia 90-second demo script for localhost (PowerShell)

Write-Host "🚀 Starting Evidentia demo stack..." -ForegroundColor Green

# Start Docker Compose services
Set-Location ops
docker compose up -d
Write-Host "⏳ Waiting for services to be healthy..." -ForegroundColor Yellow
Start-Sleep -Seconds 45

# Start backend (assumes venv already created)
Set-Location ..\backend
if (-not (Test-Path .venv)) {
    Write-Host "❌ Backend venv not found. Run 'python -m venv .venv && .venv\Scripts\Activate.ps1 && pip install -r requirements.txt' first." -ForegroundColor Red
    exit 1
}
.venv\Scripts\Activate.ps1
$backend = Start-Process -FilePath "uvicorn" -ArgumentList "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload" -PassThru
Write-Host "✅ Backend started (PID $($backend.Id))" -ForegroundColor Green

# Start frontend
Set-Location ..\frontend
$frontend = Start-Process -FilePath "npm" -ArgumentList "run", "dev" -PassThru
Write-Host "✅ Frontend started (PID $($frontend.Id))" -ForegroundColor Green

Write-Host ""
Write-Host "🌐 Open your browser to: http://localhost:3000" -ForegroundColor Cyan
Write-Host "📌 Try this query: 'Compare GLP-1 vs SGLT2 outcomes in T2D'" -ForegroundColor Cyan
Write-Host "📊 Watch the progress, then view the Evidence Matrix and export PDF." -ForegroundColor Cyan
Write-Host ""
Write-Host "Press Ctrl+C to stop all services." -ForegroundColor Yellow

# Wait for interrupt
try {
    Wait-Process -Id $backend.Id, $frontend.Id
} finally {
    Write-Host "🛑 Stopping services..." -ForegroundColor Yellow
    Stop-Process -Id $backend.Id, $frontend.Id -ErrorAction SilentlyContinue
    Set-Location ..\ops
    docker compose down
}
