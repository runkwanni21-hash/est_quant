@echo off
setlocal enabledelayedexpansion
chcp 65001 >/dev/null 2>&1

echo.
echo  ================================================
echo   Tele Quant - Setup (WSL2 / Ubuntu)
echo  ================================================
echo.

:: ----------------------------------------------------------------
:: STEP 0  WSL2 확인
:: ----------------------------------------------------------------
wsl -d Ubuntu -- echo ok >/dev/null 2>&1
if !ERRORLEVEL! NEQ 0 (
    echo  [ERROR] WSL2 Ubuntu 배포판을 찾을 수 없습니다.
    echo.
    echo  설치 방법 (관리자 PowerShell):
    echo    wsl --install
    echo    (재부팅 후 Ubuntu 초기 사용자 설정 완료)
    echo.
    pause
    exit /b 1
)
echo  [OK] WSL2 Ubuntu 확인

:: ----------------------------------------------------------------
:: STEP 1  이미 설정된 경우 건너뜀
:: ----------------------------------------------------------------
if exist "%~dp0.setup_done" (
    echo  [SKIP] setup.bat 이미 완료됨 (.setup_done 존재)
    echo         재설치하려면 .setup_done 파일을 삭제하세요.
    goto :end_success
)

:: ----------------------------------------------------------------
:: STEP 2  WSL 사용자명 + 프로젝트 경로 감지
:: ----------------------------------------------------------------
set "WIN_PATH=%~dp0"
if "!WIN_PATH:~-1!" == "\" set "WIN_PATH=!WIN_PATH:~0,-1!"

for /f "delims=" %%u in ('wsl -d Ubuntu -- bash -l -c "echo $USER" 2^>nul') do set "WSL_USER=%%u"
if "!WSL_USER!"=="" (
    echo  [ERROR] WSL 사용자명을 가져오지 못했습니다.
    pause
    exit /b 1
)
echo  [OK] WSL 사용자: !WSL_USER!

for /f "delims=" %%p in ('wsl -d Ubuntu -- wslpath "!WIN_PATH!" 2^>nul') do set "WSL_PATH=%%p"
if "!WSL_PATH!"=="" (
    echo  [ERROR] WSL 경로 변환 실패: !WIN_PATH!
    pause
    exit /b 1
)
echo  [OK] WSL 경로: !WSL_PATH!

:: ----------------------------------------------------------------
:: STEP 3  심볼릭 링크 ~/tq 생성
:: ----------------------------------------------------------------
echo  [3/5] 심볼릭 링크 ~/tq 생성 중...
wsl -d Ubuntu -- bash -l -c "ln -sfn '!WSL_PATH!' ~/tq && echo OK"
if !ERRORLEVEL! NEQ 0 (
    echo  [ERROR] 심볼릭 링크 생성 실패
    pause
    exit /b 1
)
echo  [OK] ~/tq -> !WSL_PATH!

:: ----------------------------------------------------------------
:: STEP 4  uv 설치 (없는 경우)
:: ----------------------------------------------------------------
echo  [4/5] uv 설치 확인 중...
wsl -d Ubuntu -- bash -l -c "which uv >/dev/null 2>&1 && echo already || (curl -LsSf https://astral.sh/uv/install.sh | sh && echo installed)"
if !ERRORLEVEL! NEQ 0 (
    echo  [ERROR] uv 설치 실패. 인터넷 연결을 확인하세요.
    pause
    exit /b 1
)
echo  [OK] uv 준비 완료

:: ----------------------------------------------------------------
:: STEP 5  Python 패키지 동기화
:: ----------------------------------------------------------------
echo  [5/5] 패키지 동기화 중 (최초 실행: 3-5분 소요)...
wsl -d Ubuntu -- bash -l -c "UV_PROJECT_ENVIRONMENT=~/.venvs/tele-quant uv sync --extra dev --project ~/tq"
if !ERRORLEVEL! NEQ 0 (
    echo  [ERROR] 패키지 설치 실패. 오류 메시지를 확인하세요.
    pause
    exit /b 1
)
echo  [OK] 패키지 설치 완료

:: ----------------------------------------------------------------
:: STEP 6  .env.local 생성
:: ----------------------------------------------------------------
if not exist "%~dp0.env.local" (
    if exist "%~dp0env.template" (
        copy /Y "%~dp0env.template" "%~dp0.env.local" >/dev/null
        echo  [OK] .env.local 생성됨 (env.template 복사)
    ) else (
        echo  [WARN] env.template 파일이 없어 .env.local을 생성하지 못했습니다.
    )
) else (
    echo  [SKIP] .env.local 이미 존재
)

:: ----------------------------------------------------------------
:: 완료 마커
:: ----------------------------------------------------------------
echo. > "%~dp0.setup_done"

:end_success
echo.
echo  ================================================
echo   설정 완료!
echo  ================================================
echo.
echo  다음 단계:
echo    1. .env.local 파일에서 API 키를 입력하세요.
echo       (아래에서 메모장으로 자동으로 열립니다)
echo    2. run_dashboard.bat 을 실행하세요.
echo.

if exist "%~dp0.env.local" (
    echo  [INFO] .env.local 을 메모장으로 엽니다...
    start notepad "%~dp0.env.local"
)

echo  [READY] run_dashboard.bat 을 더블클릭하면 대시보드가 시작됩니다.
echo.
pause
