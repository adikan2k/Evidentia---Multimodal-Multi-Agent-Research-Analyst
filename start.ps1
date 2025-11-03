# Evidentia - Single Command Startup Script
# Run this with: .\start.ps1

Write-Host "🚀 Starting Evidentia..." -ForegroundColor Cyan
Write-Host ""

# Check if backend venv exists
if (-not (Test-Path "backend\.venv")) {
    Write-Host "⚠️  Backend virtual environment not found. Creating it..." -ForegroundColor Yellow
    Set-Location backend
    python -m venv .venv
    .\.venv\Scripts\Activate.ps1
    pip install -r requirements.txt
    Set-Location ..
    Write-Host "✅ Backend dependencies installed" -ForegroundColor Green
}

# Check if frontend node_modules exists
if (-not (Test-Path "frontend\node_modules")) {
    Write-Host "⚠️  Frontend dependencies not found. Installing..." -ForegroundColor Yellow
    Set-Location frontend
    npm install
    Set-Location ..
    Write-Host "✅ Frontend dependencies installed" -ForegroundColor Green
}

Write-Host ""
Write-Host "🔧 Starting services..." -ForegroundColor Cyan
Write-Host ""

# Start Backend
Write-Host "📡 Starting Backend API on http://localhost:8000..." -ForegroundColor Green
$backendProcess = Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$PWD\backend'; if (Test-Path .venv\Scripts\Activate.ps1) { .\.venv\Scripts\Activate.ps1 }; python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload" -PassThru -WindowStyle Normal

Start-Sleep -Seconds 3

# Start Frontend
Write-Host "🎨 Starting Frontend UI on http://localhost:3000..." -ForegroundColor Green
$frontendProcess = Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$PWD\frontend'; npm run dev" -PassThru -WindowStyle Normal

Start-Sleep -Seconds 2

Write-Host ""
Write-Host "✅ Evidentia is running!" -ForegroundColor Green
Write-Host ""
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan
Write-Host "  🌐 Frontend:  http://localhost:3000" -ForegroundColor Cyan
Write-Host "  📡 Backend:   http://localhost:8000" -ForegroundColor Cyan
Write-Host "  📚 API Docs:  http://localhost:8000/docs" -ForegroundColor Cyan
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan
Write-Host ""
Write-Host "💡 Try researching: 'Latest AI developments in healthcare'" -ForegroundColor Yellow
Write-Host ""
Write-Host "Press Ctrl+C to stop all services" -ForegroundColor Red
Write-Host ""

# Keep script running and handle cleanup
try {
    # Wait for user interrupt
    while ($true) {
        Start-Sleep -Seconds 1
    }
}
finally {
    Write-Host ""
    Write-Host "🛑 Shutting down services..." -ForegroundColor Yellow
    Stop-Process -Id $backendProcess.Id -ErrorAction SilentlyContinue
    Stop-Process -Id $frontendProcess.Id -ErrorAction SilentlyContinue
    Write-Host "✅ All services stopped" -ForegroundColor Green
}
