"""Cached market-data access with Yahoo Finance rate-limit fallbacks.

This module is the shared guardrail around yfinance. It keeps beginner-facing
dashboard runs quiet, detects Yahoo rate limits, and falls back to alternative
sources where practical:

- KR equities: pykrx, then FinanceDataReader
- Macro/index/FX/commodities: FinanceDataReader mappings
- US equities with keys: Alpha Vantage, FMP, then Finnhub quote snapshot
"""

from __future__ import annotations

import contextlib
import io
import logging
import os
import re
import time
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

log = logging.getLogger(__name__)

__all__ = [
    "MarketDataStatus",
    "get_balance_sheet",
    "get_cashflow",
    "get_earnings_history",
    "get_income_stmt",
    "get_ohlcv",
    "get_ohlcv_status",
    "get_ticker_info",
    "invalidate",
    "is_yfinance_rate_limited",
    "quiet_yfinance_logs",
    "yfinance_rate_limit_message",
]

_TTL: float = 900.0  # 15 minutes; reduce repeat requests during dashboard use.
_YF_RATE_LIMIT_COOLDOWN: float = 600.0
_YF_RATE_LIMIT_MARKERS = (
    "YFRateLimitError",
    "Too Many Requests",
    "Rate limited",
    "rate limit",
    "rate-limited",
)

_ohlcv_cache: dict[tuple[str, str, str], tuple[Any, float]] = {}
_ohlcv_status_cache: dict[tuple[str, str, str], MarketDataStatus] = {}
_info_cache: dict[str, tuple[dict[str, Any], float]] = {}
_stmt_cache: dict[tuple[str, str], tuple[Any, float]] = {}

_yf_rate_limited_until: float = 0.0
_last_yf_error: str = ""
_last_rate_limit_log: float = 0.0


@dataclass(slots=True)
class MarketDataStatus:
    status: str = "unknown"  # ok | fallback | rate_limited | unavailable | error
    source: str = ""
    message: str = ""
    rate_limited: bool = False
    fallback_used: bool = False


def quiet_yfinance_logs() -> None:
    """Hide noisy yfinance per-symbol ERROR logs from beginner-facing consoles."""
    for name in (
        "yfinance",
        "yfinance.base",
        "yfinance.cache",
        "yfinance.data",
        "yfinance.multi",
        "yfinance.scrapers.history",
        "yfinance.ticker",
        "yfinance.utils",
    ):
        yf_log = logging.getLogger(name)
        yf_log.setLevel(logging.CRITICAL)
        yf_log.disabled = True
        yf_log.propagate = False


quiet_yfinance_logs()


def _fresh(ts: float) -> bool:
    return (time.monotonic() - ts) < _TTL


def _is_kr_symbol(symbol: str) -> bool:
    return symbol.endswith((".KS", ".KQ", ".KN"))


def _is_us_equity_symbol(symbol: str) -> bool:
    return bool(re.fullmatch(r"[A-Z][A-Z0-9.-]{0,9}", symbol)) and not symbol.startswith("^")


def _is_yf_rate_limit(exc: BaseException | str) -> bool:
    text = f"{type(exc).__name__}: {exc}" if isinstance(exc, BaseException) else str(exc)
    return any(marker.lower() in text.lower() for marker in _YF_RATE_LIMIT_MARKERS)


def _mark_yf_rate_limited(exc: BaseException | str) -> None:
    global _last_rate_limit_log, _last_yf_error, _yf_rate_limited_until
    now = time.monotonic()
    _yf_rate_limited_until = max(_yf_rate_limited_until, now + _YF_RATE_LIMIT_COOLDOWN)
    _last_yf_error = str(exc)
    if now - _last_rate_limit_log > 60:
        log.info(r"\[market-data] Yahoo Finance rate limited; using fallback sources")
        _last_rate_limit_log = now


def is_yfinance_rate_limited() -> bool:
    return time.monotonic() < _yf_rate_limited_until


def yfinance_rate_limit_message() -> str:
    return "Yahoo 요청 제한 중입니다. 잠시 후 재시도하거나 대체 데이터/API를 설정하세요."


