#!/usr/bin/env bash
# Called by run_dashboard.bat / 실행.bat
export UV_PROJECT_ENVIRONMENT="$HOME/.venvs/tele-quant"
PROJECT_DIR="$HOME/tq"
# 포트 8765가 이미 사용 중이면 기존 프로세스 종료
fuser -k 8765/tcp 2>/dev/null && sleep 1
cd "$PROJECT_DIR"
exec uv run tele-quant dashboard --host 0.0.0.0 "$@"
