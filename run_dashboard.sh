#!/usr/bin/env bash
# WSL 터미널에서 실행: bash run_dashboard.sh
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
URL="http://localhost:8765"

echo ""
echo "  ============================================"
echo "   Tele Quant Dashboard"
echo "  ============================================"
echo "   브라우저 주소: $URL"
echo "   종료: Ctrl+C"
echo "  ============================================"
echo ""

cd "$PROJECT_DIR"

# 의존성 체크
if ! command -v uv &>/dev/null; then
    echo "[오류] uv가 설치되어 있지 않습니다."
    echo "  curl -LsSf https://astral.sh/uv/install.sh | sh"
    exit 1
fi

# 3초 후 브라우저 열기 (백그라운드)
(
    sleep 3
    # WSL → Windows 브라우저
    if command -v explorer.exe &>/dev/null; then
        explorer.exe "$URL" &>/dev/null
    elif command -v xdg-open &>/dev/null; then
        xdg-open "$URL" &>/dev/null
    fi
) &

# 대시보드 실행
exec uv run tele-quant dashboard
