"""Tests for mispricing_detector.py."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from tele_quant.mispricing_detector import (
    MispricingResult,
    MispricingSignal,
    detect_mispricing,
    format_mispricing,
)

# ── 헬퍼 ──────────────────────────────────────────────────────────────────────

def _make_history(results_data: list[dict]) -> MagicMock:
    """EarningsHistory mock 생성."""
    mock = MagicMock()
    mock.data_limited = False
    rows = []
    for d in results_data:
        r = MagicMock()
        r.net_income_bn = d.get("net")
        r.operating_income_bn = d.get("op")
        r.revenue_bn = d.get("rev")
        r.revenue_yoy_pct = d.get("rev_yoy")
        rows.append(r)
    mock.results = rows
    return mock


def _make_surprise(quarters_data: list[dict]) -> MagicMock:
    """EarningsSurprise mock 생성."""
    mock = MagicMock()
    mock.symbol = "TEST"
    qs = []
    for d in quarters_data:
        q = MagicMock()
        q.surprise_pct = d.get("surprise")
        qs.append(q)
    mock.quarters = qs
    mock.beat_rate_pct = None
    return mock


# ── detect_mispricing 기본 ─────────────────────────────────────────────────────

class TestDetectMispricingBasic:
    def test_no_signals_returns_result(self):
        history = _make_history([
            {"net": 1.0, "op": 0.5, "rev": 10.0, "rev_yoy": 3.0},
            {"net": 1.2, "op": 0.6, "rev": 9.7, "rev_yoy": 2.0},
        ])
        surprise = _make_surprise([])
        with (
            patch("tele_quant.earnings_history.fetch_earnings_history", return_value=history),
            patch("tele_quant.earnings_surprise.fetch_earnings_surprise", return_value=surprise),
        ):
            result = detect_mispricing("TEST")
        assert isinstance(result, MispricingResult)
        assert result.conclusion == "해당없음"

    def test_returns_mispricing_result_type(self):
        history = _make_history([{"net": None, "op": None}])
        surprise = _make_surprise([])
        with (
            patch("tele_quant.earnings_history.fetch_earnings_history", return_value=history),
            patch("tele_quant.earnings_surprise.fetch_earnings_surprise", return_value=surprise),
        ):
            result = detect_mispricing("TEST")
        assert isinstance(result, MispricingResult)

    def test_price_position_stored(self):
        history = _make_history([])
        history.data_limited = True
        surprise = _make_surprise([])
        with (
            patch("tele_quant.earnings_history.fetch_earnings_history", return_value=history),
            patch("tele_quant.earnings_surprise.fetch_earnings_surprise", return_value=surprise),
        ):
            result = detect_mispricing("TEST", price_position_pct=25.0, price_6m_chg_pct=3.0)
        assert result.price_position_pct == 25.0
        assert result.price_6m_chg_pct == 3.0


# ── 흑자 턴어라운드 ───────────────────────────────────────────────────────────

class TestTurnaround:
    def _run(self, results_data: list[dict], **kwargs) -> MispricingResult:
        history = _make_history(results_data)
        surprise = _make_surprise([])
        with (
            patch("tele_quant.earnings_history.fetch_earnings_history", return_value=history),
            patch("tele_quant.earnings_surprise.fetch_earnings_surprise", return_value=surprise),
        ):
            return detect_mispricing("TEST", **kwargs)

    def test_net_income_turnaround_detected(self):
        result = self._run([
            {"net": 1.5, "op": 0.8},   # 최신: 흑자
            {"net": -0.5, "op": -0.2},  # 전년: 적자
        ])
        types = [s.signal_type for s in result.signals]
        assert "turnaround" in types

    def test_already_profitable_no_turnaround(self):
        result = self._run([
            {"net": 1.5, "op": 0.8},
            {"net": 1.0, "op": 0.5},
        ])
        types = [s.signal_type for s in result.signals]
        assert "turnaround" not in types

    def test_continued_loss_no_turnaround(self):
        result = self._run([
            {"net": -0.3, "op": -0.1},
            {"net": -0.5, "op": -0.2},
        ])
        types = [s.signal_type for s in result.signals]
        assert "turnaround" not in types

    def test_turnaround_with_low_price_position_gives_strong_score(self):
        result = self._run(
            [{"net": 2.0, "op": 1.0}, {"net": -1.0, "op": -0.5}],
            price_position_pct=15.0,
            price_6m_chg_pct=2.0,
        )
        assert result.total_score > 50
        assert result.conclusion in ("강한괴리", "괴리가능")


# ── 영업이익 급반등 ───────────────────────────────────────────────────────────

class TestOpRebound:
    def _run(self, results_data: list[dict]) -> MispricingResult:
        history = _make_history(results_data)
        surprise = _make_surprise([])
        with (
            patch("tele_quant.earnings_history.fetch_earnings_history", return_value=history),
            patch("tele_quant.earnings_surprise.fetch_earnings_surprise", return_value=surprise),
        ):
            return detect_mispricing("TEST")

    def test_op_rebound_50pct_detected(self):
        result = self._run([
            {"net": 1.0, "op": 1.5},   # +50% op
            {"net": 0.8, "op": 1.0},
        ])
        types = [s.signal_type for s in result.signals]
        assert "op_rebound" in types

    def test_small_op_growth_not_detected(self):
        result = self._run([
            {"net": 1.0, "op": 1.1},   # +10% op (부족)
            {"net": 0.9, "op": 1.0},
        ])
        types = [s.signal_type for s in result.signals]
        assert "op_rebound" not in types

    def test_op_loss_to_profit_detected(self):
        result = self._run([
            {"net": 0.5, "op": 0.8},
            {"net": -0.1, "op": -0.3},
        ])
        types = [s.signal_type for s in result.signals]
        assert "op_rebound" in types


# ── EPS 비트 연속 ─────────────────────────────────────────────────────────────

class TestBeatStreak:
    def _run(self, quarters: list[dict]) -> MispricingResult:
        history = _make_history([])
        history.data_limited = True
        surprise = _make_surprise(quarters)
        with (
            patch("tele_quant.earnings_history.fetch_earnings_history", return_value=history),
            patch("tele_quant.earnings_surprise.fetch_earnings_surprise", return_value=surprise),
        ):
            return detect_mispricing("TEST")

    def test_3q_beat_streak_detected(self):
        result = self._run([
            {"surprise": 8.0},
            {"surprise": 12.0},
            {"surprise": 5.0},
        ])
        types = [s.signal_type for s in result.signals]
        assert "beat_streak" in types

    def test_2q_beat_not_detected(self):
        result = self._run([
            {"surprise": 8.0},
            {"surprise": 5.0},
        ])
        types = [s.signal_type for s in result.signals]
        assert "beat_streak" not in types

    def test_miss_streak_not_detected(self):
        result = self._run([
            {"surprise": -5.0},
            {"surprise": -3.0},
            {"surprise": -2.0},
        ])
        types = [s.signal_type for s in result.signals]
        assert "beat_streak" not in types


# ── format_mispricing ─────────────────────────────────────────────────────────

class TestFormatMispricing:
    def test_empty_signals_returns_empty(self):
        result = MispricingResult(symbol="TEST", signals=[], conclusion="해당없음")
        assert format_mispricing(result) == ""

    def test_strong_signal_contains_label(self):
        result = MispricingResult(
            symbol="TEST",
            signals=[MispricingSignal("turnaround", "흑자 턴어라운드", 0.9, "적자→흑자 전환")],
            total_score=75.0,
            conclusion="강한괴리",
            summary="실적 대비 주가 저평가",
        )
        text = format_mispricing(result)
        assert "강한괴리" in text
        assert "흑자 턴어라운드" in text
        assert "매수 권장" not in text
        assert "확정" not in text

    def test_no_forbidden_expressions(self):
        result = MispricingResult(
            symbol="TEST",
            signals=[MispricingSignal("op_rebound", "영업이익 급반등", 0.8, "상세")],
            total_score=60.0,
            conclusion="괴리가능",
        )
        text = format_mispricing(result)
        for forbidden in ["매수 권장", "매도 권장", "확정 수익", "자동매매"]:
            assert forbidden not in text

    def test_price_context_shown(self):
        result = MispricingResult(
            symbol="TEST",
            signals=[MispricingSignal("turnaround", "흑자 턴어라운드", 0.9, "")],
            price_position_pct=20.0,
            price_6m_chg_pct=3.5,
            total_score=80.0,
            conclusion="강한괴리",
        )
        text = format_mispricing(result)
        assert "20%" in text or "20" in text
