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
echo  [0/5] WSL2 Ubuntu 확인 중...
wsl -d Ubuntu -- echo ok >/dev/null 2>&1
if !ERRORLEVEL! NEQ 0 (
    echo.
    echo  [오류] WSL2 Ubuntu 배포판을 찾을 수 없습니다.
    echo.
    echo  해결 방법 (관리자 PowerShell 에서 실행):
    echo    wsl --install
    echo    설치 완료 후 재부팅 ^> Ubuntu 초기 사용자 설정
    echo.
    pause
    exit /b 1
)
echo  [OK] WSL2 Ubuntu 확인

:: ----------------------------------------------------------------
:: STEP 1  이미 설정된 경우 건너뜀
:: ----------------------------------------------------------------
if exist "%~dp0.setup_done" (
    echo  [건너뜀] 이미 설정 완료됨 (.setup_done 존재)
    goto :end_success
)

:: ----------------------------------------------------------------
:: STEP 2  WSL 사용자명 + 프로젝트 경로 감지
:: ----------------------------------------------------------------
echo  [2/5] WSL 사용자명 감지 중...
set "WIN_PATH=%~dp0"
if "!WIN_PATH:~-1!" == "\" set "WIN_PATH=!WIN_PATH:~0,-1!"

for /f "delims=" %%u in ('wsl -d Ubuntu -- bash -l -c "echo $USER" 2^>nul') do set "WSL_USER=%%u"
if "!WSL_USER!"=="" (
    echo.
    echo  [오류] WSL 사용자명을 가져오지 못했습니다.
    echo  WSL Ubuntu 가 정상 설치되었는지 확인하세요:
    echo    wsl -d Ubuntu -- echo $USER
    echo.
    pause
    exit /b 1
)
echo  [OK] WSL 사용자: !WSL_USER!

echo  [2/5] WSL 경로 변환 중...
for /f "delims=" %%p in ('wsl -d Ubuntu -- wslpath "!WIN_PATH!" 2^>nul') do set "WSL_PATH=%%p"
if "!WSL_PATH!"=="" (
    echo.
    echo  [오류] WSL 경로 변환 실패
    echo  Windows 경로: !WIN_PATH!
    echo.
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
    echo.
    echo  [오류] 심볼릭 링크 생성 실패
    echo.
    pause
    exit /b 1
)
echo  [OK] ~/tq 링크 완료

:: ----------------------------------------------------------------
:: STEP 4  uv 설치 (없는 경우)
:: ----------------------------------------------------------------
echo  [4/5] uv 패키지 관리자 확인 중...
wsl -d Ubuntu -- bash -l -c "which uv >/dev/null 2>&1 && echo already || (curl -LsSf https://astral.sh/uv/install.sh | sh && echo installed)"
if !ERRORLEVEL! NEQ 0 (
    echo.
    echo  [오류] uv 설치 실패. 인터넷 연결을 확인하세요.
    echo.
    pause
    exit /b 1
)
echo  [OK] uv 준비 완료

:: ----------------------------------------------------------------
:: STEP 5  Python 패키지 동기화
:: ----------------------------------------------------------------
echo  [5/5] Python 패키지 설치 중 (최초 3-5분 소요)...
wsl -d Ubuntu -- bash -l -c "UV_PROJECT_ENVIRONMENT=~/.venvs/tele-quant uv sync --extra dev --project ~/tq"
if !ERRORLEVEL! NEQ 0 (
    echo.
    echo  [오류] 패키지 설치 실패.
    echo  인터넷 연결 또는 WSL 디스크 공간을 확인하세요.
    echo.
    pause
    exit /b 1
)
echo  [OK] 패키지 설치 완료

:: ----------------------------------------------------------------
:: STEP 6  .env.local 생성
:: ----------------------------------------------------------------
if not exist "%~dp0.env.local" (
    if exist "%~dp0env.template" (
        copy /Y "%~dp0env.template" "%~dp0.env.local" >NUL
        echo  [OK] .env.local 생성됨
    ) else (
        echo  [경고] env.template 없음 - .env.local 수동 생성 필요
    )
) else (
    echo  [건너뜀] .env.local 이미 존재
)

:: 완료 마커
echo. > "%~dp0.setup_done"

:end_success
echo.
echo  ================================================
echo   설정 완료!
echo  ================================================
echo.
echo  다음 단계:
echo    .env.local 에 API 키 입력 후 실행.bat 실행
echo.

if exist "%~dp0.env.local" (
    echo  .env.local 을 메모장으로 엽니다...
    start notepad "%~dp0.env.local"
)

echo.
echo  설정 완료. 아무 키나 눌러 닫기
pause