def _status_for(
    status: str,
    source: str = "",
    message: str = "",
    *,
    fallback_used: bool = False,
) -> MarketDataStatus:
    return MarketDataStatus(
        status=status,
        source=source,
        message=message,
        rate_limited=is_yfinance_rate_limited() or status == "rate_limited",
        fallback_used=fallback_used,
    )


def get_ohlcv_status(
    symbol: str,
    period: str = "3mo",
    interval: str = "1d",
) -> MarketDataStatus:
    return _ohlcv_status_cache.get((symbol, period, interval), MarketDataStatus())


def _normalize(df: Any) -> Any:
    if df is None:
        return None
    try:
        import pandas as pd

        if isinstance(df.columns, pd.MultiIndex):
            df = df.droplevel(1, axis=1)
    except Exception:
        pass
    return _normalize_ohlcv_columns(df)


def _normalize_ohlcv_columns(df: Any) -> Any:
    if df is None:
        return None
    try:
        rename = {
            "시가": "Open",
            "고가": "High",
            "저가": "Low",
            "종가": "Close",
            "거래량": "Volume",
        }
        df = df.rename(columns={c: rename.get(str(c), c) for c in df.columns}).copy()
        wanted = [c for c in ("Open", "High", "Low", "Close", "Volume") if c in df.columns]
        if "Close" not in wanted:
            return None
        df = df[wanted].sort_index()
        for col in wanted:
            df[col] = df[col].astype(float)
        df = df.dropna(subset=["Close"])
        if hasattr(df, "empty") and df.empty:
            return None
        return df
    except Exception as exc:
        log.debug("[stock_data_provider] normalize failed: %s", exc)
        return None


def _period_days(period: str) -> int:
    m = re.fullmatch(r"(\d+)(d|mo|y)", period.strip().lower())
    if not m:
        return 120
    n = int(m.group(1))
    unit = m.group(2)
    if unit == "d":
        return max(7, n + 5)
    if unit == "mo":
        return max(30, n * 32 + 10)
    return max(365, n * 370)


def _start_date(period: str) -> str:
    return (date.today() - timedelta(days=_period_days(period))).strftime("%Y-%m-%d")


def _get_setting(name: str, default: Any = "") -> Any:
    env_val = os.environ.get(name.upper())
    if env_val not in (None, ""):
        return env_val
    try:
        from tele_quant.settings import Settings

        return getattr(Settings(), name.lower(), default)
    except Exception:
        return default


def _is_enabled(name: str, default: bool = True) -> bool:
    raw = _get_setting(f"{name}_enabled", str(default))
    if isinstance(raw, bool):
        return raw
    return str(raw).lower() in ("1", "true", "yes", "on")


_FDR_SYMBOL_MAP = {
    "^GSPC": "US500",
    "^IXIC": "IXIC",
    "^DJI": "DJI",
    "^VIX": "VIX",
    "^KS11": "KS11",
    "^KQ11": "KQ11",
    "KRW=X": "USD/KRW",
    "CL=F": "CL=F",
    "GC=F": "GC=F",
    "^TNX": "US10YT",
}


def _fdr_symbol(symbol: str) -> str:
    if _is_kr_symbol(symbol):
        return symbol.split(".")[0]
    return _FDR_SYMBOL_MAP.get(symbol, symbol)


def _fetch_pykrx_ohlcv(symbol: str, period: str, interval: str) -> Any:
    if interval != "1d" or not _is_kr_symbol(symbol):
        return None
    bare = symbol.split(".")[0]
    end = date.today().strftime("%Y%m%d")
    start = (date.today() - timedelta(days=_period_days(period))).strftime("%Y%m%d")
    try:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            from pykrx import stock  # type: ignore[import-untyped]

            df = stock.get_market_ohlcv_by_date(start, end, bare)
        return _normalize_ohlcv_columns(df)
    except Exception as exc:
        log.debug("[stock_data_provider] pykrx fallback failed %s: %s", symbol, exc)
        return None


