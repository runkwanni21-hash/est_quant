"""Stock Data Provider — yfinance 호출 캐싱 + 정규화 레이어.

모든 yfinance 호출을 이 모듈로 라우팅해 동일 프로세스 내 중복 네트워크 요청을 차단한다.
단일 /분석 실행 중 같은 심볼에 대한 .info / OHLCV 요청이 여러 모듈에서 발생하는 것을
TTL 5분 캐시로 흡수한다.

공개 정보 기반 리서치 보조. 투자 판단 책임은 사용자에게 있음.
"""

from __future__ import annotations

import logging
import time
from typing import Any

log = logging.getLogger(__name__)

__all__ = [
    "get_balance_sheet",
    "get_cashflow",
    "get_earnings_history",
    "get_income_stmt",
    "get_ohlcv",
    "get_ticker_info",
    "invalidate",
]

_TTL: float = 300.0  # 5분

# (symbol, period, interval) → (DataFrame | None, fetched_at)
_ohlcv_cache: dict[tuple[str, str, str], tuple[Any, float]] = {}
# symbol → (info_dict, fetched_at)
_info_cache: dict[str, tuple[dict[str, Any], float]] = {}
# (symbol, stmt_type) → (DataFrame | None, fetched_at)
_stmt_cache: dict[tuple[str, str], tuple[Any, float]] = {}


def _fresh(ts: float) -> bool:
    return (time.monotonic() - ts) < _TTL


def _normalize(df: Any) -> Any:
    """yf.download()가 반환하는 MultiIndex 컬럼을 단일 레벨로 정규화."""
    if df is None:
        return None
    try:
        import pandas as pd

        if isinstance(df.columns, pd.MultiIndex):
            df = df.droplevel(1, axis=1)
    except Exception:
        pass
    return df


def get_ohlcv(
    symbol: str,
    period: str = "3mo",
    interval: str = "1d",
) -> Any:
    """정규화된 OHLCV DataFrame 반환. 실패 시 None. 캐시 TTL 5분.

    Args:
        symbol:   티커 (예: 005930.KS, NVDA)
        period:   yfinance period 문자열 (예: "3mo", "10d", "1y")
        interval: "1d" (일봉, yf.download 사용) | "1h" (시간봉, Ticker.history 사용)
    """
    key = (symbol, period, interval)
    cached = _ohlcv_cache.get(key)
    if cached is not None and _fresh(cached[1]):
        return cached[0]

    df: Any = None
    try:
        import yfinance as yf

        if interval == "1d":
            raw = yf.download(symbol, period=period, auto_adjust=True, progress=False)
            df = _normalize(raw)
        else:
            raw = yf.Ticker(symbol).history(period=period, interval=interval, auto_adjust=True)
            df = raw if raw is not None else None

        if df is not None and hasattr(df, "empty") and df.empty:
            df = None
    except Exception as exc:
        log.debug("[stock_data_provider] OHLCV 실패 %s %s/%s: %s", symbol, period, interval, exc)

    _ohlcv_cache[key] = (df, time.monotonic())
    return df


def get_ticker_info(symbol: str) -> dict[str, Any]:
    """yfinance Ticker.info dict 반환. 실패 시 빈 dict. 캐시 TTL 5분."""
    cached = _info_cache.get(symbol)
    if cached is not None and _fresh(cached[1]):
        return cached[0]

    info: dict[str, Any] = {}
    try:
        import yfinance as yf

        raw = yf.Ticker(symbol).info
        info = raw if isinstance(raw, dict) else {}
    except Exception as exc:
        log.debug("[stock_data_provider] info 실패 %s: %s", symbol, exc)

    _info_cache[symbol] = (info, time.monotonic())
    return info


def _get_statement(symbol: str, stmt_type: str) -> Any:
    """연간 재무제표 DataFrame 반환. 캐시 TTL 5분."""
    key = (symbol, stmt_type)
    cached = _stmt_cache.get(key)
    if cached is not None and _fresh(cached[1]):
        return cached[0]

    df: Any = None
    try:
        import yfinance as yf

        t = yf.Ticker(symbol)
        df = getattr(t, stmt_type, None)
        if df is not None and hasattr(df, "empty") and df.empty:
            df = None
    except Exception as exc:
        log.debug("[stock_data_provider] %s 실패 %s: %s", stmt_type, symbol, exc)

    _stmt_cache[key] = (df, time.monotonic())
    return df


def get_income_stmt(symbol: str) -> Any:
    """연간 손익계산서 DataFrame. 실패 시 None."""
    return _get_statement(symbol, "income_stmt")


def get_balance_sheet(symbol: str) -> Any:
    """연간 재무상태표 DataFrame. 실패 시 None."""
    return _get_statement(symbol, "balance_sheet")


def get_cashflow(symbol: str) -> Any:
    """연간 현금흐름표 DataFrame. 실패 시 None."""
    return _get_statement(symbol, "cashflow")


def get_earnings_history(symbol: str) -> Any:
    """분기 EPS 실적 DataFrame (earnings_history). 실패 시 None."""
    return _get_statement(symbol, "earnings_history")


def invalidate(symbol: str | None = None) -> None:
    """캐시 무효화. symbol=None이면 전체 초기화."""
    if symbol is None:
        _ohlcv_cache.clear()
        _info_cache.clear()
        _stmt_cache.clear()
        return
    for k in [k for k in _ohlcv_cache if k[0] == symbol]:
        del _ohlcv_cache[k]
    _info_cache.pop(symbol, None)
    for k in [k for k in _stmt_cache if k[0] == symbol]:
        del _stmt_cache[k]
