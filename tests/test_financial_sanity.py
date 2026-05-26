"""Tests for financial_sanity module."""
from __future__ import annotations

from tele_quant.financial_sanity import (
    canonicalize_kr_ticker,
    check_financial_sanity,
    format_sanity_note,
    is_bare_kr_ticker,
)

# ── check_financial_sanity ────────────────────────────────────────────────────

def test_high_dividend_flagged():
    r = check_financial_sanity(dividend_yield=55.0)
    warns = [f.field for f in r.flags if f.severity == "WARN"]
    assert "dividend_yield" in warns


def test_normal_dividend_not_flagged():
    r = check_financial_sanity(dividend_yield=3.5)
    assert not r.flags


def test_extreme_roe_flagged():
    r = check_financial_sanity(roe=232.0, sector="Technology")
    warns = [f.field for f in r.flags if f.severity == "WARN"]
    assert "roe" in warns


def test_normal_roe_not_flagged():
    r = check_financial_sanity(roe=18.5)
    assert not r.flags


def test_high_eps_growth_flagged():
    r = check_financial_sanity(eps_growth=496.0)
    warns = [f.field for f in r.flags if f.severity == "WARN"]
    assert "eps_growth" in warns


def test_normal_eps_growth_not_flagged():
    r = check_financial_sanity(eps_growth=25.0)
    assert not r.flags


def test_extreme_pbr_non_saas_flagged():
    r = check_financial_sanity(pb=75.0, sector="Consumer Cyclical")
    warns = [f.field for f in r.flags if f.severity == "WARN"]
    assert "pb" in warns


def test_high_pbr_saas_not_flagged():
    r = check_financial_sanity(pb=75.0, sector="Software")
    # SaaS는 고PBR 허용
    assert all(f.field != "pb" or f.severity != "WARN" for f in r.flags)


def test_kr_price_abnormal_flagged():
    r = check_financial_sanity(current_price=2_000_000.0, market="KR")
    warns = [f.field for f in r.flags if f.severity == "WARN"]
    assert "current_price" in warns


def test_kr_price_normal_not_flagged():
    r = check_financial_sanity(current_price=75_000.0, market="KR")
    assert all(f.field != "current_price" for f in r.flags)


def test_confidence_degrades_with_warnings():
    r = check_financial_sanity(
        dividend_yield=55.0,
        roe=300.0,
        eps_growth=500.0,
    )
    assert r.confidence in ("MEDIUM", "LOW")


def test_clean_data_high_confidence():
    r = check_financial_sanity(pe_trailing=15.0, roe=12.0, dividend_yield=2.5)
    assert r.confidence == "HIGH"


def test_format_sanity_note_empty_when_clean():
    r = check_financial_sanity(pe_trailing=15.0)
    note = format_sanity_note(r)
    assert note == ""


def test_format_sanity_note_has_confidence_prefix():
    r = check_financial_sanity(dividend_yield=55.0)
    note = format_sanity_note(r)
    assert "재무 데이터 신뢰도" in note


# ── ticker canonicalization ───────────────────────────────────────────────────

def test_canonicalize_bare_5digit():
    assert canonicalize_kr_ticker("17856").startswith("017856.")


def test_canonicalize_bare_3digit():
    result = canonicalize_kr_ticker("432")
    assert result.startswith("000432.")
    assert result.endswith((".KS", ".KQ"))


def test_canonicalize_already_canonical_ks():
    assert canonicalize_kr_ticker("005930.KS") == "005930.KS"


def test_canonicalize_already_canonical_kq():
    assert canonicalize_kr_ticker("000660.KQ") == "000660.KQ"


def test_canonicalize_short_ks_pads():
    result = canonicalize_kr_ticker("5930.KS")
    assert result == "005930.KS"


def test_canonicalize_us_ticker_unchanged():
    assert canonicalize_kr_ticker("NVDA") == "NVDA"


def test_is_bare_kr_ticker_true():
    assert is_bare_kr_ticker("17856") is True
    assert is_bare_kr_ticker("432") is True
    assert is_bare_kr_ticker("1") is True


def test_is_bare_kr_ticker_false():
    assert is_bare_kr_ticker("005930") is False  # 6자리
    assert is_bare_kr_ticker("NVDA") is False
    assert is_bare_kr_ticker("005930.KS") is False
