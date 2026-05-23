@echo off
chcp 65001 >nul 2>&1
title Tele Quant Dashboard

echo.
echo  ============================================
echo   Tele Quant Dashboard
echo  ============================================
echo   브라우저 주소: http://localhost:8765
echo   종료: Ctrl+C  또는  이 창 닫기
echo  ============================================
echo.

REM WSL 경로 계산 (이 배치파일 위치 기준)
set "WIN_DIR=%~dp0"
for /f "delims=" %%i in ('wsl wslpath -u "%WIN_DIR%"') do set "WSL_DIR=%%i"

REM 3초 후 브라우저 자동 열기 (백그라운드)
start /B "" cmd /c "timeout /t 4 /nobreak >nul 2>&1 && start http://localhost:8765"

REM WSL에서 대시보드 실행 (블로킹)
wsl -d Ubuntu -- bash -l -c "cd \"%WSL_DIR%\" && uv run tele-quant dashboard 2>&1"

echo.
echo  서버가 종료되었습니다.
pause
