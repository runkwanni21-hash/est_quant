"""Tests for recent_issue_collector — news/disclosure aggregator."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from tele_quant.recent_issue_collector import (
    RecentIssue,
    _classify_issue_type,
    _dedupe,
    _from_db_row,
    _is_broker_report,
    _sentiment_emoji,
    collect_recent_issues,
    format_recent_issues,
)

# ── _classify_issue_type ──────────────────────────────────────────────────────


def test_classify_earnings():
    assert _classify_issue_type("NVDA beats EPS estimate for Q3") == "earnings"


def test_classify_contract():
    assert _classify_issue_type("삼성 LNG선 수주 공시") == "contract"


def test_classify_clinical():
    assert _classify_issue_type("FDA Phase 2 trial approved") == "clinical"


def test_classify_regulation():
    assert _classify_issue_type("공정위 조사 개시") == "regulation"


def test_classify_macro():
    assert _classify_issue_type("FOMC 금리 동결 결정") == "macro"


def test_classify_guidance():
    assert _classify_issue_type("가이던스 상향 조정") == "guidance"


def test_classify_analyst():
    assert _classify_issue_type("Goldman Sachs 목표주가 상향") == "analyst"


def test_classify_price_action():
    assert _classify_issue_type("NVDA surged 15% after earnings") == "price_action"


def test_classify_general():
    assert _classify_issue_type("일반 뉴스 제목") == "general"


# ── _is_broker_report ─────────────────────────────────────────────────────────


def test_broker_report_goldman():
    assert _is_broker_report("Goldman Sachs rates NVDA Buy") is True


def test_broker_report_korean():
    assert _is_broker_report("미래에셋 삼성전자 매수의견") is True


def test_not_broker_report():
    assert _is_broker_report("NVDA announces new GPU lineup") is False


def test_broker_source_name():
    assert _is_broker_report("Something happened", "Jefferies") is True


# ── RecentIssue dataclass ─────────────────────────────────────────────────────


def test_recent_issue_auto_hash():
    iss = RecentIssue(title="Test headline about NVDA")
    assert iss._hash != ""
    assert len(iss._hash) == 12


def test_recent_issue_same_title_same_hash():
    iss1 = RecentIssue(title="Same headline")
    iss2 = RecentIssue(title="Same headline")
    assert iss1._hash == iss2._hash


# ── _dedupe ───────────────────────────────────────────────────────────────────


def test_dedupe_removes_duplicates():
    issues = [
        RecentIssue(title="Same headline"),
        RecentIssue(title="Same headline"),
        RecentIssue(title="Different headline"),
    ]
    deduped = _dedupe(issues)
    assert len(deduped) == 2


def test_dedupe_preserves_order():
    issues = [
        RecentIssue(title="First"),
        RecentIssue(title="Second"),
        RecentIssue(title="First"),  # duplicate
    ]
    deduped = _dedupe(issues)
    assert deduped[0].title == "First"
    assert deduped[1].title == "Second"


# ── _from_db_row ──────────────────────────────────────────────────────────────


def test_from_db_row_snippet():
    row = {"snippet": "NVDA beats earnings", "source_name": "Reuters"}
    iss = _from_db_row(row)
    assert iss is not None
    assert iss.title == "NVDA beats earnings"
    assert iss.source == "Reuters"


def test_from_db_row_title_fallback():
    row = {"title": "Samsung wins contract", "source_name": "Bloomberg"}
    iss = _from_db_row(row)
    assert iss is not None
    assert "Samsung" in iss.title


def test_from_db_row_empty_title():
    row = {"title": "", "snippet": "   "}
    iss = _from_db_row(row)
    assert iss is None


def test_from_db_row_short_title():
    row = {"title": "Ok"}
    iss = _from_db_row(row)
    assert iss is None


# ── _sentiment_emoji ──────────────────────────────────────────────────────────


def test_sentiment_bullish():
    assert _sentiment_emoji("bullish") == "✅"
    assert _sentiment_emoji("positive") == "✅"


def test_sentiment_bearish():
    assert _sentiment_emoji("bearish") == "⚠"
    assert _sentiment_emoji("negative") == "⚠"


def test_sentiment_neutral():
    assert _sentiment_emoji("neutral") == "•"


def test_sentiment_unknown():
    assert _sentiment_emoji("") == "•"


# ── collect_recent_issues ─────────────────────────────────────────────────────


def test_collect_no_store_no_finnhub(tmp_path):
    """Store 없으면 yfinance news만 시도 — 네트워크 실패해도 빈 리스트 반환."""
    from unittest.mock import patch

    with patch("yfinance.Ticker") as MockTicker:
        instance = MockTicker.return_value
        instance.news = []
        issues = collect_recent_issues("NVDA", store=None, days=7, max_items=5)

    assert isinstance(issues, list)


def test_collect_from_db(tmp_path):
    from tele_quant.db import Store

    store = Store(tmp_path / "test.db")
    _ts = (datetime.now(UTC) - timedelta(days=1)).isoformat()

    with store.connect() as conn:
        conn.execute(
            """INSERT INTO raw_items
               (external_id, content_hash, source_name, source_type, title, text, url, published_at, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            ("id1", "hash1", "Reuters", "rss_news",
             "NVDA announces record earnings", "", "https://example.com", _ts, _ts),
        )

    issues = collect_recent_issues("NVDA", store=store, days=7, max_items=5)
    # DB에서 가져온 이슈는 ticker 매칭 기준으로 필터됨 — 최소 빈 리스트 반환 확인
    assert isinstance(issues, list)


