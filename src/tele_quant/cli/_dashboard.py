"""대시보드 CLI 명령 — tele-quant dashboard."""

from __future__ import annotations

import logging
from typing import Annotated

import typer

from tele_quant.cli._app import app
from tele_quant.cli._common import console

_YF_NOISE = (
    "HTTP Error 401",
    "possibly delisted",
    "no price data found",
    "No data found",
    "1 Failed download",
    "Failed download",
)


class _SuppressYFNoise(logging.Filter):
    """yfinance가 자체 로깅하는 예상된 데이터 부재·인증 에러를 억제한다.

    stock_data_provider / macro_pulse 에서 이미 None 반환으로 처리하므로
    ERROR 레벨로 콘솔에 노출될 필요가 없다.
    """
    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        return not any(pat in msg for pat in _YF_NOISE)


@app.command("dashboard")
def dashboard_cmd(
    host: Annotated[str, typer.Option("--host", help="바인딩 주소")] = "127.0.0.1",
    port: Annotated[int, typer.Option("--port", help="포트 번호")] = 8765,
    reload: Annotated[bool, typer.Option("--reload/--no-reload", help="개발 모드 자동 재시작")] = False,
) -> None:
    """웹 대시보드 실행 — 텔레그램 없이 브라우저에서 바로 투자 분석.

    브라우저에서 http://localhost:8765 로 접속하세요.

    기능:
      - 매크로 지표 (VIX / 10Y / USD/KRW / S&P / KOSPI / Gold / WTI / DXY)
      - 워치리스트 빠른 스크리너 (30초 내, 병렬 수집)
      - 종목 즉석 전체 분석 (/분석 과 동일)
      - 4H 퀀터멘탈 브리핑 미리보기

    Example:
        uv run tele-quant dashboard
        uv run tele-quant dashboard --port 9000
    """
    try:
        import uvicorn
    except ImportError:
        console.print(
            "[red]uvicorn이 설치되어 있지 않습니다.[/red]\n"
            "  uv add fastapi 'uvicorn[standard]'\n"
            "  또는: pip install fastapi 'uvicorn[standard]'"
        )
        raise SystemExit(1) from None

    logging.getLogger("yfinance").addFilter(_SuppressYFNoise())

    try:
        from tele_quant.dashboard.app import create_app
        dash_app = create_app()
    except ImportError as exc:
        console.print(f"[red]대시보드 초기화 실패: {exc}[/red]")
        raise SystemExit(1) from exc

    url = f"http://{host}:{port}"
    console.print("[bold green]✓ Tele Quant Dashboard 시작[/bold green]")
    console.print(f"  브라우저에서 열기: [bold cyan]{url}[/bold cyan]")
    console.print("  종료: Ctrl+C")
    console.print()

    uvicorn.run(
        dash_app,
        host=host,
        port=port,
        reload=reload,
        log_level="warning",
    )
