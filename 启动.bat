@echo off
title DeepResearch Pro - Starting
echo [1/4] Stop old services (if running)...
taskkill /FI "WINDOWTITLE eq DeepResearch Backend*" /T /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq DeepResearch Frontend*" /T /F >nul 2>&1
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { ($_.Name -eq 'python.exe' -and $_.CommandLine -match 'uvicorn|multiprocessing') -or ($_.Name -eq 'node.exe' -and $_.CommandLine -match 'vite') } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
timeout /t 2 /nobreak >nul

echo [2/4] Start backend (new window)...
start "DeepResearch Backend" cmd /k "cd /d %~dp0backend && .venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000"

echo [3/4] Start frontend (new window)...
start "DeepResearch Frontend" cmd /k "cd /d %~dp0frontend && set PATH=C:\Users\Administrator\AppData\Local\hermes\node;%%PATH%% && npm run dev"

echo [4/4] Waiting for services, then opening browser...
timeout /t 10 /nobreak >nul
start http://localhost:5173

echo.
echo ==============================================
echo   Done! Two service windows are open:
echo     - Backend window : API logs (check here for errors)
echo     - Frontend window: Vite status (minimize it)
echo   Stop: double-click stop-services.bat
echo ==============================================
pause
