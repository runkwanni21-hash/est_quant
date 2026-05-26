"""Tests for ticker_resolver.py."""

from __future__ import annotations

from unittest.mock import patch

from tele_quant.ticker_resolver import TickerResolution, cap_bucket_label, resolve_ticker


class TestCapBucketLabel:
    def test_mega_cap(self):
        assert "메가캡" in cap_bucket_label(300_000_000_000)

    def test_large_cap(self):
        assert "대형주" in cap_bucket_label(15_000_000_000)

    def test_mid_cap(self):
        assert "중형주" in cap_bucket_label(3_000_000_000)

    def test_small_cap(self):
        assert "소형주" in cap_bucket_label(500_000_000)

    def test_micro_cap(self):
        assert "마이크로캡" in cap_bucket_label(100_000_000)

    def test_nano_cap(self):
        assert "나노캡" in cap_bucket_label(10_000_000)

    def test_none_returns_unknown(self):
        result = cap_bucket_label(None)
        assert "미확인" in result


class TestResolveTicker:
    def _good_info(self) -> dict:
        return {
            "longName": "NVIDIA Corporation",
            "currentPrice": 222.35,
            "exchange": "NMS",
            "marketCap": 5_000_000_000_000,
        }

    def test_returns_ticker_resolution(self):
        with patch("tele_quant.stock_data_provider.get_ticker_info", return_value=self._good_info()):
            res = resolve_ticker("NVDA", "US")
        assert isinstance(res, TickerResolution)

    def test_valid_ticker_data_available(self):
        with patch("tele_quant.stock_data_provider.get_ticker_info", return_value=self._good_info()):
            res = resolve_ticker("NVDA", "US")
        assert res.data_available is True

    def test_mega_cap_bucket(self):
        with patch("tele_quant.stock_data_provider.get_ticker_info", return_value=self._good_info()):
            res = resolve_ticker("NVDA", "US")
        assert "메가캡" in res.cap_bucket

    def test_long_name_captured(self):
        with patch("tele_quant.stock_data_provider.get_ticker_info", return_value=self._good_info()):
            res = resolve_ticker("NVDA", "US")
        assert res.long_name == "NVIDIA Corporation"

    def test_micro_cap_warning(self):
        info = {
            "longName": "Tiny Corp",
            "currentPrice": 5.0,
            "exchange": "OTC",
            "marketCap": 100_000_000,
        }
        with patch("tele_quant.stock_data_provider.get_ticker_info", return_value=info):
            res = resolve_ticker("TINY", "US")
        assert any("마이크로캡" in w or "유동성" in w for w in res.warnings)

    def test_nano_cap_warning(self):
        info = {
            "longName": "Nano Corp",
            "currentPrice": 1.0,
            "exchange": "PNK",
            "marketCap": 10_000_000,
        }
        with patch("tele_quant.stock_data_provider.get_ticker_info", return_value=info):
            res = resolve_ticker("NANO", "US")
        assert any("나노캡" in w for w in res.warnings)

    def test_otc_warning(self):
        info = {
            "longName": "OTC Corp",
            "currentPrice": 2.5,
            "exchange": "OTC",
            "marketCap": 200_000_000,
        }
        with patch("tele_quant.stock_data_provider.get_ticker_info", return_value=info):
            res = resolve_ticker("OTCX", "US")
        assert res.is_otc is True
        assert any("OTC" in w for w in res.warnings)

    def test_empty_info_data_unavailable(self):
        with (
            patch("tele_quant.stock_data_provider.get_ticker_info", return_value={}),
            patch("tele_quant.ticker_resolver._sec_edgar_lookup", return_value=None),
        ):
            res = resolve_ticker("FAKE123", "US")
        assert res.data_available is False

    def test_recent_ipo_warning(self):
        import time
        info = {
            "longName": "New IPO Corp",
            "currentPrice": 20.0,
            "exchange": "NMS",
            "marketCap": 1_000_000_000,
            "firstTradeDateMilliseconds": (time.time() - 30 * 86400) * 1000,  # 30일 전
        }
        with patch("tele_quant.stock_data_provider.get_ticker_info", return_value=info):
            res = resolve_ticker("NEWIPO", "US")
        assert res.is_recent_ipo is True
        assert any("IPO" in w for w in res.warnings)

    def test_resolved_symbol_defaults_to_original(self):
        with patch("tele_quant.stock_data_provider.get_ticker_info", return_value=self._good_info()):
            res = resolve_ticker("NVDA", "US")
        assert res.resolved_symbol == "NVDA"

    def test_exception_handled_gracefully(self):
        with patch("tele_quant.stock_data_provider.get_ticker_info", side_effect=RuntimeError("err")):
            res = resolve_ticker("ERR", "US")
        assert res.data_available is False

    def test_corrupted_shortname_filtered(self):
        """yfinance bug: shortName='222420.KS,0P00016I29,14567' → 걸러내야 함."""
        info = {
            "shortName": "222420.KS,0P00016I29,14567",
            "longName": None,
            "regularMarketPrice": 1300.0,
        }
        with (
            patch("tele_quant.stock_data_provider.get_ticker_info", return_value=info),
            patch("pykrx.stock.get_market_ticker_name", return_value="쎄노텍"),
        ):
            res = resolve_ticker("222420.KS", "KR")
        assert "," not in res.long_name
        assert res.long_name == "쎄노텍"

    def test_short_name_clean_accepted(self):
        """쉼표 없는 shortName은 그대로 사용."""
        info = {
            "shortName": "NVIDIA Corp",
            "longName": None,
            "currentPrice": 222.0,
            "marketCap": 1_000_000_000_000,
        }
        with patch("tele_quant.stock_data_provider.get_ticker_info", return_value=info):
            res = resolve_ticker("NVDA", "US")
        assert res.long_name == "NVIDIA Corp"
