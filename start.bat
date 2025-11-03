@echo off
echo.
echo ========================================
echo   Starting Evidentia Research Platform
echo ========================================
echo.

REM Start Backend
echo Starting Backend API...
start "Evidentia Backend" cmd /k "cd backend && python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload"

timeout /t 3 /nobreak >nul

REM Start Frontend
echo Starting Frontend UI...
start "Evidentia Frontend" cmd /k "cd frontend && npm run dev"

timeout /t 2 /nobreak >nul

echo.
echo ========================================
echo   Evidentia is running!
echo ========================================
echo.
echo   Frontend:  http://localhost:3000
echo   Backend:   http://localhost:8000
echo   API Docs:  http://localhost:8000/docs
echo.
echo Press any key to stop all services...
pause >nul

REM Cleanup
taskkill /FI "WindowTitle eq Evidentia Backend*" /T /F >nul 2>&1
taskkill /FI "WindowTitle eq Evidentia Frontend*" /T /F >nul 2>&1
echo.
echo All services stopped.
