@echo off
setlocal enabledelayedexpansion

if not defined _TQ_LAUNCHED (
    set _TQ_LAUNCHED=1
    start "Tele Quant Dashboard" cmd /k ""%~f0""
    exit /b
)

chcp 65001 >NUL 2>&1
cd /d "%~dp0"
set PYTHONUTF8=1
set UV_LINK_MODE=copy

echo.
echo  ================================================
echo   Tele Quant - AI Investment Analysis Dashboard
echo  ================================================
echo   Working dir: %CD%
echo.

:: ================================================================
::  STEP 1  Python 3.11+
:: ================================================================
echo  [1/5] Checking Python...
set "PY="

python --version 2>NUL
if !ERRORLEVEL! EQU 0 (
    for /f "tokens=2" %%v in ('python --version 2^>^&1') do (
        for /f "tokens=1,2 delims=." %%a in ("%%v") do (
            if %%a GEQ 3 if %%b GEQ 11 set "PY=python"
        )
    )
)

if "!PY!"=="" (
    py -3 --version 2>NUL
    if !ERRORLEVEL! EQU 0 (
        for /f "tokens=2" %%v in ('py -3 --version 2^>^&1') do (
            for /f "tokens=1,2 delims=." %%a in ("%%v") do (
                if %%a GEQ 3 if %%b GEQ 11 set "PY=py -3"
            )
        )
    )
)

if "!PY!"=="" (
    for /d %%d in ("%LOCALAPPDATA%\Programs\Python\Python3*") do (
        if "!PY!"=="" if exist "%%d\python.exe" set "PY=%%d\python.exe"
    )
)

if "!PY!"=="" (
    echo.
    echo  [ERROR] Python 3.11+ not found.
    echo  Install: https://www.python.org/downloads/
    echo.
    pause
    exit /b 1
)
echo  [1/5] Python OK: !PY!

:: ================================================================
::  STEP 2  uv
:: ================================================================
echo  [2/5] Checking uv...
set "UV="

uv --version 2>NUL
if !ERRORLEVEL! EQU 0 set "UV=uv"

if "!UV!"=="" if exist "%LOCALAPPDATA%\uv\bin\uv.exe"    set "UV=%LOCALAPPDATA%\uv\bin\uv.exe"
if "!UV!"=="" if exist "%USERPROFILE%\.local\bin\uv.exe" set "UV=%USERPROFILE%\.local\bin\uv.exe"
if "!UV!"=="" if exist "%USERPROFILE%\.cargo\bin\uv.exe" set "UV=%USERPROFILE%\.cargo\bin\uv.exe"
if "!UV!"=="" if exist "%APPDATA%\uv\uv.exe"             set "UV=%APPDATA%\uv\uv.exe"

if "!UV!"=="" (
    echo  [install] Installing uv via PowerShell...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex"
    if exist "%LOCALAPPDATA%\uv\bin\uv.exe"    set "UV=%LOCALAPPDATA%\uv\bin\uv.exe"
    if "!UV!"=="" if exist "%USERPROFILE%\.local\bin\uv.exe" set "UV=%USERPROFILE%\.local\bin\uv.exe"
)

if "!UV!"=="" (
    echo  [fallback] pip install uv...
    !PY! -m pip install uv -q
    if !ERRORLEVEL! EQU 0 set "UV=!PY! -m uv"
)

if "!UV!"=="" (
    echo.
    echo  [ERROR] Cannot install uv. Run: pip install uv
    echo.
    pause
    exit /b 1
)
echo  [2/5] uv OK: !UV!

:: ================================================================
::  STEP 3  .env.local
:: ================================================================
echo  [3/5] Checking config...
if not exist ".env.local" (
    if exist "env.template" (
        copy /Y "env.template" ".env.local" >NUL
        echo  [info] Created .env.local from env.template
    )
)
echo  [3/5] Config OK

:: ================================================================
::  STEP 4  Packages
:: ================================================================
echo  [4/5] Installing packages (first run: 2-5 min)...
if exist ".venv" (
    echo  [cleanup] Removing old .venv folder...
    rmdir /s /q ".venv"
)
!UV! sync --no-dev
if !ERRORLEVEL! NEQ 0 (
    echo.
    echo  [ERROR] Package install failed. Check internet connection.
    echo.
    pause
    exit /b 1
)
echo  [4/5] Packages OK

:: ================================================================
::  STEP 5  Launch
:: ================================================================
echo  [5/5] Launching...
echo.
echo  ================================================
echo   URL:  http://localhost:8765
echo   NOTE: Keep this window open (Ctrl+C to stop)
echo  ================================================
echo.

start /B "" cmd /c "timeout /t 5 /nobreak >NUL 2>&1 && start http://localhost:8765"
!UV! run python launcher.py

echo.
echo  Dashboard stopped. Close this window.
