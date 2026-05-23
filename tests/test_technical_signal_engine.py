"""Tests for analysis/technical_signal_engine.py."""

from __future__ import annotations

from unittest.mock import patch

import numpy as np
import pandas as pd


def _make_df(n: int = 60, trend: str = "up") -> pd.DataFrame:
    dates = pd.date_range("2025-01-01", periods=n, freq="B")
    if trend == "up":
        close = pd.Series(np.linspace(100, 130, n), index=dates)
    elif trend == "down":
        close = pd.Series(np.linspace(130, 100, n), index=dates)
    else:  # flat
        close = pd.Series([110.0] * n, index=dates)
    vol = pd.Series([1_500_000] * n, index=dates)
    df = pd.DataFrame({"Open": close, "High": close * 1.01, "Low": close * 0.99,
                        "Close": close, "Volume": vol})
    return df


# ── _rsi ────────────────────────────────────────────────────────────────────


def test_rsi_uptrend_high():
    from tele_quant.analysis.technical_signal_engine import _rsi

    df = _make_df(60, "up")
    rsi = _rsi(df["Close"])
    assert rsi is not None
    assert rsi > 60  # 상승추세 → RSI 높음


def test_rsi_downtrend_low():
    from tele_quant.analysis.technical_signal_engine import _rsi

    df = _make_df(60, "down")
    rsi = _rsi(df["Close"])
    assert rsi is not None
    assert rsi < 40


def test_rsi_insufficient_data():
    from tele_quant.analysis.technical_signal_engine import _rsi

    df = _make_df(10, "up")
    assert _rsi(df["Close"]) is None


# ── _obv_trend ────────────────────────────────────────────────────────────────


def test_obv_trend_up():
    from tele_quant.analysis.technical_signal_engine import _obv_trend

    df = _make_df(30, "up")
    assert _obv_trend(df) == "UP"


def test_obv_trend_down():
    from tele_quant.analysis.technical_signal_engine import _obv_trend

    df = _make_df(30, "down")
    assert _obv_trend(df) == "DOWN"


# ── _bollinger ────────────────────────────────────────────────────────────────


def test_bollinger_width_positive():
    from tele_quant.analysis.technical_signal_engine import _bollinger

    df = _make_df(30, "flat")
    bb = _bollinger(df)
    assert bb["width"] is not None
    assert bb["width"] >= 0


def test_bollinger_pct_range():
    from tele_quant.analysis.technical_signal_engine import _bollinger

    df = _make_df(30, "up")
    bb = _bollinger(df)
    # pct는 0~1 범위 대체로 유지
    if bb["pct"] is not None:
        # 강한 상승 추세에서 상단 초과 가능하므로 0 이상만 확인
        assert bb["pct"] >= -0.1


# ── _detect_overheat ─────────────────────────────────────────────────────────


def test_overheat_all_flags():
    from tele_quant.analysis.technical_signal_engine import _detect_overheat

    assert _detect_overheat(rsi=75, ret_20d=35, vol_ratio=4, bb_pct=0.97) is True


def test_no_overheat():
    from tele_quant.analysis.technical_signal_engine import _detect_overheat

    assert _detect_overheat(rsi=55, ret_20d=10, vol_ratio=1.5, bb_pct=0.5) is False


# ── compute_technical_accumulation_signal ─────────────────────────────────────


def test_compute_signal_up_trend():
    from tele_quant.analysis.technical_signal_engine import compute_technical_accumulation_signal

    df = _make_df(80, "up")
    with patch("tele_quant.stock_data_provider.get_ohlcv", return_value=df):
        sig = compute_technical_accumulation_signal("NVDA", period="6mo")
    assert sig.score >= 0
    assert sig.score <= 100
    assert sig.rsi_1d is not None


def test_compute_signal_no_data():
    from tele_quant.analysis.technical_signal_engine import compute_technical_accumulation_signal

    with patch("tele_quant.stock_data_provider.get_ohlcv", return_value=None):
        sig = compute_technical_accumulation_signal("FAKE")
    assert sig.score == 0.0
    assert sig.rsi_1d is None


def test_compute_signal_label_not_empty():
    from tele_quant.analysis.technical_signal_engine import compute_technical_accumulation_signal

    df = _make_df(60, "flat")
    with patch("tele_quant.stock_data_provider.get_ohlcv", return_value=df):
        sig = compute_technical_accumulation_signal("TEST")
    assert isinstance(sig.label, str)


def test_compute_signal_52w():
    from tele_quant.analysis.technical_signal_engine import compute_technical_accumulation_signal

    df = _make_df(260, "up")
    with patch("tele_quant.stock_data_provider.get_ohlcv", return_value=df):
        sig = compute_technical_accumulation_signal("NVDA")
    assert sig.w52_position_pct is not None
    assert 0 <= sig.w52_position_pct <= 100
