# Setup Backend Dependencies
Write-Host "🔧 Setting up backend dependencies..." -ForegroundColor Cyan

Set-Location backend

# Check if virtual environment exists
if (-not (Test-Path ".venv")) {
    Write-Host "📦 Creating virtual environment..." -ForegroundColor Yellow
    python -m venv .venv
}

# Activate virtual environment
Write-Host "🔌 Activating virtual environment..." -ForegroundColor Yellow
.venv\Scripts\Activate.ps1

# Install dependencies
Write-Host "📥 Installing dependencies..." -ForegroundColor Yellow
pip install -r requirements.txt

# Test if backend can start
Write-Host "🧪 Testing backend startup..." -ForegroundColor Yellow
try {
    python -c "import app.main; print('✅ Backend imports successfully')"
    Write-Host "✅ Backend setup complete!" -ForegroundColor Green
} catch {
    Write-Host "❌ Backend setup failed: $_" -ForegroundColor Red
}

Write-Host ""
Write-Host "🚀 To start the backend, run:" -ForegroundColor Cyan
Write-Host "   .venv\Scripts\Activate.ps1" -ForegroundColor White
Write-Host "   python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload" -ForegroundColor White
