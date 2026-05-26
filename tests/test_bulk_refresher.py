"""Tests for bulk_refresher.py."""

from __future__ import annotations

from unittest.mock import MagicMock, patch


def test_run_bulk_refresh_empty_universe():
    """universe가 비어있으면 0 반환."""
    from tele_quant.bulk_refresher import run_bulk_refresh

    mock_store = MagicMock()
    mock_store.get_universe_symbols.return_value = []
    result = run_bulk_refresh(mock_store, limit=10)
    assert result["updated"] == 0
    assert result["failed"] == 0


def test_run_bulk_refresh_updates_store():
    """섹터 감지 성공 시 store.upsert_ticker_universe 호출."""
    from tele_quant.bulk_refresher import run_bulk_refresh

    mock_store = MagicMock()
    mock_store.get_universe_symbols.return_value = ["NVDA", "AAPL"]
    mock_store.upsert_ticker_universe.return_value = 2

    with patch("tele_quant.bulk_refresher._refresh_sector_and_cap",
               side_effect=[
                   {"symbol": "NVDA", "sector_id": "ai_semiconductor_hbm_foundry",
                    "market_cap_usd": 3e12},
                   {"symbol": "AAPL", "sector_id": "telecom_network_smartphone_equipment",
                    "market_cap_usd": 3.5e12},
               ]):
        result = run_bulk_refresh(mock_store, limit=10)
    assert result["updated"] == 2
    assert result["failed"] == 0


def test_refresh_sector_and_cap_failure_graceful():
    """yfinance 실패해도 빈 dict 반환 (크래시 없음)."""
    from tele_quant.bulk_refresher import _refresh_sector_and_cap

    with patch("tele_quant.stock_data_provider.get_ticker_info", side_effect=Exception("fail")):
        result = _refresh_sector_and_cap("FAIL")
    assert result["symbol"] == "FAIL"
