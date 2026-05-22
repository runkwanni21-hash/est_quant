"""Tests for analysis/analyst_consensus.py."""

from __future__ import annotations

from unittest.mock import patch

# ── _opinion_label ────────────────────────────────────────────────────────────


def test_opinion_label_buy_dominant():
    from tele_quant.analysis.analyst_consensus import _opinion_label

    assert _opinion_label(10, 2, 1, None) == "BUY 우세"


def test_opinion_label_sell_dominant():
    from tele_quant.analysis.analyst_consensus import _opinion_label

    assert _opinion_label(1, 2, 8, None) == "SELL 우세"


def test_opinion_label_hold():
    from tele_quant.analysis.analyst_consensus import _opinion_label

    assert _opinion_label(3, 6, 3, None) == "HOLD 우세"


def test_opinion_label_no_data():
    from tele_quant.analysis.analyst_consensus import _opinion_label

    assert _opinion_label(0, 0, 0, None) == "확인 제한"


def test_opinion_label_from_rec_mean():
    from tele_quant.analysis.analyst_consensus import _opinion_label

    assert _opinion_label(0, 0, 0, 1.5) == "BUY 우세"
    assert _opinion_label(0, 0, 0, 4.5) == "SELL 우세"
    assert _opinion_label(0, 0, 0, 3.0) == "HOLD 우세"


# ── _upside ──────────────────────────────────────────────────────────────────


def test_upside_positive():
    from tele_quant.analysis.analyst_consensus import _upside

    result = _upside(current=100.0, target_mean=120.0)
    assert result is not None
    assert abs(result - 20.0) < 0.01


def test_upside_none_inputs():
    from tele_quant.analysis.analyst_consensus import _upside

    assert _upside(None, 120.0) is None
    assert _upside(100.0, None) is None


# ── build_analyst_consensus ───────────────────────────────────────────────────


def test_build_consensus_yfinance_target():
    from tele_quant.analysis.analyst_consensus import build_analyst_consensus

    mock_info = {
        "targetMeanPrice": 200.0,
        "targetLowPrice": 150.0,
        "targetHighPrice": 250.0,
        "targetMedianPrice": 195.0,
        "currentPrice": 170.0,
        "numberOfAnalystOpinions": 25,
    }
    with patch("tele_quant.stock_data_provider.get_ticker_info", return_value=mock_info):
        cons = build_analyst_consensus("NVDA", store=None)
    assert cons.target_mean == 200.0
    assert cons.current_price == 170.0
    assert cons.upside_pct is not None
    assert abs(cons.upside_pct - (200 - 170) / 170 * 100) < 0.01
    assert cons.analyst_count == 25


def test_build_consensus_no_target():
    """목표가 없으면 '확인 제한'."""
    from tele_quant.analysis.analyst_consensus import build_analyst_consensus

    with patch("tele_quant.stock_data_provider.get_ticker_info", return_value={}):
        cons = build_analyst_consensus("UNKN", store=None)
    assert cons.target_mean is None
    assert "확인 제한" in cons.note


def test_build_consensus_no_forbidden():
    """컨센서스 출력에 금지 표현 없음."""
    from tele_quant.analysis.analyst_consensus import build_analyst_consensus

    forbidden = ["매수 권장", "매도 권장", "확정 수익"]
    with patch("tele_quant.stock_data_provider.get_ticker_info", return_value={}):
        cons = build_analyst_consensus("TEST", store=None)
    all_text = " ".join([
        cons.note, cons.opinion_label,
        *cons.bull_theses, *cons.bear_theses,
    ])
    assert all(w not in all_text for w in forbidden)
