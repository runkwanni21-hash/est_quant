"""Tests for opendart_client, finnhub_client, economic_calendar modules."""
from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

# ---------- economic_calendar ----------

class TestGetUpcomingEvents:
    def test_returns_list(self):
        from tele_quant.economic_calendar import get_upcoming_events
        events = get_upcoming_events(lookahead_days=365, importance="high")
        assert isinstance(events, list)

    def test_event_has_required_keys(self):
        from tele_quant.economic_calendar import get_upcoming_events
        events = get_upcoming_events(lookahead_days=365, importance="high")
        if events:
            e = events[0]
            assert "date" in e
            assert "name" in e
            assert "importance" in e
            assert "days_away" in e

    def test_sorted_by_date(self):
        from tele_quant.economic_calendar import get_upcoming_events
        events = get_upcoming_events(lookahead_days=365, importance="high")
        dates = [e["date"] for e in events]
        assert dates == sorted(dates)

    def test_fomc_present(self):
        from tele_quant.economic_calendar import get_upcoming_events
        events = get_upcoming_events(lookahead_days=365, importance="high")
        names = [e["name"] for e in events]
        assert any("FOMC" in n for n in names)

    def test_bok_present(self):
        from tele_quant.economic_calendar import get_upcoming_events
        events = get_upcoming_events(lookahead_days=365, importance="high")
        names = [e["name"] for e in events]
        assert any("한국은행" in n for n in names)


class TestBuildCalendarSection:
    def test_returns_string(self):
        from tele_quant.economic_calendar import build_calendar_section
        settings = MagicMock()
        settings.finnhub_api_key = ""
        settings.finnhub_timeout_seconds = 5.0
        settings.economic_calendar_lookahead_days = 365
        result = build_calendar_section(settings, lookahead_days=365)
        assert isinstance(result, str)

    def test_contains_calendar_icon(self):
        from tele_quant.economic_calendar import build_calendar_section
        settings = MagicMock()
        settings.finnhub_api_key = ""
        settings.finnhub_timeout_seconds = 5.0
        result = build_calendar_section(settings, lookahead_days=365)
        if result:
            assert "📅" in result or "D-" in result or "일" in result


# ---------- opendart_client ----------

class TestRawItemFromDart:
    def test_creates_raw_item(self):
        from tele_quant.opendart_client import _raw_item_from_dart
        item = _raw_item_from_dart(
            {
                "corp_name": "삼성전자",
                "report_nm": "주요사항보고",
                "rcept_dt": "20260514",
                "rcept_no": "20260514000001",
            },
            "005930.KS",
        )
        assert item.source_name == "OpenDART"
        assert "삼성전자" in item.title
        assert item.published_at.year == 2026

    def test_invalid_date_falls_back(self):
        from tele_quant.opendart_client import _raw_item_from_dart
        item = _raw_item_from_dart({"corp_name": "테스트", "rcept_dt": "invalid"}, "000001.KS")
        assert item.published_at is not None

    def test_url_contains_rcept_no(self):
        from tele_quant.opendart_client import _raw_item_from_dart
        item = _raw_item_from_dart(
            {"corp_name": "X", "rcept_dt": "20260101", "rcept_no": "ABC123"}, "000001.KS"
        )
        assert "ABC123" in (item.url or "")

    def test_no_api_key_returns_empty(self):
        from tele_quant.opendart_client import fetch_dart_disclosures
        result = fetch_dart_disclosures(["005930.KS"], api_key="")
        assert result == []

    def test_non_kr_code_skipped(self):
        from tele_quant.opendart_client import fetch_dart_disclosures
        # NVDA has no .KS/.KQ → skipped, so no HTTP calls made, returns empty
        result = fetch_dart_disclosures(["NVDA"], api_key="KEY")
        assert result == []

    def test_watchlist_disabled(self):
        from tele_quant.opendart_client import fetch_dart_for_watchlist
        settings = MagicMock()
        settings.opendart_enabled = False
        settings.opendart_api_key = "KEY"
        result = fetch_dart_for_watchlist(settings)
        assert result == []


# ---------- finnhub_client ----------

