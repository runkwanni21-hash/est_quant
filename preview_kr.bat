@echo off
chcp 65001 >nul 2>&1
echo [Tele Quant] Generating KR Briefing Preview...
uv run tele-quant briefing --market KR --no-send
pause