def _fetch_fdr_ohlcv(symbol: str, period: str, interval: str) -> Any:
    if interval != "1d":
        return None
    try:
        import FinanceDataReader as fdr  # type: ignore[import-untyped]

        code = _fdr_symbol(symbol)
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            df = fdr.DataReader(code, _start_date(period))
        return _normalize_ohlcv_columns(df)
    except Exception as exc:
        log.debug("[stock_data_provider] FDR fallback failed %s: %s", symbol, exc)
        return None


def _fetch_finnhub_quote(symbol: str) -> Any:
    if not _is_us_equity_symbol(symbol):
        return None
    if not _is_enabled("finnhub", False):
        return None
    api_key = str(_get_setting("finnhub_api_key", "") or "")
    if not api_key:
        return None
    try:
        import httpx
        import pandas as pd

        with httpx.Client(timeout=8.0) as client:
            resp = client.get(
                "https://finnhub.io/api/v1/quote",
                params={"symbol": symbol, "token": api_key},
            )
            resp.raise_for_status()
            data = resp.json()
        current = float(data.get("c") or 0)
        prev = float(data.get("pc") or 0)
        if current <= 0:
            return None
        today = pd.Timestamp(date.today())
        rows = []
        if prev > 0:
            rows.append(
                {"Date": today - pd.Timedelta(days=1), "Open": prev, "High": prev, "Low": prev, "Close": prev, "Volume": 0}
            )
        rows.append(
            {"Date": today, "Open": current, "High": current, "Low": current, "Close": current, "Volume": 0}
        )
        return pd.DataFrame(rows).set_index("Date")
    except Exception as exc:
        log.debug("[stock_data_provider] Finnhub quote fallback failed %s: %s", symbol, exc)
        return None


def _fetch_alpha_vantage_daily(symbol: str, period: str) -> Any:
    if not _is_us_equity_symbol(symbol):
        return None
    if not _is_enabled("alphavantage", False):
        return None
    api_key = str(_get_setting("alphavantage_api_key", "") or "")
    if not api_key:
        return None
    try:
        import httpx
        import pandas as pd

        with httpx.Client(timeout=12.0) as client:
            resp = client.get(
                "https://www.alphavantage.co/query",
                params={
                    "function": "TIME_SERIES_DAILY",
                    "symbol": symbol,
                    "outputsize": "compact",
                    "apikey": api_key,
                },
            )
            resp.raise_for_status()
            data = resp.json()
        series = data.get("Time Series (Daily)") or {}
        if not series:
            return None
        rows = []
        cutoff = date.today() - timedelta(days=_period_days(period))
        for day, vals in series.items():
            dt = date.fromisoformat(day)
            if dt < cutoff:
                continue
            rows.append(
                {
                    "Date": pd.Timestamp(dt),
                    "Open": float(vals["1. open"]),
                    "High": float(vals["2. high"]),
                    "Low": float(vals["3. low"]),
                    "Close": float(vals["4. close"]),
                    "Volume": float(vals.get("5. volume") or 0),
                }
            )
        if not rows:
            return None
        return pd.DataFrame(rows).set_index("Date").sort_index()
    except Exception as exc:
        log.debug("[stock_data_provider] Alpha Vantage fallback failed %s: %s", symbol, exc)
        return None


def _fetch_fmp_daily(symbol: str, period: str) -> Any:
    if not _is_us_equity_symbol(symbol):
        return None
    if not _is_enabled("fmp", False):
        return None
    api_key = str(_get_setting("fmp_api_key", "") or "")
    if not api_key:
        return None
    try:
        import httpx
        import pandas as pd

        with httpx.Client(timeout=12.0) as client:
            resp = client.get(
                f"https://financialmodelingprep.com/api/v3/historical-price-full/{symbol}",
                params={"timeseries": min(_period_days(period), 365), "apikey": api_key},
            )
            resp.raise_for_status()
            rows = resp.json().get("historical") or []
        if not rows:
            return None
        normalized = [
            {
                "Date": pd.Timestamp(row["date"]),
                "Open": row.get("open"),
                "High": row.get("high"),
                "Low": row.get("low"),
                "Close": row.get("close"),
                "Volume": row.get("volume") or 0,
            }
            for row in rows
            if row.get("date") and row.get("close") is not None
        ]
        if not normalized:
            return None
        return pd.DataFrame(normalized).set_index("Date").sort_index()
    except Exception as exc:
        log.debug("[stock_data_provider] FMP fallback failed %s: %s", symbol, exc)
        return None


