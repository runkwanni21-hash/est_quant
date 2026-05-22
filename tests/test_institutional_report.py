"""Tests for analysis/report_models.py and report_builder.py."""

from __future__ import annotations

from unittest.mock import patch

from tele_quant.analysis.report_models import (
    AnalystConsensus,
    ChainCandidate,
    InstitutionalFlowSignal,
    InstitutionalInvestmentReport,
    ReportEvidence,
    SwingReportScore,
    TechnicalAccumulationSignal,
)

# ── 모델 기본값 ────────────────────────────────────────────────────────────────


def test_report_evidence_defaults():
    ev = ReportEvidence(title="테스트 뉴스")
    assert ev.title == "테스트 뉴스"
    assert ev.polarity == "NEUTRAL"
    assert ev.confidence == "MEDIUM"


def test_analyst_consensus_defaults():
    c = AnalystConsensus()
    assert c.report_count == 0
    assert c.target_mean is None
    assert c.opinion_label == "확인 제한"


def test_technical_accumulation_signal_defaults():
    sig = TechnicalAccumulationSignal()
    assert sig.score == 0.0
    assert sig.overheat is False
    assert sig.patterns == []


def test_institutional_flow_signal_defaults():
    flow = InstitutionalFlowSignal()
    assert flow.flow_level == "MEDIUM"
    assert flow.flow_score == 0.0
    assert flow.data_source == "proxy"


def test_chain_candidate_watch_only_low():
    cand = ChainCandidate(symbol="TEST", confidence="LOW", watch_only=True)
    assert cand.watch_only is True


def test_swing_score_grade():
    sc = SwingReportScore(total=82.0)
    sc.grade = "우선관찰 A"
    assert sc.grade == "우선관찰 A"


def test_institutional_report_defaults():
    rpt = InstitutionalInvestmentReport(symbol="NVDA", market="US")
    assert rpt.symbol == "NVDA"
    assert rpt.error == ""
    assert rpt.chain_beneficiaries == []


# ── 금지 표현 없음 검증 ───────────────────────────────────────────────────────


_FORBIDDEN = [
    "매수 권장", "매도 권장", "확정 수익", "기관 매집 확정",
    "수혜 확정", "피해 확정", "자동매매",
]


def _check_text(text: str) -> list[str]:
    return [w for w in _FORBIDDEN if w in text]


def test_chain_candidate_no_forbidden_in_reason():
    cand = ChainCandidate(
        symbol="005930.KS",
        name="삼성전자",
        connection_reason="고객사 수요 연동 — 수혜 가능성",
    )
    assert _check_text(cand.connection_reason) == []


def test_flow_signal_level_values():
    for level in ("HIGH", "MEDIUM", "LOW"):
        flow = InstitutionalFlowSignal(flow_level=level)
        assert flow.flow_level == level


# ── report_builder (단위 테스트 — yfinance mock) ──────────────────────────────


def _make_mock_ohlcv():
    import numpy as np
    import pandas as pd

    dates = pd.date_range("2025-01-01", periods=60, freq="B")
    close = pd.Series(np.linspace(100, 120, 60), index=dates)
    vol = pd.Series([1_000_000] * 60, index=dates)
    df = pd.DataFrame({"Open": close, "High": close * 1.01, "Low": close * 0.99,
                        "Close": close, "Volume": vol})
    df.index = dates
    return df


def test_build_institutional_report_partial():
    """report_builder가 yfinance 실패해도 부분 결과 반환."""
    mock_df = _make_mock_ohlcv()

    with (
        patch("tele_quant.stock_data_provider.get_ohlcv", return_value=mock_df),
        patch("tele_quant.stock_data_provider.get_ticker_info", return_value={}),
    ):
        from tele_quant.analysis.report_builder import build_institutional_report

        rpt = build_institutional_report("NVDA", "US", store=None, deep=False)
        assert rpt.symbol == "NVDA"
        assert rpt.market == "US"
        assert isinstance(rpt.score, SwingReportScore)
        assert 0 <= rpt.score.total <= 100
        # 금지 표현 없음
        assert _check_text(rpt.one_line_conclusion) == []


def test_build_institutional_report_grade_enum():
    """점수 등급이 허용 문자열인지 확인."""
    mock_df = _make_mock_ohlcv()
    with (
        patch("tele_quant.stock_data_provider.get_ohlcv", return_value=mock_df),
        patch("tele_quant.stock_data_provider.get_ticker_info", return_value={}),
    ):
        from tele_quant.analysis.report_builder import build_institutional_report

        rpt = build_institutional_report("AAPL", "US", store=None)
        allowed_grades = {"우선관찰 A", "관찰 B", "조건부 관찰 C", "보류"}
        assert rpt.score.grade in allowed_grades


def test_build_institutional_report_no_store():
    """store=None이어도 동작."""
    mock_df = _make_mock_ohlcv()
    with (
        patch("tele_quant.stock_data_provider.get_ohlcv", return_value=mock_df),
        patch("tele_quant.stock_data_provider.get_ticker_info", return_value={}),
    ):
        from tele_quant.analysis.report_builder import build_institutional_report

        rpt = build_institutional_report("TSLA", "US", store=None)
        assert rpt.symbol == "TSLA"
