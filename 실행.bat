@echo off
chcp 65001 >nul 2>&1
cd /d "%~dp0"

set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "UV_LINK_MODE=copy"

title Tele Quant Dashboard

echo.
echo ================================================
echo  Tele Quant - Dashboard Launcher
echo ================================================
echo  Folder: %CD%
echo.

echo [1/5] Preparing folders...
if exist "data" goto data_ok
mkdir "data"
:data_ok
if exist "data\private" goto private_ok
mkdir "data\private"
:private_ok
if exist "logs" goto logs_ok
mkdir "logs"
:logs_ok

echo [2/5] Checking .env.local...
if exist ".env.local" goto env_ok

if exist "env.example" (
    copy /Y "env.example" ".env.local" >nul
    goto env_created
)

if exist "env.template" (
    copy /Y "env.template" ".env.local" >nul
    goto env_created
)

echo.
echo [ERROR] env.example or env.template was not found.
echo Please make sure this file is in the est_quant project root folder.
echo.
pause
exit /b 1

:env_created
echo.
echo FIRST RUN:
echo .env.local was created.
echo Notepad will open now.
echo Fill only the keys you want to use, save the file, close Notepad,
echo then run this bat file again.
echo.
start "" notepad ".env.local"
pause
exit /b 0

:env_ok
echo [2/5] .env.local OK

echo [3/5] Checking uv...
where uv >nul 2>&1
if %ERRORLEVEL% EQU 0 goto uv_ok

echo uv was not found. Installing uv with PowerShell...
powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex"

set "PATH=%LOCALAPPDATA%\uv\bin;%USERPROFILE%\.local\bin;%USERPROFILE%\.cargo\bin;%PATH%"

where uv >nul 2>&1
if %ERRORLEVEL% EQU 0 goto uv_ok

echo.
echo [ERROR] uv installation failed.
echo Try opening a new Command Prompt, then run this file again.
echo.
pause
exit /b 1

:uv_ok
echo [3/5] uv OK

echo [4/5] Installing or updating packages...
uv sync --no-dev --link-mode copy
if %ERRORLEVEL% EQU 0 goto sync_ok

echo.
echo [ERROR] Package installation failed.
echo Check the error above, then run this file again.
echo.
pause
exit /b 1

:sync_ok
echo [4/5] Packages OK

echo [5/5] Launching dashboard...
echo.
echo launcher.py will open the browser after the server starts.
echo If port 8765 is busy, it will choose another port and print the real URL.
echo.
uv run python launcher.py

echo.
echo Dashboard stopped.
pause
exit /b 0
