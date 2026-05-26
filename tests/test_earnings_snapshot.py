"""Tests for earnings_snapshot module."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from tele_quant.earnings_snapshot import (
    EarningsSnapshot,
    fetch_earnings_snapshot,
    format_earnings_snapshot,
)

# ── EarningsSnapshot dataclass ────────────────────────────────────────────────


def test_earnings_snapshot_defaults():
    snap = EarningsSnapshot(symbol="NVDA")
    assert snap.eps_actual is None
    assert snap.next_report_date == ""
    assert snap.data_limited is False


# ── fetch_earnings_snapshot ───────────────────────────────────────────────────


def _mock_info(eps_ttm=5.0, eps_fwd=7.0, rev=44e9, rev_growth=0.22):
    return {
        "trailingEps": eps_ttm,
        "forwardEps": eps_fwd,
        "totalRevenue": rev,
        "revenueGrowth": rev_growth,
    }


def test_fetch_us_basic():
    with patch("yfinance.Ticker") as MockTicker:
        instance = MagicMock()
        instance.info = _mock_info()
        instance.calendar = {"Earnings Date": ["2026-08-20"]}
        MockTicker.return_value = instance

        snap = fetch_earnings_snapshot("NVDA", "US")

    assert snap.eps_actual == 5.0
    assert snap.eps_estimate == 7.0
    assert snap.revenue_actual_bn is not None
    assert snap.revenue_growth_yoy_pct == pytest.approx(22.0, abs=0.1)
    assert snap.next_report_date == "2026-08-20"
    assert snap.data_limited is False


def test_fetch_kr_marked_limited():
    with patch("yfinance.Ticker") as MockTicker:
        instance = MagicMock()
        instance.info = {}
        instance.calendar = None
        MockTicker.return_value = instance

        snap = fetch_earnings_snapshot("005930.KS", "KR")

    assert snap.data_limited is True
    assert "DART" in snap.note


def test_fetch_yfinance_failure_graceful():
    with patch("yfinance.Ticker", side_effect=RuntimeError("network error")):
        snap = fetch_earnings_snapshot("NVDA", "US")

    assert snap.data_limited is True
    assert snap.eps_actual is None


def test_fetch_yfinance_rate_limit_uses_friendly_note():
    with patch("yfinance.Ticker", side_effect=RuntimeError("YFRateLimitError: Too Many Requests")):
        snap = fetch_earnings_snapshot("NVDA", "US")

    assert snap.data_limited is True
    assert "Yahoo" in snap.note
    assert "Too Many Requests" not in snap.note


def test_fetch_eps_surprise_calculated():
    with patch("yfinance.Ticker") as MockTicker:
        instance = MagicMock()
        instance.info = _mock_info(eps_ttm=4.0, eps_fwd=6.0)
        instance.calendar = None
        MockTicker.return_value = instance

        snap = fetch_earnings_snapshot("NVDA", "US")

    assert snap.eps_surprise_pct == pytest.approx(50.0, abs=0.1)


# ── format_earnings_snapshot ──────────────────────────────────────────────────


def test_format_basic():
    snap = EarningsSnapshot(
        symbol="NVDA",
        eps_actual=5.0,
        eps_estimate=7.0,
        eps_surprise_pct=40.0,
        revenue_actual_bn=44.1,
        revenue_growth_yoy_pct=22.0,
        next_report_date="2026-08-20",
    )
    result = format_earnings_snapshot(snap)
    assert "EPS" in result
    assert "44.1" in result
    assert "2026-08-20" in result


def test_format_limited_shows_restriction():
    snap = EarningsSnapshot(
        symbol="005930.KS",
        market="KR",
        data_limited=True,
        note="KR 실적 데이터는 yfinance 기준 제한적.",
    )
    result = format_earnings_snapshot(snap)
    assert "확인 제한" in result or "제한적" in result


def test_format_no_eps_shows_limitation():
    snap = EarningsSnapshot(symbol="UNKNOWN")
    result = format_earnings_snapshot(snap)
    assert "확인 제한" in result


def test_format_no_forbidden_words():
    snap = EarningsSnapshot(
        symbol="NVDA",
        eps_actual=5.0,
        revenue_actual_bn=44.0,
        revenue_growth_yoy_pct=22.0,
    )
    result = format_earnings_snapshot(snap)
    forbidden = ["매수 권장", "확정 수익", "반드시 상승", "자동매매"]
    for word in forbidden:
        assert word not in result


def test_format_guidance_raised():
    snap = EarningsSnapshot(symbol="NVDA", guidance_direction="raised")
    result = format_earnings_snapshot(snap)
    assert "상향" in result


def test_format_guidance_lowered():
    snap = EarningsSnapshot(symbol="AAPL", guidance_direction="lowered")
    result = format_earnings_snapshot(snap)
    assert "하향" in result