class TestRawItemFromFinnhub:
    def test_creates_raw_item(self):
        from tele_quant.finnhub_client import _raw_item_from_finnhub
        now_ts = int(datetime.now(UTC).timestamp())
        item = _raw_item_from_finnhub(
            {
                "headline": "NVDA beats earnings",
                "summary": "Revenue up 20%",
                "url": "https://example.com/nvda",
                "source": "Reuters",
                "datetime": now_ts,
            },
            "NVDA",
        )
        assert item.source_name == "Finnhub/Reuters"
        assert "NVDA beats earnings" in item.title
        assert item.url == "https://example.com/nvda"

    def test_empty_api_key_returns_empty(self):
        from tele_quant.finnhub_client import fetch_finnhub_news
        result = fetch_finnhub_news(["NVDA"], api_key="")
        assert result == []

    def test_empty_symbols_returns_empty(self):
        from tele_quant.finnhub_client import fetch_finnhub_news
        result = fetch_finnhub_news([], api_key="KEY")
        assert result == []

    def test_kr_symbols_skipped(self):
        from tele_quant.finnhub_client import fetch_finnhub_news
        # .KS symbols should be skipped, no HTTP calls
        result = fetch_finnhub_news(["005930.KS"], api_key="KEY")
        assert result == []

    @patch("tele_quant.finnhub_client.httpx.Client")
    def test_successful_fetch(self, mock_client_class):
        now_ts = int(datetime.now(UTC).timestamp())
        mock_resp = MagicMock()
        mock_resp.json.return_value = [
            {
                "headline": "NVDA Q1 Earnings Beat",
                "summary": "Revenue up 20%",
                "url": "https://example.com/1",
                "source": "Reuters",
                "datetime": now_ts,
            }
        ]
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = mock_resp
        mock_client_class.return_value = mock_client

        from tele_quant.finnhub_client import fetch_finnhub_news
        result = fetch_finnhub_news(["NVDA"], api_key="KEY", lookback_days=2, max_per_symbol=5)
        assert len(result) == 1
        assert result[0].source_type == "rss_news"
        assert "NVDA" in result[0].title or "Earnings" in result[0].title

    @patch("tele_quant.finnhub_client.httpx.Client")
    def test_max_per_symbol_respected(self, mock_client_class):
        now_ts = int(datetime.now(UTC).timestamp())
        mock_resp = MagicMock()
        mock_resp.json.return_value = [
            {"headline": f"News {i}", "summary": "", "url": "", "source": "T", "datetime": now_ts}
            for i in range(10)
        ]
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = mock_resp
        mock_client_class.return_value = mock_client

        from tele_quant.finnhub_client import fetch_finnhub_news
        result = fetch_finnhub_news(["NVDA"], api_key="KEY", lookback_days=2, max_per_symbol=3)
        assert len(result) <= 3

    def test_watchlist_disabled(self):
        from tele_quant.finnhub_client import fetch_finnhub_for_watchlist
        settings = MagicMock()
        settings.finnhub_enabled = False
        settings.finnhub_api_key = "KEY"
        result = fetch_finnhub_for_watchlist(settings)
        assert result == []

    def test_extracts_us_symbols_from_watchlist(self):
        from tele_quant.finnhub_client import fetch_finnhub_for_watchlist

        settings = MagicMock()
        settings.finnhub_enabled = True
        settings.finnhub_api_key = "KEY"
        settings.finnhub_lookback_days = 2
        settings.finnhub_max_per_symbol = 3
        settings.finnhub_max_symbols = 8
        settings.finnhub_timeout_seconds = 5.0
        settings.finnhub_rate_limit_per_sec = 100
        settings.yfinance_symbols = "^GSPC,^VIX"

        grp = MagicMock()
        grp.symbols = ["NVDA", "005930.KS", "TSLA"]
        wl = MagicMock()
        wl.groups = {"ai": grp}

        with patch("tele_quant.finnhub_client.fetch_finnhub_news", return_value=[]) as mock_fetch:
            fetch_finnhub_for_watchlist(settings, watchlist_cfg=wl)
            assert mock_fetch.called
            call = mock_fetch.call_args
            called_syms = call.args[0] if call.args else call.kwargs.get("symbols", [])
            assert "NVDA" in called_syms
            assert "TSLA" in called_syms
            assert "005930.KS" not in called_syms


# ---------- intraday BB fields ----------

class TestIntradayBBFields:
    def test_snapshot_has_bb_fields(self):
        from tele_quant.analysis.intraday import IntradayTechnicalSnapshot
        snap = IntradayTechnicalSnapshot(symbol="NVDA")
        assert snap.bb_upper is None
        assert snap.bb_middle is None
        assert snap.bb_lower is None

    def test_bb_bands_returns_prices(self):
        import pandas as pd

        from tele_quant.analysis.intraday import _bb_bands
        close = pd.Series([float(100 + i % 5) for i in range(25)])
        label, upper, middle, lower = _bb_bands(close)
        assert label in ("상단돌파", "중단~상단", "하단~중단", "하단이탈")
        assert upper is not None
        assert middle is not None
        assert lower is not None
        assert upper >= middle >= lower

    def test_bb_bands_insufficient_data(self):
        import pandas as pd

        from tele_quant.analysis.intraday import _bb_bands
        close = pd.Series([100.0] * 5)
        label, upper, _middle, _lower = _bb_bands(close)
        assert label == "데이터 부족"
        assert upper is None

    def test_compute_4h_snapshot_populates_bb_prices(self):
        import numpy as np
        import pandas as pd

        from tele_quant.analysis.intraday import compute_4h_snapshot

        np.random.seed(42)
        prices = 100 + np.cumsum(np.random.randn(40) * 0.5)
        df = pd.DataFrame({
            "Open": prices,
            "High": prices + 0.5,
            "Low": prices - 0.5,
            "Close": prices,
            "Volume": [1000.0] * 40,
        }, index=pd.date_range("2026-01-01", periods=40, freq="4h"))

        snap = compute_4h_snapshot("NVDA", df)
        assert snap is not None
        assert snap.bb_upper is not None
        assert snap.bb_middle is not None
        assert snap.bb_lower is not None
        assert snap.bb_upper >= snap.bb_lower


