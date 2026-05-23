"""Tests for extended fields in FundamentalSnapshot."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from tele_quant.fundamentals import FundamentalSnapshot, fetch_fundamentals


def _make_info(overrides: dict | None = None) -> dict:
    base: dict = {
        "marketCap": 1_000_000_000,
        "trailingPE": 20.0,
        "forwardPE": 18.0,
        "priceToBook": 3.0,
        "returnOnEquity": 0.15,
        "earningsGrowth": 0.10,
        "revenueGrowth": 0.08,
        "operatingMargins": 0.20,
        "debtToEquity": 50.0,
        "sector": "Technology",
        "industry": "Semiconductors",
        "dividendYield": 0.01,
        "enterpriseToEbitda": 15.5,
        "freeCashflow": 50_000_000,
        "grossMargins": 0.62,
        "currentRatio": 2.1,
        "pegRatio": 1.8,
        "targetMeanPrice": 120.0,
        "numberOfAnalystOpinions": 25,
        "recommendationMean": 2.1,
        "currentPrice": 100.0,
        "fiftyTwoWeekHigh": 130.0,
        "fiftyTwoWeekLow": 70.0,
    }
    if overrides:
        base.update(overrides)
    return base


class TestFundamentalSnapshotExtended:
    def _fetch(self, overrides: dict | None = None) -> FundamentalSnapshot:
        with patch(
            "tele_quant.stock_data_provider.get_ticker_info",
            return_value=_make_info(overrides),
        ):
            return fetch_fundamentals("NVDA", "US")

    def test_ev_to_ebitda(self):
        snap = self._fetch()
        assert snap.ev_to_ebitda == pytest.approx(15.5)

    def test_fcf_yield(self):
        snap = self._fetch()
        # 50_000_000 / 1_000_000_000 * 100 = 5.0%
        assert snap.fcf_yield == pytest.approx(5.0)

    def test_gross_margin(self):
        snap = self._fetch()
        assert snap.gross_margin == pytest.approx(62.0)

    def test_current_ratio(self):
        snap = self._fetch()
        assert snap.current_ratio == pytest.approx(2.1)

    def test_peg_ratio(self):
        snap = self._fetch()
        assert snap.peg_ratio == pytest.approx(1.8)

    def test_analyst_target(self):
        snap = self._fetch()
        assert snap.analyst_target == pytest.approx(120.0)

    def test_analyst_target_upside(self):
        snap = self._fetch()
        # (120 - 100) / 100 * 100 = 20%
        assert snap.analyst_target_upside == pytest.approx(20.0)

    def test_analyst_count(self):
        snap = self._fetch()
        assert snap.analyst_count == 25

    def test_analyst_rec_mean(self):
        snap = self._fetch()
        assert snap.analyst_rec_mean == pytest.approx(2.1)

    def test_ev_ebitda_none_when_negative(self):
        snap = self._fetch({"enterpriseToEbitda": -5.0})
        assert snap.ev_to_ebitda is None

    def test_ev_ebitda_none_when_extreme(self):
        snap = self._fetch({"enterpriseToEbitda": 1500.0})
        assert snap.ev_to_ebitda is None

    def test_peg_none_when_negative(self):
        snap = self._fetch({"pegRatio": -1.0})
        assert snap.peg_ratio is None

    def test_analyst_upside_none_when_target_missing(self):
        snap = self._fetch({"targetMeanPrice": None})
        assert snap.analyst_target is None
        assert snap.analyst_target_upside is None

    def test_fcf_yield_none_when_no_fcf(self):
        snap = self._fetch({"freeCashflow": None})
        assert snap.fcf_yield is None

    def test_dataclass_fields_exist(self):
        snap = FundamentalSnapshot(symbol="X", market="US", sector="", fetched_at=__import__("datetime").datetime.now())
        for field in ("ev_to_ebitda", "fcf_yield", "gross_margin", "current_ratio",
                      "peg_ratio", "analyst_target", "analyst_target_upside",
                      "analyst_count", "analyst_rec_mean"):
            assert hasattr(snap, field), f"Missing field: {field}"
