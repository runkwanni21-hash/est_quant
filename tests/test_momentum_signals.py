"""Tests for momentum_signals.py."""

from __future__ import annotations

from unittest.mock import patch

import pandas as pd
import pytest

from tele_quant.momentum_signals import (
    MomentumSignals,
    _dtc_label,
    _rs_label,
    _vol_label,
    fetch_momentum_signals,
    format_momentum_signals,
)

# ── Label helpers ─────────────────────────────────────────────────────────────


class TestRsLabel:
    def test_very_strong(self):
        assert _rs_label(15) == "매우 강함"

    def test_strong(self):
        assert _rs_label(5) == "강함"

    def test_neutral(self):
        assert _rs_label(0) == "중립"

    def test_weak(self):
        assert _rs_label(-5) == "약함"

    def test_very_weak(self):
        assert _rs_label(-15) == "매우 약함"

    def test_none(self):
        assert _rs_label(None) == ""


class TestVolLabel:
    def test_surge(self):
        assert "급증" in _vol_label(3.5)

    def test_increase(self):
        assert _vol_label(2.0) == "증가"

    def test_normal(self):
        assert _vol_label(1.0) == "보통"

    def test_decrease(self):
        assert _vol_label(0.5) == "감소"

    def test_none(self):
        assert _vol_label(None) == ""


class TestDtcLabel:
    def test_explosive(self):
        assert "폭발위험" in _dtc_label(12)

    def test_high(self):
        assert "높음" in _dtc_label(7)

    def test_normal(self):
        assert "보통" in _dtc_label(3)

    def test_low(self):
        assert "낮음" in _dtc_label(1)

    def test_none(self):
        assert _dtc_label(None) == ""


# ── Fetch ─────────────────────────────────────────────────────────────────────


def _make_ohlcv(n: int = 65, base: float = 100.0) -> pd.DataFrame:
    import numpy as np

    dates = pd.date_range("2024-01-01", periods=n, freq="B")
    prices = base + np.linspace(0, 20, n)
    vol = [1_000_000 + i * 10_000 for i in range(n)]
    return pd.DataFrame({"Close": prices, "Volume": vol}, index=dates)


class TestFetchMomentumSignals:
    def _good_info(self) -> dict:
        return {
            "sharesShort": 10_000_000,
            "averageVolume10days": 5_000_000,
            "totalCash": 50_000_000_000,
            "totalDebt": 10_000_000_000,
            "sharesOutstanding": 2_000_000_000,
        }

    def test_returns_momentum_signals(self):
        df = _make_ohlcv()
        with (
            patch("tele_quant.stock_data_provider.get_ohlcv", return_value=df),
            patch("tele_quant.stock_data_provider.get_ticker_info", return_value=self._good_info()),
        ):
            sig = fetch_momentum_signals("NVDA")
        assert isinstance(sig, MomentumSignals)

    def test_52w_position_calculated(self):
        df = _make_ohlcv()
        with (
            patch("tele_quant.stock_data_provider.get_ohlcv", return_value=df),
            patch("tele_quant.stock_data_provider.get_ticker_info", return_value=self._good_info()),
        ):
            sig = fetch_momentum_signals("NVDA")
        assert sig.week52_pos_pct is not None
        assert 0 <= sig.week52_pos_pct <= 100

    def test_vol_surge_calculated(self):
        df = _make_ohlcv()
        with (
            patch("tele_quant.stock_data_provider.get_ohlcv", return_value=df),
            patch("tele_quant.stock_data_provider.get_ticker_info", return_value=self._good_info()),
        ):
            sig = fetch_momentum_signals("NVDA")
        assert sig.vol_surge_ratio is not None

    def test_dtc_calculated(self):
        df = _make_ohlcv()
        with (
            patch("tele_quant.stock_data_provider.get_ohlcv", return_value=df),
            patch("tele_quant.stock_data_provider.get_ticker_info", return_value=self._good_info()),
        ):
            sig = fetch_momentum_signals("NVDA")
        assert sig.dtc == pytest.approx(2.0)

    def test_net_cash_positive(self):
        df = _make_ohlcv()
        with (
            patch("tele_quant.stock_data_provider.get_ohlcv", return_value=df),
            patch("tele_quant.stock_data_provider.get_ticker_info", return_value=self._good_info()),
        ):
            sig = fetch_momentum_signals("NVDA")
        assert sig.net_cash_per_share is not None
        assert sig.net_cash_per_share > 0
        assert sig.net_cash_label == "순현금 +"

    def test_no_data_returns_empty(self):
        with (
            patch("tele_quant.stock_data_provider.get_ohlcv", return_value=None),
            patch("tele_quant.stock_data_provider.get_ticker_info", return_value={}),
        ):
            sig = fetch_momentum_signals("NODATA")
        assert sig.week52_pos_pct is None

    def test_exception_handled(self):
        with patch("tele_quant.stock_data_provider.get_ohlcv", side_effect=RuntimeError("err")):
            sig = fetch_momentum_signals("ERR")
        assert isinstance(sig, MomentumSignals)
        assert sig.warnings


# ── Format ────────────────────────────────────────────────────────────────────


class TestFormatMomentumSignals:
    def _sig(self) -> MomentumSignals:
        sig = MomentumSignals(symbol="NVDA")
        sig.rs_1m_pct = 5.2
        sig.rs_3m_pct = 12.4
        sig.rs_label = "강함"
        sig.vol_surge_ratio = 2.3
        sig.vol_label = "증가"
        sig.week52_pos_pct = 92.0
        sig.is_breakout = True
        sig.dtc = 3.5
        sig.dtc_label = "보통(2-5일)"
        sig.net_cash_per_share = 12.34
        sig.net_cash_label = "순현금 +"
        return sig

    def test_rs_in_output(self):
        text = format_momentum_signals(self._sig())
        assert "상대강도" in text

    def test_vol_in_output(self):
        text = format_momentum_signals(self._sig())
        assert "거래량" in text

    def test_breakout_flagged(self):
        text = format_momentum_signals(self._sig())
        assert "돌파" in text

    def test_dtc_in_output(self):
        text = format_momentum_signals(self._sig())
        assert "Short DTC" in text

    def test_net_cash_in_output(self):
        text = format_momentum_signals(self._sig())
        assert "순현금" in text

    def test_empty_signal_returns_empty(self):
        sig = MomentumSignals(symbol="X")
        assert format_momentum_signals(sig) == ""
