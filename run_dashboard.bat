@echo off
chcp 65001 >NUL 2>&1
title Tele Quant Dashboard

echo.
echo  ============================================
echo   Tele Quant Dashboard
echo   URL: http://localhost:8765
echo   Stop: Ctrl+C or close this window
echo  ============================================
echo.

start /B "" cmd /c "timeout /t 8 /nobreak >NUL 2>&1 && start http://localhost:8765"

wsl -d Ubuntu -- bash -l /home/kwanni/tq/_launch.sh

echo.
echo Server stopped.
pause
