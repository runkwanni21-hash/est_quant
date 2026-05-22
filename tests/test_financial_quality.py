"""Tests for financial_quality.py — Piotroski, Altman Z, ROIC, etc."""

from __future__ import annotations

import pandas as pd

from tele_quant.financial_quality import (
    FinancialQuality,
    _altman_z,
    _liquidity_grade,
    _piotroski,
    _revenue_cagr,
    _roic,
    format_financial_quality,
)

# ── Fixtures ──────────────────────────────────────────────────────────────────

def _make_income(rev=(100e9, 88e9), gp=(62e9, 54e9), net=(21e9, 16e9), op=(25e9, 20e9),
                 shares=(1e9, 1e9)) -> pd.DataFrame:
    cols = pd.to_datetime(["2024-12-31", "2023-12-31"])
    idx = ["Total Revenue", "Gross Profit", "Net Income", "Operating Income",
           "Diluted Average Shares"]
    data = {cols[0]: [rev[0], gp[0], net[0], op[0], shares[0]],
            cols[1]: [rev[1], gp[1], net[1], op[1], shares[1]]}
    return pd.DataFrame(data, index=idx)


def _make_balance(ta=(200e9, 180e9), ca=(80e9, 70e9), cl=(30e9, 28e9),
                  ltd=(10e9, 12e9), re=(50e9, 40e9), te=(100e9, 90e9)) -> pd.DataFrame:
    cols = pd.to_datetime(["2024-12-31", "2023-12-31"])
    idx = ["Total Assets", "Current Assets", "Current Liabilities",
           "Long Term Debt", "Retained Earnings",
           "Total Stockholder Equity"]
    data = {cols[0]: [ta[0], ca[0], cl[0], ltd[0], re[0], te[0]],
            cols[1]: [ta[1], ca[1], cl[1], ltd[1], re[1], te[1]]}
    return pd.DataFrame(data, index=idx)


def _make_cashflow(ocf=(28e9, 22e9)) -> pd.DataFrame:
    cols = pd.to_datetime(["2024-12-31", "2023-12-31"])
    idx = ["Operating Cash Flow"]
    data = {cols[0]: [ocf[0]], cols[1]: [ocf[1]]}
    return pd.DataFrame(data, index=idx)


_GOOD_INFO = {
    "marketCap": 3_000_000_000_000,
    "effectiveTaxRate": 0.21,
    "shortPercentOfFloat": 0.021,
    "heldPercentInsiders": 0.042,
    "heldPercentInstitutions": 0.713,
    "averageVolume10days": 45_000_000,
}


# ── Piotroski ─────────────────────────────────────────────────────────────────

class TestPiotroski:
    def test_returns_tuple(self):
        score, ok, fail = _piotroski(
            _make_income(), _make_balance(), _make_cashflow(), _GOOD_INFO
        )
        assert isinstance(score, int)
        assert isinstance(ok, list)
        assert isinstance(fail, list)

    def test_score_in_range(self):
        score, _, _ = _piotroski(
            _make_income(), _make_balance(), _make_cashflow(), _GOOD_INFO
        )
        assert 0 <= score <= 9

    def test_positive_roa_passes(self):
        _score, ok, _ = _piotroski(
            _make_income(), _make_balance(), _make_cashflow(), _GOOD_INFO
        )
        assert "ROA>0" in ok

    def test_positive_ocf_passes(self):
        _, ok, _ = _piotroski(
            _make_income(), _make_balance(), _make_cashflow(), _GOOD_INFO
        )
        assert "영업현금흐름>0" in ok

    def test_gross_margin_improved_passes(self):
        # gp/rev: 62/100=62% now vs 54/88=61.4% prev → improved
        _, ok, _ = _piotroski(
            _make_income(), _make_balance(), _make_cashflow(), _GOOD_INFO
        )
        assert "매출총이익률 개선" in ok

    def test_leverage_decreased_passes(self):
        # ltd/ta: 10/200=5% now vs 12/180=6.7% prev → decreased
        _, ok, _ = _piotroski(
            _make_income(), _make_balance(), _make_cashflow(), _GOOD_INFO
        )
        assert "레버리지 감소" in ok

    def test_empty_dfs_no_crash(self):
        score, _, _ = _piotroski(pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), {})
        assert score == 0


