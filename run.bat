@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul 2>&1
title Tele Quant - Dashboard Runner

echo.
echo  ================================================
echo   [Tele Quant] Dashboard Runner
echo  ================================================
echo.

:: 1. Ensure directories exist
if not exist "data\private" (
    echo  [info] Creating data\private directory...
    mkdir "data\private"
)
if not exist "logs" (
    echo  [info] Creating logs directory...
    mkdir "logs"
)

:: 2. Check config
if not exist ".env.local" (
    echo  [warning] .env.local not found!
    if exist "env.example" (
        echo  [info] Copying env.example to .env.local...
        copy "env.example" ".env.local" >nul
        echo  [info] Opening .env.local for editing. Please enter your API keys.
        start notepad ".env.local"
        echo.
        echo  ================================================
        echo   STOP: Please enter your API keys in Notepad,
        echo   SAVE the file, and then come back here.
        echo  ================================================
        echo.
        pause
    ) else (
        echo  [ERROR] env.example missing! Cannot create .env.local.
        pause
        exit /b 1
    )
)

:: 3. Launch Dashboard
echo  [info] Starting browser at http://127.0.0.1:8765...
start http://127.0.0.1:8765

echo  [info] Launching Tele Quant Dashboard...
echo  (Keep this window open while using the dashboard)
echo.

uv run python launcher.py

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo  [ERROR] Dashboard exited with error code %ERRORLEVEL%.
    echo  Make sure you have run install.bat first.
    pause
)
