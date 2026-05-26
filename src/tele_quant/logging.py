from __future__ import annotations

import logging
import sys
from contextlib import suppress

from rich.console import Console
from rich.logging import RichHandler


def _prefer_utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        with suppress(Exception):
            stream.reconfigure(encoding="utf-8", errors="replace")


_prefer_utf8_stdio()
console = Console(legacy_windows=False)


def configure_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(console=console, show_path=False, markup=True)],
    )
    # Suppress httpx/httpcore INFO logs that expose API URLs with secrets
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    try:
        from tele_quant.stock_data_provider import quiet_yfinance_logs

        quiet_yfinance_logs()
    except Exception:
        pass
