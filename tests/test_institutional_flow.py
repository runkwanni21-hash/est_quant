"""Tests for analysis/institutional_flow.py."""

from __future__ import annotations

from unittest.mock import patch

import numpy as np
import pandas as pd


def _make_df(n: int = 40) -> pd.DataFrame:
    dates = pd.date_range("2025-01-01", periods=n, freq="B")
    close = pd.Series(np.linspace(50000, 55000, n), index=dates)
    vol = pd.Series([500_000] * n, index=dates)
    df = pd.DataFrame({"Open": close, "High": close * 1.01, "Low": close * 0.99,
                        "Close": close, "Volume": vol})
    return df


# ── _obv_proxy ────────────────────────────────────────────────────────────────


def test_obv_proxy_flat_price():
    from tele_quant.analysis.institutional_flow import _obv_proxy

    df = _make_df(40)
    # 가격이 완만히 상승 → OBV 상승 추세
    with patch("tele_quant.stock_data_provider.get_ohlcv", return_value=df):
        result = _obv_proxy("005930.KS")
    assert result["obv_slope"] in ("UP", "DOWN", "FLAT")
    assert isinstance(result["price_obv_divergence"], bool)
    assert isinstance(result["bb_squeeze_recovery"], bool)


def test_obv_proxy_no_data():
    from tele_quant.analysis.institutional_flow import _obv_proxy

    with patch("tele_quant.stock_data_provider.get_ohlcv", return_value=None):
        result = _obv_proxy("FAKE")
    assert result["obv_slope"] == "FLAT"
    assert result["price_obv_divergence"] is False


# ── _compute_flow_score ───────────────────────────────────────────────────────


def test_flow_score_high():
    from tele_quant.analysis.institutional_flow import _compute_flow_score

    krx = {
        "inst_net_5d": 200.0,
        "inst_net_20d": 500.0,
        "foreign_net_5d": 100.0,
        "foreign_net_20d": 300.0,
        "inst_consecutive_buy": 6,
        "inst_consecutive_sell": 0,
        "foreign_consecutive_buy": 4,
    }
    proxy = {"obv_slope": "UP", "price_obv_divergence": True, "bb_squeeze_recovery": True}
    score, level, notes = _compute_flow_score(krx, proxy, rsi=55.0, ret_20d=8.0, vol_ratio=1.5, bb_pct=0.6)
    assert level == "HIGH"
    assert score >= 65
    assert len(notes) > 0


def test_flow_score_low_overheat():
    from tele_quant.analysis.institutional_flow import _compute_flow_score

    krx = {}
    proxy = {"obv_slope": "DOWN", "price_obv_divergence": False, "bb_squeeze_recovery": False}
    _score, level, notes = _compute_flow_score(krx, proxy, rsi=75.0, ret_20d=35.0, vol_ratio=6.0, bb_pct=0.98)
    assert level == "LOW"
    assert any("과열" in n or "추격" in n for n in notes)


# ── compute_institutional_flow ────────────────────────────────────────────────


def test_compute_institutional_flow_us():
    from tele_quant.analysis.institutional_flow import compute_institutional_flow

    df = _make_df(40)
    with patch("tele_quant.stock_data_provider.get_ohlcv", return_value=df):
        sig = compute_institutional_flow("NVDA", rsi=55.0)
    assert sig.flow_level in ("HIGH", "MEDIUM", "LOW")
    assert 0 <= sig.flow_score <= 100
    # US 종목은 pykrx 없으므로 inst_net_5d = None
    assert sig.inst_net_5d is None
    assert sig.data_source == "proxy"


def test_compute_institutional_flow_kr_pykrx_unavailable():
    """pykrx 없어도 graceful fallback."""
    from tele_quant.analysis.institutional_flow import compute_institutional_flow

    df = _make_df(40)
    with (
        patch("tele_quant.stock_data_provider.get_ohlcv", return_value=df),
        patch.dict("sys.modules", {"pykrx": None}),
    ):
        sig = compute_institutional_flow("005930.KS", rsi=50.0)
    assert sig.flow_level in ("HIGH", "MEDIUM", "LOW")


def test_compute_flow_forbidden_text():
    """출력에 '기관 매집 확정' 포함 안 됨."""
    from tele_quant.analysis.institutional_flow import compute_institutional_flow

    df = _make_df(40)
    with patch("tele_quant.stock_data_provider.get_ohlcv", return_value=df):
        sig = compute_institutional_flow("AAPL")
    all_notes = " ".join(sig.flow_notes)
    assert "기관 매집 확정" not in all_notes