# ── Altman Z ─────────────────────────────────────────────────────────────────

class TestAltmanZ:
    def test_returns_z_and_zone(self):
        z, zone = _altman_z(_make_income(), _make_balance(), _GOOD_INFO)
        assert z is not None
        assert zone != ""

    def test_safe_zone_large_cap(self):
        z, zone = _altman_z(_make_income(), _make_balance(), _GOOD_INFO)
        # With large market cap (3T) vs total liabilities ~100B → should be safe
        assert z is not None
        assert "안전" in zone or "회색" in zone  # large company likely safe

    def test_none_on_empty_balance(self):
        z, zone = _altman_z(_make_income(), pd.DataFrame(), _GOOD_INFO)
        assert z is None
        assert zone == ""


# ── ROIC ─────────────────────────────────────────────────────────────────────

class TestROIC:
    def test_roic_positive(self):
        # NOPAT = 25B * (1-0.21) = 19.75B; IC = 100B + 10B - cash ≈ 100B+
        r = _roic(_make_income(), _make_balance(), _GOOD_INFO)
        assert r is not None
        assert r > 0

    def test_roic_none_on_empty(self):
        r = _roic(pd.DataFrame(), pd.DataFrame(), {})
        assert r is None


# ── Revenue CAGR ─────────────────────────────────────────────────────────────

class TestRevenueCagr:
    def test_cagr_calculated(self):
        cols = pd.to_datetime(["2024-12-31", "2023-12-31", "2022-12-31", "2021-12-31"])
        revs = [100e9, 88e9, 78e9, 65e9]
        df = pd.DataFrame({"Total Revenue": revs}, index=cols).T
        cagr = _revenue_cagr(df, years=3)
        assert cagr is not None
        # (100/65)^(1/3) - 1 ≈ 15.4%
        assert 10 < cagr < 20

    def test_none_on_insufficient_data(self):
        df = pd.DataFrame({"Total Revenue": [100e9]},
                          index=pd.to_datetime(["2024-12-31"])).T
        assert _revenue_cagr(df, years=3) is None


# ── Liquidity grade ───────────────────────────────────────────────────────────

class TestLiquidityGrade:
    def test_high(self):
        assert _liquidity_grade(10_000_000) == "높음"

    def test_medium(self):
        assert _liquidity_grade(1_000_000) == "중간"

    def test_low(self):
        assert _liquidity_grade(100_000) == "낮음"

    def test_very_low(self):
        assert _liquidity_grade(10_000) == "매우 낮음"

    def test_none(self):
        assert _liquidity_grade(None) == "미확인"


# ── Format ────────────────────────────────────────────────────────────────────

class TestFormatFinancialQuality:
    def _make_fq(self) -> FinancialQuality:
        fq = FinancialQuality(symbol="NVDA")
        fq.piotroski_score = 7
        fq.piotroski_failed = ["발생액<0(현금질)"]
        fq.altman_z = 8.5
        fq.altman_zone = "안전 (Z>2.99)"
        fq.roic = 28.5
        fq.revenue_cagr_3y = 65.0
        fq.short_float_pct = 2.1
        fq.insider_pct = 4.2
        fq.institutional_pct = 71.3
        fq.avg_volume_10d = 45_000_000
        fq.liquidity_grade = "높음"
        return fq

    def test_piotroski_in_output(self):
        text = format_financial_quality(self._make_fq())
        assert "Piotroski" in text
        assert "7/9" in text

    def test_altman_z_in_output(self):
        text = format_financial_quality(self._make_fq())
        assert "Altman Z" in text
        assert "8.5" in text

    def test_roic_in_output(self):
        text = format_financial_quality(self._make_fq())
        assert "ROIC" in text
        assert "28.5%" in text

    def test_cagr_in_output(self):
        text = format_financial_quality(self._make_fq())
        assert "CAGR" in text

    def test_short_interest_in_output(self):
        text = format_financial_quality(self._make_fq())
        assert "공매도" in text

    def test_institutional_in_output(self):
        text = format_financial_quality(self._make_fq())
        assert "기관" in text

    def test_empty_returns_empty(self):
        fq = FinancialQuality(symbol="X")
        assert format_financial_quality(fq) == ""
