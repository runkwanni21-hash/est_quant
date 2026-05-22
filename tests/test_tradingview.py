"""Tests for tradingview.py chart link generator."""

from tele_quant.tradingview import chart_url


class TestChartUrl:
    def test_kr_kospi(self):
        url = chart_url("005930.KS", "KR")
        assert "KRX:005930" in url
        assert "interval=240" in url

    def test_kr_kosdaq(self):
        url = chart_url("000660.KQ", "KR")
        assert "KOSDAQ:000660" in url

    def test_us_symbol(self):
        url = chart_url("NVDA", "US")
        assert "NVDA" in url
        assert "KRX" not in url
        assert "KOSDAQ" not in url

    def test_auto_detect_kr_from_suffix_ks(self):
        url = chart_url("005380.KS")
        assert "KRX:005380" in url

    def test_auto_detect_kr_from_suffix_kq(self):
        url = chart_url("035900.KQ")
        assert "KOSDAQ:035900" in url

    def test_auto_detect_us_no_suffix(self):
        url = chart_url("AAPL")
        assert "AAPL" in url
        assert "KRX" not in url

    def test_interval_4h_string(self):
        url = chart_url("NVDA", interval="4H")
        assert "interval=240" in url

    def test_interval_daily(self):
        url = chart_url("NVDA", interval="1D")
        assert "interval=D" in url

    def test_interval_weekly(self):
        url = chart_url("NVDA", interval="W")
        assert "interval=W" in url

    def test_interval_raw_240(self):
        url = chart_url("NVDA", interval="240")
        assert "interval=240" in url

    def test_us_symbol_uppercased(self):
        url = chart_url("nvda", "US")
        assert "NVDA" in url

    def test_kr_dot_stripped(self):
        url = chart_url("329180.KS")
        assert "329180" in url
        assert ".KS" not in url

    def test_tradingview_domain(self):
        url = chart_url("TSLA")
        assert url.startswith("https://www.tradingview.com/chart/")