def test_collect_max_items_limit(tmp_path):
    from unittest.mock import patch

    from tele_quant.db import Store

    store = Store(tmp_path / "test.db")

    with patch("yfinance.Ticker") as MockTicker:
        instance = MockTicker.return_value
        instance.news = [
            {"title": f"News {i}", "providerPublishTime": 1700000000 + i, "publisher": "Test"}
            for i in range(10)
        ]
        issues = collect_recent_issues("NVDA", store=store, days=7, max_items=3)

    assert len(issues) <= 3


def test_collect_broker_filtered(tmp_path):
    from unittest.mock import patch

    from tele_quant.db import Store

    store = Store(tmp_path / "test.db")
    _ts = (datetime.now(UTC) - timedelta(days=1)).isoformat()

    with store.connect() as conn:
        conn.execute(
            """INSERT INTO raw_items
               (external_id, content_hash, source_name, source_type, title, text, url, published_at, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            ("id2", "hash2", "Goldman Sachs", "rss_news",
             "Goldman Sachs rates NVDA Buy with TP $200", "", "https://example.com", _ts, _ts),
        )

    with patch("yfinance.Ticker") as MockTicker:
        instance = MockTicker.return_value
        instance.news = []
        issues = collect_recent_issues("NVDA", store=store, days=7, max_items=5)

    broker_issues = [i for i in issues if "Goldman" in i.source]
    assert len(broker_issues) == 0


# ── format_recent_issues ──────────────────────────────────────────────────────


def test_format_empty_returns_empty():
    assert format_recent_issues([]) == ""


def test_format_includes_title():
    issues = [RecentIssue(title="NVDA beats earnings expectations", sentiment="bullish")]
    result = format_recent_issues(issues)
    assert "NVDA beats earnings" in result
    assert "📰 최근 이슈" in result


def test_format_issue_type_tag():
    issues = [RecentIssue(title="FDA Phase 2 approval", issue_type="clinical")]
    result = format_recent_issues(issues)
    assert "[clinical]" in result


def test_format_no_broker_reports_in_output():
    issues = [
        RecentIssue(title="Real news", source="Reuters", sentiment="neutral"),
    ]
    result = format_recent_issues(issues)
    assert "Goldman Sachs" not in result


def test_format_sentiment_emojis():
    issues = [
        RecentIssue(title="Good news", sentiment="bullish"),
        RecentIssue(title="Bad news", sentiment="bearish"),
        RecentIssue(title="Neutral news", sentiment="neutral"),
    ]
    result = format_recent_issues(issues)
    assert "✅" in result
    assert "⚠" in result
    assert "•" in result
