"""Tests for earnings_surprise.py."""

from __future__ import annotations

from unittest.mock import patch

import pandas as pd

from tele_quant.earnings_surprise import (
    EarningsSurprise,
    QuarterlyBeat,
    _calc_trend,
    fetch_earnings_surprise,
    format_earnings_surprise,
)

# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_earnings_df(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


# ── Trend calc ────────────────────────────────────────────────────────────────


class TestCalcTrend:
    def _quarters(self, surprises: list[float]) -> list[QuarterlyBeat]:
        return [QuarterlyBeat(quarter=f"Q{i}", surprise_pct=s) for i, s in enumerate(surprises)]

    def test_accelerating(self):
        # recent avg (15+20)/2=17.5 vs prior avg (5+10)/2=7.5 → diff=10 >= 5
        qs = self._quarters([20, 15, 10, 5])
        assert _calc_trend(qs) == "가속(↑)"

    def test_decelerating(self):
        qs = self._quarters([2, 1, 20, 15])
        assert _calc_trend(qs) == "둔화(↓)"

    def test_stable(self):
        qs = self._quarters([10, 10, 10, 10])
        assert _calc_trend(qs) == "안정(→)"

    def test_insufficient_data(self):
        qs = self._quarters([10, 5])
        assert _calc_trend(qs) == "미확인"


# ── Fetch ─────────────────────────────────────────────────────────────────────


class TestFetchEarningsSurprise:
    def _make_df(self) -> pd.DataFrame:
        return pd.DataFrame({
            "Date": ["2023-10-31", "2024-01-31", "2024-04-30", "2024-07-31"],
            "EPS Estimate": [0.95, 1.00, 1.10, 1.20],
            "Reported EPS": [1.05, 1.15, 1.25, 1.40],
            "Surprise(%)": [10.5, 15.0, 13.6, 16.7],
        })

    def test_returns_earnings_surprise(self):
        with patch("tele_quant.stock_data_provider.get_earnings_history",
                   return_value=self._make_df()):
            es = fetch_earnings_surprise("NVDA")
        assert isinstance(es, EarningsSurprise)

    def test_quarters_populated(self):
        with patch("tele_quant.stock_data_provider.get_earnings_history",
                   return_value=self._make_df()):
            es = fetch_earnings_surprise("NVDA")
        assert len(es.quarters) >= 1

    def test_beat_rate_calculated(self):
        with patch("tele_quant.stock_data_provider.get_earnings_history",
                   return_value=self._make_df()):
            es = fetch_earnings_surprise("NVDA")
        assert es.beat_rate_pct is not None
        assert es.beat_rate_pct == 100.0

    def test_avg_surprise_calculated(self):
        with patch("tele_quant.stock_data_provider.get_earnings_history",
                   return_value=self._make_df()):
            es = fetch_earnings_surprise("NVDA")
        assert es.avg_surprise_pct is not None
        assert es.avg_surprise_pct > 0

    def test_trend_populated(self):
        with patch("tele_quant.stock_data_provider.get_earnings_history",
                   return_value=self._make_df()):
            es = fetch_earnings_surprise("NVDA")
        assert es.trend != ""

    def test_no_data_returns_limited(self):
        with patch("tele_quant.stock_data_provider.get_earnings_history",
                   return_value=None):
            es = fetch_earnings_surprise("NODATA")
        assert es.data_limited is True

    def test_empty_df_returns_limited(self):
        with patch("tele_quant.stock_data_provider.get_earnings_history",
                   return_value=pd.DataFrame()):
            es = fetch_earnings_surprise("EMPTY")
        assert es.data_limited is True

    def test_exception_handled(self):
        with patch("tele_quant.stock_data_provider.get_earnings_history",
                   side_effect=RuntimeError("err")):
            es = fetch_earnings_surprise("ERR")
        assert es.data_limited is True


# ── Format ────────────────────────────────────────────────────────────────────


class TestFormatEarningsSurprise:
    def _es(self) -> EarningsSurprise:
        es = EarningsSurprise(symbol="NVDA")
        es.quarters = [
            QuarterlyBeat("2024-07", eps_actual=1.40, eps_estimate=1.20, surprise_pct=16.7, beat=True),
            QuarterlyBeat("2024-04", eps_actual=1.25, eps_estimate=1.10, surprise_pct=13.6, beat=True),
            QuarterlyBeat("2024-01", eps_actual=1.15, eps_estimate=1.00, surprise_pct=15.0, beat=True),
            QuarterlyBeat("2023-10", eps_actual=1.05, eps_estimate=0.95, surprise_pct=10.5, beat=True),
        ]
        es.beat_rate_pct = 100.0
        es.avg_surprise_pct = 13.95
        es.trend = "안정(→)"
        return es

    def test_header_present(self):
        text = format_earnings_surprise(self._es())
        assert "EPS 서프라이즈" in text

    def test_beat_checkmark(self):
        text = format_earnings_surprise(self._es())
        assert "✅" in text

    def test_beat_rate_shown(self):
        text = format_earnings_surprise(self._es())
        assert "비트율" in text
        assert "100%" in text

    def test_avg_surprise_shown(self):
        text = format_earnings_surprise(self._es())
        assert "평균서프라이즈" in text

    def test_trend_shown(self):
        text = format_earnings_surprise(self._es())
        assert "트렌드" in text

    def test_max_4_quarters(self):
        es = self._es()
        es.quarters = es.quarters * 2  # 8개
        text = format_earnings_surprise(es)
        assert text.count("✅") <= 4

    def test_empty_returns_empty(self):
        es = EarningsSurprise(symbol="X")
        assert format_earnings_surprise(es) == ""

    def test_miss_shows_x(self):
        es = EarningsSurprise(symbol="X")
        es.quarters = [QuarterlyBeat("2024-01", surprise_pct=-5.0, beat=False)]
        text = format_earnings_surprise(es)
        assert "❌" in text
