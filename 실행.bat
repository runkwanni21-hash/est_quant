@echo off
setlocal enabledelayedexpansion
chcp 65001 >NUL 2>&1

:: ----------------------------------------------------------------
:: setup.bat 이 완료되지 않았으면 먼저 실행
:: ----------------------------------------------------------------
if not exist "%~dp0.setup_done" (
    echo  [INFO] 최초 실행: setup.bat 을 먼저 실행합니다...
    call "%~dp0setup.bat"
    if !ERRORLEVEL! NEQ 0 exit /b !ERRORLEVEL!
)

:: ----------------------------------------------------------------
:: 대시보드 실행
:: ----------------------------------------------------------------
title Tele Quant Dashboard

echo.
echo  ============================================
echo   Tele Quant Dashboard
echo   URL: http://localhost:8765
echo   종료: Ctrl+C 또는 이 창 닫기
echo  ============================================
echo.

start /B "" cmd /c "timeout /t 8 /nobreak >NUL 2>&1 && start http://localhost:8765"

wsl -d Ubuntu -- bash -l ~/tq/_launch.sh

echo.
echo  서버 종료됨
pause
