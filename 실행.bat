@echo off
setlocal enabledelayedexpansion
chcp 65001 >/dev/null 2>&1

:: 전체 출력을 로그 파일에도 저장
set "LOG=%~dp02로그.log"

:: ----------------------------------------------------------------
:: setup.bat 이 완료되지 않았으면 먼저 실행
:: ----------------------------------------------------------------
if not exist "%~dp0.setup_done" (
    echo  [INFO] 최초 실행: setup.bat 을 먼저 실행합니다...
    call "%~dp0setup.bat"
    if !ERRORLEVEL! NEQ 0 (
        echo.
        echo  [오류] setup.bat 실패! ERRORLEVEL=!ERRORLEVEL!
        echo  위에 표시된 오류 메시지를 확인하세요.
        pause
        exit /b !ERRORLEVEL!
    )
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

start /B "" cmd /c "timeout /t 8 /nobreak >/dev/null 2>&1 && start http://localhost:8765"

echo  [INFO] WSL 서버 시작 중... (Ctrl+C 로 종료)
wsl -d Ubuntu -- bash -l ~/tq/_launch.sh

echo.
echo  서버 종료됨. 열린 창을 다시 실동하려면 실행.bat 실행.
pause
