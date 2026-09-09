@echo off
title DeepResearch Pro - Stop services
taskkill /FI "WINDOWTITLE eq DeepResearch Backend*" /T /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq DeepResearch Frontend*" /T /F >nul 2>&1
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { ($_.Name -eq 'python.exe' -and $_.CommandLine -match 'uvicorn|multiprocessing') -or ($_.Name -eq 'node.exe' -and $_.CommandLine -match 'vite') } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
echo Services stopped (backend 8000 + frontend 5173).
pause
