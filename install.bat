@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul 2>&1
title Tele Quant - Install

echo.
echo  ================================================
echo   [Tele Quant] Beginner-Proof Installer
echo  ================================================
echo.

:: 1. Check uv
echo  [1/4] Checking uv...
set "UV_EXE="
where uv >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    set "UV_EXE=uv"
) else (
    if exist "%LOCALAPPDATA%\uv\bin\uv.exe" (
        set "UV_EXE=%LOCALAPPDATA%\uv\bin\uv.exe"
    ) else if exist "%USERPROFILE%\.local\bin\uv.exe" (
        set "UV_EXE=%USERPROFILE%\.local\bin\uv.exe"
    ) else if exist "%USERPROFILE%\.cargo\bin\uv.exe" (
        set "UV_EXE=%USERPROFILE%\.cargo\bin\uv.exe"
    )
)

if "!UV_EXE!"=="" (
    echo  [info] uv not found. Installing via PowerShell...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex"
    set "UV_EXE=%LOCALAPPDATA%\uv\bin\uv.exe"
    if not exist "!UV_EXE!" (
        echo  [ERROR] uv installation failed. Please install uv manually: https://astral.sh/uv
        pause
        exit /b 1
    )
)
echo  [1/4] uv OK: !UV_EXE!

:: 2. Install Python 3.12
echo  [2/4] Ensuring Python 3.12...
"!UV_EXE!" python install 3.12
if %ERRORLEVEL% NEQ 0 (
    echo  [ERROR] Python 3.12 installation failed.
    pause
    exit /b 1
)
echo  [2/4] Python 3.12 OK

:: 3. Sync dependencies
echo  [3/4] Installing dependencies (this may take 1-3 min)...
"!UV_EXE!" sync --all-extras --link-mode copy
if %ERRORLEVEL% NEQ 0 (
    echo  [ERROR] uv sync failed.
    pause
    exit /b 1
)
echo  [3/4] Dependencies OK

:: 4. Finalizing
echo  [4/4] Installation complete!
echo.
echo  Next steps:
echo   1. Edit .env.local with your API keys (created automatically if missing)
echo   2. Run auth_telegram.bat to log in
echo   3. Run run.bat to start the dashboard
echo.
pause
