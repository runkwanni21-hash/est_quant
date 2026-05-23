"""Tests for analysis/chain_recommendation_engine.py."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd


def _make_df(n: int = 60) -> pd.DataFrame:
    dates = pd.date_range("2025-01-01", periods=n, freq="B")
    close = pd.Series(np.linspace(100, 120, n), index=dates)
    vol = pd.Series([1_000_000] * n, index=dates)
    df = pd.DataFrame({"Open": close, "High": close * 1.01, "Low": close * 0.99,
                        "Close": close, "Volume": vol})
    return df


# ── _classify_candidate ──────────────────────────────────────────────────────


def test_classify_beneficiary_type():
    from tele_quant.analysis.chain_recommendation_engine import _classify_candidate

    assert _classify_candidate("BENEFICIARY", "UP_LEADS_UP") == "beneficiary"
    assert _classify_candidate("CUSTOMER", "") == "beneficiary"


def test_classify_burden_type():
    from tele_quant.analysis.chain_recommendation_engine import _classify_candidate

    assert _classify_candidate("VICTIM", "UP_LEADS_DOWN") == "burden"
    assert _classify_candidate("INPUT_COST_VICTIM", "") == "burden"


def test_classify_peer_type():
    from tele_quant.analysis.chain_recommendation_engine import _classify_candidate

    assert _classify_candidate("PEER", "CORRELATED") == "peer"


# ── _lag_score ───────────────────────────────────────────────────────────────


def test_lag_score_1d():
    from tele_quant.analysis.chain_recommendation_engine import _lag_score

    assert _lag_score("1d") > _lag_score("1m")
    assert _lag_score("1d") > _lag_score("3m")


def test_lag_score_unknown():
    from tele_quant.analysis.chain_recommendation_engine import _lag_score

    assert _lag_score("") == 0
    assert _lag_score("unknown") == 0


# ── build_chain_candidates ────────────────────────────────────────────────────


def test_build_chain_candidates_no_store():
    """store=None, supply_chain fallback 없어도 빈 목록 반환."""
    from tele_quant.analysis.chain_recommendation_engine import build_chain_candidates

    df = _make_df()
    with (
        patch("tele_quant.stock_data_provider.get_ohlcv", return_value=df),
        patch("tele_quant.stock_data_provider.get_ticker_info", return_value={}),
        patch(
            "tele_quant.supply_chain_alpha.load_supply_chain_rules",
            side_effect=Exception("no rules"),
        ),
    ):
        bens, burdens, peers = build_chain_candidates("NVDA", "US", store=None)
    assert isinstance(bens, list)
    assert isinstance(burdens, list)
    assert isinstance(peers, list)


def test_build_chain_candidates_with_edges():
    """가짜 relation edges로 체인 후보 생성 확인."""
    from tele_quant.analysis.chain_recommendation_engine import build_chain_candidates

    mock_store = MagicMock()
    mock_store.get_all_relation_edges.return_value = [
        {
            "source_symbol": "NVDA",
            "target_symbol": "AMD",
            "relation_type": "PEER",
            "direction": "CORRELATED",
            "confidence": "HIGH",
            "expected_lag": "1d",
            "connection_reason": "동종 AI GPU",
            "relation_score": 0.8,
            "active": True,
        },
        {
            "source_symbol": "NVDA",
            "target_symbol": "TSM",
            "relation_type": "CUSTOMER",
            "direction": "UP_LEADS_UP",
            "confidence": "HIGH",
            "expected_lag": "3d",
            "connection_reason": "파운드리 고객사",
            "relation_score": 0.85,
            "active": True,
        },
    ]

    df = _make_df()
    with (
        patch("tele_quant.stock_data_provider.get_ohlcv", return_value=df),
        patch("tele_quant.stock_data_provider.get_ticker_info", return_value={}),
    ):
        bens, burdens, peers = build_chain_candidates("NVDA", "US", store=mock_store)

    all_cands = bens + burdens + peers
    assert len(all_cands) >= 1


def test_chain_candidate_low_confidence_watch_only():
    """LOW confidence → watch_only=True."""
    from tele_quant.analysis.chain_recommendation_engine import build_chain_candidates

    mock_store = MagicMock()
    mock_store.get_all_relation_edges.return_value = [
        {
            "source_symbol": "NVDA",
            "target_symbol": "INTC",
            "relation_type": "PEER",
            "direction": "CORRELATED",
            "confidence": "LOW",
            "expected_lag": "1w",
            "connection_reason": "경쟁사",
            "relation_score": 0.3,
            "active": True,
        },
    ]

    df = _make_df()
    with (
        patch("tele_quant.stock_data_provider.get_ohlcv", return_value=df),
        patch("tele_quant.stock_data_provider.get_ticker_info", return_value={}),
    ):
        bens, burdens, peers = build_chain_candidates("NVDA", "US", store=mock_store)

    all_cands = bens + burdens + peers
    # LOW confidence 후보 모두 watch_only=True
    for c in all_cands:
        if c.confidence == "LOW":
            assert c.watch_only is True


def test_chain_score_range():
    """chain_score는 0~100 범위."""
    from tele_quant.analysis.chain_recommendation_engine import build_chain_candidates

    mock_store = MagicMock()
    mock_store.get_all_relation_edges.return_value = [
        {
            "source_symbol": "AAPL",
            "target_symbol": "QCOM",
            "relation_type": "CUSTOMER",
            "direction": "UP_LEADS_UP",
            "confidence": "MEDIUM",
            "expected_lag": "5d",
            "connection_reason": "칩 공급사",
            "relation_score": 0.65,
            "active": True,
        },
    ]

    df = _make_df()
    with (
        patch("tele_quant.stock_data_provider.get_ohlcv", return_value=df),
        patch("tele_quant.stock_data_provider.get_ticker_info", return_value={}),
    ):
        bens, burdens, peers = build_chain_candidates("AAPL", "US", store=mock_store)

    for c in bens + burdens + peers:
        assert 0 <= c.chain_score <= 100


def test_chain_no_forbidden_text():
    """체인 후보 reason에 금지 표현 없음."""
    from tele_quant.analysis.chain_recommendation_engine import build_chain_candidates

    mock_store = MagicMock()
    mock_store.get_all_relation_edges.return_value = [
        {
            "source_symbol": "005930.KS",
            "target_symbol": "000660.KS",
            "relation_type": "BENEFICIARY",
            "direction": "UP_LEADS_UP",
            "confidence": "MEDIUM",
            "expected_lag": "1d",
            "connection_reason": "메모리 수혜 가능성",
            "relation_score": 0.7,
            "active": True,
        },
    ]

    df = _make_df()
    with (
        patch("tele_quant.stock_data_provider.get_ohlcv", return_value=df),
        patch("tele_quant.stock_data_provider.get_ticker_info", return_value={}),
    ):
        bens, burdens, peers = build_chain_candidates("005930.KS", "KR", store=mock_store)

    forbidden = ["수혜 확정", "피해 확정", "매수 권장"]
    for c in bens + burdens + peers:
        for w in forbidden:
            assert w not in c.connection_reason
