"""Tests for ticker_universe.py."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

# ── is_valid_symbol ───────────────────────────────────────────────────────


def test_valid_kr_symbol():
    from tele_quant.ticker_universe import is_valid_symbol
    assert is_valid_symbol("005930.KS") is True
    assert is_valid_symbol("000660.KS") is True
    assert is_valid_symbol("240810.KQ") is True


def test_valid_us_symbol():
    from tele_quant.ticker_universe import is_valid_symbol
    assert is_valid_symbol("NVDA") is True
    assert is_valid_symbol("AAPL") is True
    assert is_valid_symbol("BRK-B") is True
    assert is_valid_symbol("TSM") is True


def test_invalid_numeric_symbol():
    from tele_quant.ticker_universe import is_valid_symbol
    assert is_valid_symbol("432") is False
    assert is_valid_symbol("17856") is False
    assert is_valid_symbol("12345") is False


def test_invalid_empty_symbol():
    from tele_quant.ticker_universe import is_valid_symbol
    assert is_valid_symbol("") is False


def test_invalid_warrant_symbol():
    from tele_quant.ticker_universe import is_valid_symbol
    # 5자 이상 + W suffix는 warrant
    assert is_valid_symbol("NVDAW") is False
    assert is_valid_symbol("SMACU") is False


# ── detect_sector_from_yfinance ────────────────────────────────────────────


def test_sector_from_yfinance_override():
    """override 파일에 있는 종목은 yfinance 무관하게 correct sector."""
    from tele_quant.ticker_universe import detect_sector_from_yfinance
    sid, label, _ = detect_sector_from_yfinance("005930.KS")
    assert sid == "ai_semiconductor_hbm_foundry"
    assert "반도체" in label


def test_sector_from_yfinance_nvda_override():
    from tele_quant.ticker_universe import detect_sector_from_yfinance
    sid, _, _ = detect_sector_from_yfinance("NVDA")
    assert sid == "ai_semiconductor_hbm_foundry"


def test_sector_from_yfinance_gics_fallback():
    """override 없는 종목은 yfinance GICS로 감지."""
    from tele_quant.ticker_universe import detect_sector_from_yfinance

    mock_info = {"sector": "Technology", "industry": "Semiconductors"}
    with patch("tele_quant.stock_data_provider.get_ticker_info", return_value=mock_info):
        sid, _label, _ind = detect_sector_from_yfinance("FAKEABC")
    assert sid == "ai_semiconductor_hbm_foundry"


def test_sector_from_yfinance_bio_industry():
    from tele_quant.ticker_universe import detect_sector_from_yfinance

    mock_info = {"sector": "Healthcare", "industry": "Biotechnology"}
    with patch("tele_quant.stock_data_provider.get_ticker_info", return_value=mock_info):
        sid, _, _ = detect_sector_from_yfinance("FAKEBIO")
    assert sid == "biotech_pharma_clinical_medtech"


def test_sector_from_yfinance_failure_graceful():
    from tele_quant.ticker_universe import detect_sector_from_yfinance

    with patch("tele_quant.stock_data_provider.get_ticker_info", side_effect=Exception("fail")):
        sid, label, _ind = detect_sector_from_yfinance("FAIL")
    assert sid == ""
    assert label == ""


# ── get_display_name ───────────────────────────────────────────────────────


def test_get_display_name_from_store():
    from tele_quant.ticker_universe import get_display_name

    mock_store = MagicMock()
    mock_store.get_ticker_name.return_value = "테스트회사"
    name = get_display_name("TEST.KS", store=mock_store)
    assert name == "테스트회사"


def test_get_display_name_fallback_to_symbol():
    from tele_quant.ticker_universe import get_display_name

    mock_store = MagicMock()
    mock_store.get_ticker_name.return_value = "UNKNOWN"
    name = get_display_name("UNKNOWN", store=mock_store)
    assert name == "UNKNOWN"


# ── build_universe ─────────────────────────────────────────────────────────


def test_build_universe_no_store_returns_counts():
    """store=None이면 DB 저장 없이 카운트만 반환."""
    from tele_quant.ticker_universe import build_universe

    with (
        patch("tele_quant.ticker_universe._build_kr_universe", return_value=[
            {"symbol": "005930.KS", "market": "KR", "name_ko": "삼성전자",
             "name_en": "", "exchange": "KOSPI", "sector_id": "ai_semiconductor_hbm_foundry",
             "sector_label": "AI 반도체", "industry": "", "market_cap_usd": None,
             "is_active": True, "is_etf": False},
        ]),
        patch("tele_quant.ticker_universe._build_us_universe", return_value=[
            {"symbol": "NVDA", "market": "US", "name_ko": "", "name_en": "NVIDIA",
             "exchange": "NASDAQ", "sector_id": "ai_semiconductor_hbm_foundry",
             "sector_label": "AI 반도체", "industry": "Semiconductors",
             "market_cap_usd": 3e12, "is_active": True, "is_etf": False},
        ]),
    ):
        counts = build_universe(market="ALL", store=None)
    assert counts["KR"] == 1
    assert counts["US"] == 1
    assert counts["total"] == 2


def test_build_universe_saves_to_store():
    from tele_quant.ticker_universe import build_universe

    mock_store = MagicMock()
    mock_store.upsert_ticker_universe.return_value = 2
    mock_store.get_universe_count.return_value = {"KR": 1, "US": 1, "total": 2}

    with (
        patch("tele_quant.ticker_universe._build_kr_universe", return_value=[
            {"symbol": "005930.KS", "market": "KR", "name_ko": "삼성전자",
             "name_en": "", "exchange": "KOSPI", "sector_id": "", "sector_label": "",
             "industry": "", "market_cap_usd": None, "is_active": True, "is_etf": False},
        ]),
        patch("tele_quant.ticker_universe._build_us_universe", return_value=[]),
    ):
        counts = build_universe(market="KR", store=mock_store)
    mock_store.upsert_ticker_universe.assert_called_once()
    assert counts["total"] == 2
