"""Tests for earnings_history.py — 5-year annual earnings history."""

from __future__ import annotations

from unittest.mock import patch

import pandas as pd
import pytest

from tele_quant.earnings_history import (
    AnnualResult,
    EarningsHistory,
    fetch_earnings_history,
    format_earnings_history,
)


class TestFormatEarningsHistory:
    def _make_history(self, results: list[AnnualResult], market: str = "US") -> EarningsHistory:
        return EarningsHistory(
            symbol="TEST",
            market=market,
            currency="KRW" if market == "KR" else "USD",
            results=results,
        )

    def test_empty_results_returns_empty(self):
        h = self._make_history([])
        assert format_earnings_history(h) == ""

    def test_header_present(self):
        h = self._make_history([AnnualResult(year=2024, revenue_bn=10.0)])
        text = format_earnings_history(h)
        assert "연간 실적" in text

    def test_us_currency_dollar(self):
        h = self._make_history([AnnualResult(year=2024, revenue_bn=10.0)])
        text = format_earnings_history(h)
        assert "$10.0B" in text

    def test_kr_currency_jo(self):
        h = self._make_history([AnnualResult(year=2024, revenue_bn=5.0)], market="KR")
        text = format_earnings_history(h)
        assert "5.0조" in text

    def test_yoy_positive(self):
        r = AnnualResult(year=2024, revenue_bn=10.0, revenue_yoy_pct=12.3)
        h = self._make_history([r])
        text = format_earnings_history(h)
        assert "+12.3%" in text

    def test_yoy_negative(self):
        r = AnnualResult(year=2023, revenue_bn=9.0, revenue_yoy_pct=-5.0)
        h = self._make_history([r])
        text = format_earnings_history(h)
        assert "-5.0%" in text

    def test_op_margin_shown(self):
        r = AnnualResult(year=2024, revenue_bn=10.0, op_margin_pct=22.5)
        h = self._make_history([r])
        text = format_earnings_history(h)
        assert "OPM 22.5%" in text

    def test_net_income_us(self):
        r = AnnualResult(year=2024, revenue_bn=10.0, net_income_bn=2.5)
        h = self._make_history([r])
        text = format_earnings_history(h)
        assert "$2.5B" in text

    def test_max_5_rows(self):
        results = [AnnualResult(year=2024 - i, revenue_bn=float(10 - i)) for i in range(7)]
        h = self._make_history(results)
        text = format_earnings_history(h)
        # match data rows like "  2024년" — starts with spaces + 4-digit year
        import re
        lines = [ln for ln in text.splitlines() if re.match(r"\s+\d{4}년", ln)]
        assert len(lines) <= 5

    def test_note_appended(self):
        h = self._make_history([AnnualResult(year=2024, revenue_bn=5.0)], market="KR")
        h.note = "DART 공시 확인 권장."
        text = format_earnings_history(h)
        assert "DART" in text


class TestFetchEarningsHistory:
    def _mock_stmt(self) -> pd.DataFrame:
        cols = pd.to_datetime(["2024-12-31", "2023-12-31", "2022-12-31"])
        idx = ["Total Revenue", "Operating Income", "Net Income", "Other"]
        data = {
            cols[0]: [100e9, 25e9, 20e9, 1e9],
            cols[1]: [88e9, 20e9, 16e9, 1e9],
            cols[2]: [80e9, 16e9, 12e9, 1e9],
        }
        return pd.DataFrame(data, index=idx)

    def test_returns_earnings_history(self):
        with patch("tele_quant.stock_data_provider.get_income_stmt",
                   return_value=self._mock_stmt()):
            h = fetch_earnings_history("NVDA2", "US")

        assert isinstance(h, EarningsHistory)
        assert not h.data_limited

    def test_results_newest_first(self):
        with patch("tele_quant.stock_data_provider.get_income_stmt",
                   return_value=self._mock_stmt()):
            h = fetch_earnings_history("NVDA2", "US")

        assert h.results[0].year >= h.results[-1].year

    def test_revenue_bn_calculated(self):
        with patch("tele_quant.stock_data_provider.get_income_stmt",
                   return_value=self._mock_stmt()):
            h = fetch_earnings_history("NVDA2", "US")

        # 2024 revenue = 100e9 → 100.0B
        assert h.results[0].revenue_bn == pytest.approx(100.0, abs=0.01)

    def test_yoy_calculated(self):
        with patch("tele_quant.stock_data_provider.get_income_stmt",
                   return_value=self._mock_stmt()):
            h = fetch_earnings_history("NVDA2", "US")

        # 2024 vs 2023: (100-88)/88 ≈ 13.6%
        yoy_2024 = h.results[0].revenue_yoy_pct
        assert yoy_2024 is not None
        assert yoy_2024 == pytest.approx(13.636, abs=0.1)

    def test_op_margin_calculated(self):
        with patch("tele_quant.stock_data_provider.get_income_stmt",
                   return_value=self._mock_stmt()):
            h = fetch_earnings_history("NVDA2", "US")

        # 2024: 25/100 = 25%
        assert h.results[0].op_margin_pct == pytest.approx(25.0, abs=0.01)

    def test_empty_stmt_data_limited(self):
        with patch("tele_quant.stock_data_provider.get_income_stmt",
                   return_value=pd.DataFrame()):
            h = fetch_earnings_history("EMPTY2", "US")

        assert h.data_limited

    def test_exception_data_limited(self):
        with patch("tele_quant.stock_data_provider.get_income_stmt",
                   side_effect=RuntimeError("network error")):
            h = fetch_earnings_history("ERR2", "US")

        assert h.data_limited

    def test_kr_note_appended(self):
        with patch("tele_quant.stock_data_provider.get_income_stmt",
                   return_value=self._mock_stmt()):
            h = fetch_earnings_history("005930.KS", "KR")

        assert "DART" in h.note
        assert h.currency == "KRW"