def _fallback_ohlcv(symbol: str, period: str, interval: str) -> tuple[Any, str]:
    candidates: list[tuple[str, Any]] = []
    if _is_kr_symbol(symbol):
        candidates.extend(
            [
                ("pykrx", lambda: _fetch_pykrx_ohlcv(symbol, period, interval)),
                ("finance-datareader", lambda: _fetch_fdr_ohlcv(symbol, period, interval)),
            ]
        )
    else:
        candidates.append(("finance-datareader", lambda: _fetch_fdr_ohlcv(symbol, period, interval)))
        candidates.append(("alpha-vantage", lambda: _fetch_alpha_vantage_daily(symbol, period)))
        candidates.append(("fmp", lambda: _fetch_fmp_daily(symbol, period)))
        candidates.append(("finnhub", lambda: _fetch_finnhub_quote(symbol)))

    for source, getter in candidates:
        df = getter()
        df = _normalize_ohlcv_columns(df)
        if df is not None:
            return df, source
    return None, ""


def get_ohlcv(
    symbol: str,
    period: str = "3mo",
    interval: str = "1d",
) -> Any:
    """Return normalized OHLCV DataFrame. Never raises; returns None on failure."""
    key = (symbol, period, interval)
    cached = _ohlcv_cache.get(key)
    if cached is not None and _fresh(cached[1]):
        return cached[0]

    df: Any = None
    yf_error: BaseException | str | None = None
    if not is_yfinance_rate_limited() and _is_enabled("yfinance", True):
        try:
            quiet_yfinance_logs()
            import yfinance as yf

            if interval == "1d":
                raw = yf.download(symbol, period=period, auto_adjust=True, progress=False)
                df = _normalize(raw)
            else:
                raw = yf.Ticker(symbol).history(period=period, interval=interval, auto_adjust=True)
                df = _normalize(raw)
        except Exception as exc:
            yf_error = exc
            if _is_yf_rate_limit(exc):
                _mark_yf_rate_limited(exc)
            else:
                log.debug("[stock_data_provider] OHLCV failed %s %s/%s: %s", symbol, period, interval, exc)

    if df is not None:
        _ohlcv_cache[key] = (df, time.monotonic())
        _ohlcv_status_cache[key] = _status_for("ok", "yfinance")
        return df

    us_has_keyed_fallback = _is_us_equity_symbol(symbol) and (
        (_is_enabled("finnhub", False) and bool(_get_setting("finnhub_api_key", "")))
        or (_is_enabled("alphavantage", False) and bool(_get_setting("alphavantage_api_key", "")))
        or (_is_enabled("fmp", False) and bool(_get_setting("fmp_api_key", "")))
    )
    should_fallback = (
        is_yfinance_rate_limited()
        or _is_kr_symbol(symbol)
        or symbol in _FDR_SYMBOL_MAP
        or us_has_keyed_fallback
    )
    if should_fallback:
        fallback_df, source = _fallback_ohlcv(symbol, period, interval)
        if fallback_df is not None:
            _ohlcv_cache[key] = (fallback_df, time.monotonic())
            _ohlcv_status_cache[key] = _status_for(
                "fallback",
                source,
                "Yahoo 요청 제한 중이어서 대체 데이터 소스를 사용했습니다."
                if is_yfinance_rate_limited()
                else "Yahoo 데이터가 없어 대체 데이터 소스를 사용했습니다.",
                fallback_used=True,
            )
            return fallback_df

    message = yfinance_rate_limit_message()
    status = "rate_limited" if is_yfinance_rate_limited() else "unavailable"
    if not message:
        message = "데이터 없음"
    if yf_error and _is_yf_rate_limit(yf_error):
        status = "rate_limited"
        message = yfinance_rate_limit_message()
    _ohlcv_cache[key] = (None, time.monotonic())
    _ohlcv_status_cache[key] = _status_for(status, "yfinance", message)
    return None


