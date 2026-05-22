@echo off
chcp 65001 >NUL 2>&1

:: 로그 파일에 출력 저장
set LOG=%~dp0debug.log
echo [%date% %time%] 실행.bat 시작 > %LOG%

echo [1] .setup_done 확인 중... >> %LOG%
if exist "%~dp0.setup_done" (
    echo [1] .setup_done 있음 - setup 건너뜀 >> %LOG%
    goto :launch
)
echo [1] .setup_done 없음 - setup.bat 실행 >> %LOG%

call "%~dp0setup.bat" >> %LOG% 2>&1
echo [2] setup.bat 종료코드: %ERRORLEVEL% >> %LOG%
if %ERRORLEVEL% NEQ 0 (
    echo [오류] setup.bat 실패 코드=%ERRORLEVEL% >> %LOG%
    type %LOG%
    echo.
    echo ============ 오류 발생 - 로그: %LOG% ============
    pause
    exit /b 1
)

:launch
echo [3] 서버 시작 중... >> %LOG%
title Tele Quant Dashboard

echo.
echo  ============================================
echo   Tele Quant Dashboard
echo   URL: http://localhost:8765
echo   종료: Ctrl+C 또는 이 창 닫기
echo  ============================================
echo.

start /B "" cmd /c "timeout /t 8 /nobreak >NUL 2>&1 && start http://localhost:8765"

echo [4] wsl 실행 >> %LOG%
wsl -d Ubuntu -- bash -l /home/kwanni/tq/_launch.sh
echo [5] wsl 종료코드: %ERRORLEVEL% >> %LOG%

echo.
echo  서버 종료됨. 로그: %LOG%
type %LOG%
pause
