@echo off
chcp 65001 >nul 2>&1
echo [Tele Quant] Authenticating Telegram...
uv run tele-quant auth
pause