# ---------- TradeScenario BB fields ----------

class TestTradeScenarioBBFields:
    def test_has_bb_4h_fields(self):
        from tele_quant.analysis.models import TradeScenario
        sc = TradeScenario(
            symbol="NVDA",
            name="NVIDIA",
            direction="bullish",
            score=75.0,
            grade="관심",
            entry_zone="100",
            stop_loss="95",
            take_profit="110",
            invalidation="95",
        )
        assert sc.bb_upper_4h is None
        assert sc.bb_middle_4h is None
        assert sc.bb_lower_4h is None


# ---------- opendart corp code (corpCode.xml 기반) ----------

class TestDartCorpCodeMap:
    def _mock_xml_zip(self, entries: list[dict]) -> bytes:
        import io
        import zipfile
        xml_lines = ['<?xml version="1.0" encoding="UTF-8"?><result>']
        for e in entries:
            xml_lines.append(
                f"<list><corp_code>{e['corp_code']}</corp_code>"
                f"<corp_name>{e['corp_name']}</corp_name>"
                f"<stock_code>{e['stock_code']}</stock_code></list>"
            )
        xml_lines.append("</result>")
        xml_bytes = "\n".join(xml_lines).encode("utf-8")
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("CORPCODE.xml", xml_bytes)
        return buf.getvalue()

    def test_lookup_corp_code_finds_entry(self, tmp_path):
        from unittest.mock import MagicMock, patch

        import tele_quant.opendart_client as dart
        # Isolate from real disk cache by redirecting cache file to tmp
        orig_file = dart._CORP_CODE_CACHE_FILE
        dart._CORP_CODE_CACHE_FILE = tmp_path / "dart_corp_codes.json"
        dart._CORP_CODE_MAP = {}
        dart._CORP_CODE_MAP_TS = 0.0
        dart._corp_code_cache = {}
        try:
            zip_bytes = self._mock_xml_zip([
                {"corp_code": "01091054", "corp_name": "쎄노텍", "stock_code": "222420"}
            ])
            mock_resp = MagicMock()
            mock_resp.content = zip_bytes
            mock_resp.raise_for_status = MagicMock()

            with patch("httpx.get", return_value=mock_resp):
                result = dart._lookup_corp_code("222420", "test_key", 10.0)
            assert result == "01091054"
        finally:
            dart._CORP_CODE_CACHE_FILE = orig_file

    def test_lookup_corp_code_missing_returns_none(self, tmp_path):
        from unittest.mock import MagicMock, patch

        import tele_quant.opendart_client as dart
        orig_file = dart._CORP_CODE_CACHE_FILE
        dart._CORP_CODE_CACHE_FILE = tmp_path / "dart_corp_codes.json"
        dart._CORP_CODE_MAP = {}
        dart._CORP_CODE_MAP_TS = 0.0
        try:
            zip_bytes = self._mock_xml_zip([
                {"corp_code": "01091054", "corp_name": "쎄노텍", "stock_code": "222420"}
            ])
            mock_resp = MagicMock()
            mock_resp.content = zip_bytes
            mock_resp.raise_for_status = MagicMock()

            with patch("httpx.get", return_value=mock_resp):
                result = dart._lookup_corp_code("999999", "test_key", 10.0)
            assert result is None
        finally:
            dart._CORP_CODE_CACHE_FILE = orig_file

    def test_fetch_dart_corp_name(self):
        import tele_quant.opendart_client as dart
        dart._CORP_CODE_MAP = {"222420": {"corp_code": "01091054", "corp_name": "쎄노텍"}}
        dart._CORP_CODE_MAP_TS = float("inf")

        result = dart.fetch_dart_corp_name("222420", "test_key")
        assert result == "쎄노텍"

    def test_fetch_dart_corp_name_no_api_key(self):
        from tele_quant.opendart_client import fetch_dart_corp_name
        result = fetch_dart_corp_name("222420", "")
        assert result is None

    def test_fetch_dart_corp_name_non_digit(self):
        from tele_quant.opendart_client import fetch_dart_corp_name
        result = fetch_dart_corp_name("NVDA", "key")
        assert result is None
