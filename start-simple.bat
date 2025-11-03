@echo off
echo.
echo ========================================
echo   Evidentia - Simple Startup Script
echo ========================================
echo.

echo Step 1: Setting up backend...
cd backend
if not exist ".venv" (
    echo Creating virtual environment...
    python -m venv .venv
)

echo Activating virtual environment...
call .venv\Scripts\activate.bat

echo Installing dependencies...
pip install -r requirements.txt

echo.
echo Step 2: Starting backend...
start "Backend" cmd /k "cd /d %CD% && .venv\Scripts\activate.bat && python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload"

echo.
echo Step 3: Starting frontend...
cd ..\frontend
start "Frontend" cmd /k "cd /d %CD% && npm run dev"

echo.
echo ========================================
echo   Services Starting...
echo ========================================
echo.
echo   Backend:  http://localhost:8000
echo   Frontend: http://localhost:3000 (or 3001 if 3000 is busy)
echo.
echo Both services are starting in separate windows.
echo Close this window when you see both services running.
echo.
pause
