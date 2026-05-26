"""Tests for dcf_estimator.py."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from tele_quant.dcf_estimator import DCFResult, estimate_dcf, format_dcf


def _info(overrides: dict | None = None) -> dict:
    base = {
        "forwardEps": 11.43,
        "earningsGrowth": 0.30,
        "beta": 1.9,
        "currentPrice": 222.35,
    }
    if overrides:
        base.update(overrides)
    return base


class TestEstimateDCF:
    def test_returns_dcf_result(self):
        with patch("tele_quant.stock_data_provider.get_ticker_info", return_value=_info()):
            r = estimate_dcf("NVDA", "US")
        assert isinstance(r, DCFResult)

    def test_intrinsic_value_positive(self):
        with patch("tele_quant.stock_data_provider.get_ticker_info", return_value=_info()):
            r = estimate_dcf("NVDA", "US")
        assert r.intrinsic_value is not None
        assert r.intrinsic_value > 0

    def test_upside_calculated(self):
        with patch("tele_quant.stock_data_provider.get_ticker_info", return_value=_info()):
            r = estimate_dcf("NVDA", "US")
        assert r.upside_pct is not None

    def test_assumptions_populated(self):
        with patch("tele_quant.stock_data_provider.get_ticker_info", return_value=_info()):
            r = estimate_dcf("NVDA", "US")
        assert r.assumptions != ""

    def test_no_eps_returns_empty(self):
        with patch("tele_quant.stock_data_provider.get_ticker_info",
                   return_value={"currentPrice": 100.0}):
            r = estimate_dcf("NOEPS", "US")
        assert r.intrinsic_value is None

    def test_negative_eps_returns_empty(self):
        with patch("tele_quant.stock_data_provider.get_ticker_info",
                   return_value={"forwardEps": -2.0, "currentPrice": 50.0}):
            r = estimate_dcf("NEG", "US")
        assert r.intrinsic_value is None

    def test_growth_rate_clamped(self):
        # earningsGrowth=2.0 (200%) → should be clamped to 0.45
        with patch("tele_quant.stock_data_provider.get_ticker_info",
                   return_value=_info({"earningsGrowth": 2.0})):
            r = estimate_dcf("HIGH", "US")
        assert r.growth_rate_1 <= 0.45

    def test_beta_clamped(self):
        with patch("tele_quant.stock_data_provider.get_ticker_info",
                   return_value=_info({"beta": 10.0})):
            r = estimate_dcf("HIGHBETA", "US")
        assert r.beta <= 3.0

    def test_discount_rate_capm(self):
        with patch("tele_quant.stock_data_provider.get_ticker_info",
                   return_value=_info({"beta": 1.0})):
            r = estimate_dcf("BETA1", "US")
        # CAPM: 4.5% + 1.0 * 5% = 9.5%
        assert r.discount_rate == pytest.approx(0.095, abs=0.001)

    def test_exception_returns_empty(self):
        with patch("tele_quant.stock_data_provider.get_ticker_info",
                   side_effect=RuntimeError("err")):
            r = estimate_dcf("ERR", "US")
        assert r.intrinsic_value is None


class TestFormatDCF:
    def test_empty_result_returns_empty(self):
        assert format_dcf(DCFResult()) == ""

    def test_intrinsic_value_shown(self):
        r = DCFResult(intrinsic_value=250.0, current_price=222.35, upside_pct=12.4)
        text = format_dcf(r, "US")
        assert "$250.00" in text

    def test_upside_positive_shown(self):
        r = DCFResult(intrinsic_value=250.0, current_price=200.0, upside_pct=25.0)
        text = format_dcf(r, "US")
        assert "상승 여력" in text
        assert "+25.0%" in text

    def test_downside_shown(self):
        r = DCFResult(intrinsic_value=150.0, current_price=200.0, upside_pct=-25.0)
        text = format_dcf(r, "US")
        assert "고평가" in text

    def test_kr_currency_symbol(self):
        r = DCFResult(intrinsic_value=80000.0, current_price=75000.0, upside_pct=6.7)
        text = format_dcf(r, "KR")
        assert "₩" in text

    def test_disclaimer_present(self):
        r = DCFResult(intrinsic_value=100.0)
        text = format_dcf(r, "US")
        assert "가정" in text
        assert "확정" in text
