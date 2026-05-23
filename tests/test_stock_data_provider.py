"""Tests for stock_data_provider — caching + normalization."""
from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

import tele_quant.stock_data_provider as sdp

# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_df(n: int = 10) -> pd.DataFrame:
    idx = pd.date_range("2026-01-01", periods=n, freq="D")
    return pd.DataFrame(
        {"Open": 100.0, "High": 105.0, "Low": 95.0, "Close": 102.0, "Volume": 1_000_000},
        index=idx,
    )


def _make_multiindex_df(n: int = 5) -> pd.DataFrame:
    idx = pd.date_range("2026-01-01", periods=n, freq="D")
    cols = pd.MultiIndex.from_tuples(
        [("Open", "AAPL"), ("High", "AAPL"), ("Low", "AAPL"), ("Close", "AAPL"), ("Volume", "AAPL")]
    )
    return pd.DataFrame([[100, 105, 95, 102, 1_000_000]] * n, index=idx, columns=cols)


# ── Cache isolation — each test flushes the module-level cache ────────────────

@pytest.fixture(autouse=True)
def _flush_cache():
    sdp.invalidate()
    yield
    sdp.invalidate()


# ── get_ticker_info ───────────────────────────────────────────────────────────

def test_get_ticker_info_returns_dict():
    fake_info = {"trailingPE": 20.0, "sector": "Technology"}
    mock_ticker = MagicMock()
    mock_ticker.info = fake_info

    with patch("yfinance.Ticker", return_value=mock_ticker):
        result = sdp.get_ticker_info("AAPL")

    assert result == fake_info


def test_get_ticker_info_cached_second_call():
    """yfinance.Ticker should be called only once for two get_ticker_info calls."""
    mock_ticker = MagicMock()
    mock_ticker.info = {"trailingPE": 25.0}

    with patch("yfinance.Ticker", return_value=mock_ticker) as mock_cls:
        sdp.get_ticker_info("NVDA")
        sdp.get_ticker_info("NVDA")

    assert mock_cls.call_count == 1


def test_get_ticker_info_empty_on_error():
    with patch("yfinance.Ticker", side_effect=RuntimeError("network")):
        result = sdp.get_ticker_info("FAIL")

    assert result == {}


def test_get_ticker_info_different_symbols_separate_cache():
    mock_a = MagicMock()
    mock_a.info = {"sector": "A"}
    mock_b = MagicMock()
    mock_b.info = {"sector": "B"}

    with patch("yfinance.Ticker", side_effect=[mock_a, mock_b]):
        r_a = sdp.get_ticker_info("AAA")
        r_b = sdp.get_ticker_info("BBB")

    assert r_a["sector"] == "A"
    assert r_b["sector"] == "B"


# ── get_ohlcv — daily (1d) ────────────────────────────────────────────────────

def test_get_ohlcv_daily_returns_df():
    df = _make_df()

    with patch("yfinance.download", return_value=df):
        result = sdp.get_ohlcv("005930.KS", period="3mo", interval="1d")

    assert result is not None
    assert "Close" in result.columns


def test_get_ohlcv_daily_cached():
    df = _make_df()

    with patch("yfinance.download", return_value=df) as mock_dl:
        sdp.get_ohlcv("TSLA", period="3mo", interval="1d")
        sdp.get_ohlcv("TSLA", period="3mo", interval="1d")

    assert mock_dl.call_count == 1


def test_get_ohlcv_normalizes_multiindex():
    df = _make_multiindex_df()
    assert isinstance(df.columns, pd.MultiIndex)

    with patch("yfinance.download", return_value=df):
        result = sdp.get_ohlcv("AAPL", period="3mo", interval="1d")

    assert result is not None
    assert not isinstance(result.columns, pd.MultiIndex)
    assert "Close" in result.columns


def test_get_ohlcv_returns_none_on_empty():
    empty_df = pd.DataFrame()

    with patch("yfinance.download", return_value=empty_df):
        result = sdp.get_ohlcv("EMPTY", period="3mo", interval="1d")

    assert result is None


def test_get_ohlcv_returns_none_on_error():
    with patch("yfinance.download", side_effect=OSError("timeout")):
        result = sdp.get_ohlcv("ERR", period="1mo", interval="1d")

    assert result is None


# ── get_ohlcv — hourly (1h) ───────────────────────────────────────────────────

def test_get_ohlcv_hourly_uses_ticker_history():
    df = _make_df(40)
    mock_ticker = MagicMock()
    mock_ticker.history.return_value = df

    with patch("yfinance.Ticker", return_value=mock_ticker):
        result = sdp.get_ohlcv("NVDA", period="10d", interval="1h")

    assert result is not None
    mock_ticker.history.assert_called_once_with(period="10d", interval="1h", auto_adjust=True)


def test_get_ohlcv_hourly_cached():
    df = _make_df(40)
    mock_ticker = MagicMock()
    mock_ticker.history.return_value = df

    with patch("yfinance.Ticker", return_value=mock_ticker) as mock_cls:
        sdp.get_ohlcv("JPM", period="10d", interval="1h")
        sdp.get_ohlcv("JPM", period="10d", interval="1h")

    assert mock_cls.call_count == 1


def test_get_ohlcv_period_key_separate():
    """Different periods → separate cache entries."""
    df3m = _make_df(60)
    df1m = _make_df(21)

    with patch("yfinance.download", side_effect=[df3m, df1m]) as mock_dl:
        r3m = sdp.get_ohlcv("CRM", period="3mo", interval="1d")
        r1m = sdp.get_ohlcv("CRM", period="1mo", interval="1d")

    assert mock_dl.call_count == 2
    assert len(r3m) == 60
    assert len(r1m) == 21


# ── invalidate ────────────────────────────────────────────────────────────────

def test_invalidate_symbol_clears_only_that_symbol():
    df = _make_df()

    with patch("yfinance.download", return_value=df):
        sdp.get_ohlcv("AAA", period="3mo", interval="1d")
        sdp.get_ohlcv("BBB", period="3mo", interval="1d")

    sdp.invalidate("AAA")

    assert ("BBB", "3mo", "1d") in sdp._ohlcv_cache
    assert ("AAA", "3mo", "1d") not in sdp._ohlcv_cache


def test_invalidate_all_clears_everything():
    df = _make_df()
    with patch("yfinance.download", return_value=df):
        sdp.get_ohlcv("X", period="3mo", interval="1d")

    mock_ticker = MagicMock()
    mock_ticker.info = {"sector": "Y"}
    with patch("yfinance.Ticker", return_value=mock_ticker):
        sdp.get_ticker_info("Y")

    sdp.invalidate()
    assert len(sdp._ohlcv_cache) == 0
    assert len(sdp._info_cache) == 0


# ── TTL logic ─────────────────────────────────────────────────────────────────

def test_stale_cache_refetches():
    df1 = _make_df(5)
    df2 = _make_df(10)

    with patch("yfinance.download", side_effect=[df1, df2]) as mock_dl:
        sdp.get_ohlcv("STL", period="3mo", interval="1d")
        # Force TTL expiry by backdating the cache entry
        key = ("STL", "3mo", "1d")
        old_df, _ = sdp._ohlcv_cache[key]
        sdp._ohlcv_cache[key] = (old_df, time.monotonic() - sdp._TTL - 1)
        result2 = sdp.get_ohlcv("STL", period="3mo", interval="1d")

    assert mock_dl.call_count == 2
    assert len(result2) == 10