def _finnhub_profile(symbol: str) -> dict[str, Any]:
    if not _is_us_equity_symbol(symbol):
        return {}
    if not _is_enabled("finnhub", False):
        return {}
    api_key = str(_get_setting("finnhub_api_key", "") or "")
    if not api_key:
        return {}
    try:
        import httpx

        with httpx.Client(timeout=8.0) as client:
            resp = client.get(
                "https://finnhub.io/api/v1/stock/profile2",
                params={"symbol": symbol, "token": api_key},
            )
            resp.raise_for_status()
            data = resp.json()
        if not isinstance(data, dict) or not data:
            return {}
        profile: dict[str, Any] = {
            "longName": data.get("name") or symbol,
            "shortName": data.get("ticker") or symbol,
            "currency": data.get("currency") or "USD",
        }
        market_cap = data.get("marketCapitalization")
        if market_cap:
            profile["marketCap"] = float(market_cap) * 1_000_000
        return profile
    except Exception as exc:
        log.debug("[stock_data_provider] Finnhub profile fallback failed %s: %s", symbol, exc)
        return {}


def get_ticker_info(symbol: str) -> dict[str, Any]:
    """Return yfinance-style Ticker.info dict. Never raises."""
    cached = _info_cache.get(symbol)
    if cached is not None and _fresh(cached[1]):
        return cached[0]

    info: dict[str, Any] = {}
    if not is_yfinance_rate_limited() and _is_enabled("yfinance", True):
        try:
            quiet_yfinance_logs()
            import yfinance as yf

            raw = yf.Ticker(symbol).info
            info = raw if isinstance(raw, dict) else {}
        except Exception as exc:
            if _is_yf_rate_limit(exc):
                _mark_yf_rate_limited(exc)
            else:
                log.debug("[stock_data_provider] info failed %s: %s", symbol, exc)

    if not info and is_yfinance_rate_limited():
        info = _finnhub_profile(symbol)

    _info_cache[symbol] = (info, time.monotonic())
    return info


def _get_statement(symbol: str, stmt_type: str) -> Any:
    key = (symbol, stmt_type)
    cached = _stmt_cache.get(key)
    if cached is not None and _fresh(cached[1]):
        return cached[0]

    df: Any = None
    if not is_yfinance_rate_limited() and _is_enabled("yfinance", True):
        try:
            quiet_yfinance_logs()
            import yfinance as yf

            t = yf.Ticker(symbol)
            df = getattr(t, stmt_type, None)
            if df is not None and hasattr(df, "empty") and df.empty:
                df = None
        except Exception as exc:
            if _is_yf_rate_limit(exc):
                _mark_yf_rate_limited(exc)
            else:
                log.debug("[stock_data_provider] %s failed %s: %s", stmt_type, symbol, exc)

    _stmt_cache[key] = (df, time.monotonic())
    return df


def get_income_stmt(symbol: str) -> Any:
    return _get_statement(symbol, "income_stmt")


def get_balance_sheet(symbol: str) -> Any:
    return _get_statement(symbol, "balance_sheet")


def get_cashflow(symbol: str) -> Any:
    return _get_statement(symbol, "cashflow")


def get_earnings_history(symbol: str) -> Any:
    return _get_statement(symbol, "earnings_history")


def invalidate(symbol: str | None = None) -> None:
    """Invalidate caches. symbol=None clears all and resets rate-limit state."""
    global _last_yf_error, _yf_rate_limited_until
    if symbol is None:
        _ohlcv_cache.clear()
        _ohlcv_status_cache.clear()
        _info_cache.clear()
        _stmt_cache.clear()
        _yf_rate_limited_until = 0.0
        _last_yf_error = ""
        return
    for k in [k for k in _ohlcv_cache if k[0] == symbol]:
        del _ohlcv_cache[k]
    for k in [k for k in _ohlcv_status_cache if k[0] == symbol]:
        del _ohlcv_status_cache[k]
    _info_cache.pop(symbol, None)
    for k in [k for k in _stmt_cache if k[0] == symbol]:
        del _stmt_cache[k]
