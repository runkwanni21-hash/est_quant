"""Tests for investment_scorecard.py."""

from __future__ import annotations

from tele_quant.investment_scorecard import (
    InvestmentScorecard,
    _bar,
    _tier,
    build_scorecard,
    format_scorecard,
)

# ── Helpers ───────────────────────────────────────────────────────────────────


class TestBar:
    def test_full_bar(self):
        b = _bar(100)
        assert b == "█" * 10

    def test_empty_bar(self):
        b = _bar(0)
        assert b == "░" * 10

    def test_half_bar(self):
        b = _bar(50)
        assert b.count("█") == 5
        assert b.count("░") == 5

    def test_length_always_10(self):
        for v in [0, 25, 50, 75, 100]:
            assert len(_bar(v)) == 10


class TestTier:
    def test_strong_watch(self):
        assert _tier(80) == "STRONG_WATCH"

    def test_watch(self):
        assert _tier(65) == "WATCH"

    def test_neutral(self):
        assert _tier(50) == "NEUTRAL"

    def test_avoid(self):
        assert _tier(30) == "AVOID"

    def test_boundary_75(self):
        assert _tier(75) == "STRONG_WATCH"

    def test_boundary_60(self):
        assert _tier(60) == "WATCH"

    def test_boundary_45(self):
        assert _tier(45) == "NEUTRAL"


# ── Build ─────────────────────────────────────────────────────────────────────


class TestBuildScorecard:
    def _good_kwargs(self) -> dict:
        return dict(
            rs_3m_pct=15.0,
            vol_surge_ratio=2.5,
            week52_pos_pct=85.0,
            is_breakout=False,
            dtc=8.0,
            piotroski_score=7,
            roic=22.0,
            gross_margin=65.0,
            current_ratio=2.5,
            net_cash_positive=True,
            revenue_cagr_3y=25.0,
            earnings_growth=0.30,
            beat_rate_pct=100.0,
            avg_surprise_pct=12.0,
            surprise_trend="가속(↑)",
            altman_z=5.5,
            institutional_pct=75.0,
            short_float_pct=3.0,
            peg_ratio=1.2,
            dcf_upside_pct=25.0,
            fcf_yield=4.0,
        )

    def test_returns_scorecard(self):
        sc = build_scorecard("NVDA", **self._good_kwargs())
        assert isinstance(sc, InvestmentScorecard)

    def test_scores_in_range(self):
        sc = build_scorecard("NVDA", **self._good_kwargs())
        for attr in ("momentum_score", "fundamental_score", "growth_score",
                     "reliability_score", "valuation_score"):
            v = getattr(sc, attr)
            assert 0 <= v <= 100, f"{attr}={v} out of range"

    def test_total_score_is_weighted_sum(self):
        sc = build_scorecard("NVDA", **self._good_kwargs())
        expected = (
            sc.momentum_score * 0.25
            + sc.fundamental_score * 0.20
            + sc.growth_score * 0.25
            + sc.reliability_score * 0.20
            + sc.valuation_score * 0.10
        )
        assert abs(sc.total_score - expected) < 0.01

    def test_strong_watch_on_good_inputs(self):
        sc = build_scorecard("NVDA", **self._good_kwargs())
        assert sc.tier == "STRONG_WATCH"

    def test_avoid_on_bad_inputs(self):
        sc = build_scorecard(
            "BAD",
            piotroski_score=1,
            altman_z=1.0,
            rs_3m_pct=-15.0,
            revenue_cagr_3y=-10.0,
            roic=-5.0,
        )
        assert sc.tier in ("NEUTRAL", "AVOID")

    def test_bull_points_populated(self):
        sc = build_scorecard("NVDA", **self._good_kwargs())
        assert len(sc.bull_points) >= 1

    def test_bear_points_on_weak_inputs(self):
        sc = build_scorecard(
            "WEAK",
            piotroski_score=1,
            altman_z=0.8,
            rs_3m_pct=-20.0,
            short_float_pct=25.0,
        )
        assert len(sc.bear_points) >= 1

    def test_empty_inputs_mid_range(self):
        sc = build_scorecard("EMPTY")
        # base is 50 → weighted avg = 50, tier = NEUTRAL
        assert 40 <= sc.total_score <= 60

    def test_breakout_adds_bull(self):
        sc = build_scorecard("BRK", is_breakout=True, vol_surge_ratio=2.0, week52_pos_pct=95.0)
        assert any("돌파" in p for p in sc.bull_points)

    def test_max_bull_4(self):
        sc = build_scorecard("NVDA", **self._good_kwargs())
        assert len(sc.bull_points) <= 4

    def test_max_bear_3(self):
        sc = build_scorecard(
            "WEAK",
            piotroski_score=1,
            altman_z=0.8,
            rs_3m_pct=-20.0,
            short_float_pct=30.0,
            revenue_cagr_3y=-15.0,
            roic=-10.0,
            fcf_yield=-3.0,
        )
        assert len(sc.bear_points) <= 3


# ── Format ────────────────────────────────────────────────────────────────────


class TestFormatScorecard:
    def _sc(self) -> InvestmentScorecard:
        return build_scorecard(
            "NVDA",
            rs_3m_pct=15.0,
            piotroski_score=7,
            roic=22.0,
            revenue_cagr_3y=25.0,
            beat_rate_pct=100.0,
            altman_z=5.5,
        )

    def test_tier_in_output(self):
        text = format_scorecard(self._sc())
        assert "STRONG_WATCH" in text or "WATCH" in text

    def test_bar_chars_present(self):
        text = format_scorecard(self._sc())
        assert "█" in text

    def test_all_dimensions_shown(self):
        text = format_scorecard(self._sc())
        assert "기술모멘텀" in text
        assert "펀더멘탈" in text
        assert "성장가속도" in text
        assert "실적신뢰도" in text
        assert "밸류에이션" in text

    def test_bull_points_shown(self):
        text = format_scorecard(self._sc())
        assert "강점" in text

    def test_zero_score_returns_empty(self):
        sc = InvestmentScorecard(symbol="X")
        assert format_scorecard(sc) == ""
