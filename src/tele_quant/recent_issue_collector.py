"""Recent issue collector — 최신 뉴스/공시 집계.

DB raw_items / sentiment_history → Finnhub → RSS 순으로 시도.
중복 제거, 브로커 오탐 제거, 최신순 정렬.
공개 정보 기반 리서치 보조. 투자 판단 책임은 사용자에게 있음.
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tele_quant.db import Store

log = logging.getLogger(__name__)

__all__ = [
    "IssueType",
    "RecentIssue",
    "collect_recent_issues",
    "format_recent_issues",
]

# ── 브로커 리포트 필터 ─────────────────────────────────────────────────────────

_BROKER_PREFIXES = re.compile(
    r"^(Goldman|Morgan Stanley|JP Morgan|Citi|UBS|Barclays|Deutsche|"
    r"Credit Suisse|Jefferies|Baird|Piper|Cowen|Needham|Bernstein|"
    r"Wells Fargo|Raymond James|Truist|Oppenheimer|Stifel|"
    r"미래에셋|NH투자|KB증권|하나증권|신한투자|키움|삼성증권|"
    r"한국투자|메리츠|대신증권|교보증권)",
    re.IGNORECASE,
)

_ISSUE_TYPE_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("price_action",  re.compile(r"급등|급락|상한가|하한가|신고가|신저가|surged|plunged|rally|drop", re.I)),
    ("analyst",       re.compile(r"analyst|애널리스트|리포트|목표주가|BUY|SELL|neutral|overweight", re.I)),
    ("guidance",      re.compile(r"가이던스|outlook|전망|forecast|상향|하향|목표가|TP|raised|lowered", re.I)),
    ("earnings",      re.compile(r"실적|earnings|EPS|revenue|매출|영업이익|순이익|beat|miss|분기", re.I)),
    ("contract",      re.compile(r"수주|계약|공급|납품|MOU|LOI|order|contract|backlog", re.I)),
    ("clinical",      re.compile(r"임상|clinical|FDA|phase|NDA|BLA|PDUFA|IND|승인|허가|MFDS|EMA", re.I)),
    ("regulation",    re.compile(r"규제|제재|공정위|금감원|SEC|FTC|DOJ|반독점|소송|환경|규정", re.I)),
    ("macro",         re.compile(r"금리|Fed|FOMC|CPI|GDP|인플레|고용|환율|국채|매크로|원자재", re.I)),
    ("supply_chain",  re.compile(r"공급망|supply|반도체|부품|원자재|재고|shortage|수급|소재", re.I)),
]


class IssueType(str):
    pass


@dataclass
class RecentIssue:
    title: str
    source: str = ""
    url: str = ""
    published_at: str = ""          # ISO datetime string
    sentiment: str = "neutral"      # bullish | bearish | neutral
    issue_type: str = "general"
    confidence: str = "LOW"
    _hash: str = field(default="", repr=False)

    def __post_init__(self) -> None:
        if not self._hash:
            self._hash = hashlib.sha1(self.title[:80].encode()).hexdigest()[:12]


def _classify_issue_type(title: str) -> str:
    for issue_type, pat in _ISSUE_TYPE_PATTERNS:
        if pat.search(title):
            return issue_type
    return "general"


def _is_broker_report(title: str, source: str = "") -> bool:
    return bool(_BROKER_PREFIXES.match(title) or _BROKER_PREFIXES.match(source))


def _dedupe(issues: list[RecentIssue]) -> list[RecentIssue]:
    seen: set[str] = set()
    result: list[RecentIssue] = []
    for iss in issues:
        if iss._hash not in seen:
            seen.add(iss._hash)
            result.append(iss)
    return result


def _from_db_row(row: dict) -> RecentIssue | None:
    title = (row.get("snippet") or row.get("title") or row.get("headline") or "").strip()
    if not title or len(title) < 5:
        return None
    return RecentIssue(
        title=title[:160],
        source=str(row.get("source_name") or row.get("source") or ""),
        url=str(row.get("url") or ""),
        published_at=str(row.get("published_at") or row.get("created_at") or ""),
        sentiment=str(row.get("polarity") or row.get("sentiment") or "neutral"),
        issue_type=_classify_issue_type(title),
        confidence="MEDIUM",
    )


def _fetch_from_db(
    symbol: str,
    store: Store,
    days: int,
    max_items: int,
) -> list[RecentIssue]:
    results: list[RecentIssue] = []
    cutoff = (datetime.now(UTC) - timedelta(days=days)).isoformat()

    # sentiment_history
    try:
        rows = store.recent_sentiment_history(
            ticker=symbol,
            limit=max_items * 2,
        )
        for row in (rows or []):
            iss = _from_db_row(dict(row))
            if iss and (iss.published_at or "z") >= cutoff and not _is_broker_report(iss.title, iss.source):
                results.append(iss)
    except Exception as exc:
        log.debug("[issue_collector] sentiment_history 조회 실패 %s: %s", symbol, exc)

    # raw_items
    try:
        with store.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM raw_items WHERE published_at >= ? ORDER BY published_at DESC LIMIT ?",
                (cutoff, max_items * 3),
            ).fetchall()
        for row in rows:
            d = dict(row)
            title = (d.get("title") or d.get("headline") or "").strip()
            if not title:
                continue
            if symbol.upper() not in title.upper() and (d.get("ticker") or "") != symbol:
                continue
            iss = _from_db_row(d)
            if iss and not _is_broker_report(iss.title, iss.source):
                results.append(iss)
    except Exception as exc:
        log.debug("[issue_collector] raw_items 조회 실패 %s: %s", symbol, exc)

    return results


def _fetch_from_finnhub(
    symbol: str,
    market: str,
    days: int,
    max_items: int,
) -> list[RecentIssue]:
    if (market or "").upper() == "KR":
        return []
    try:
        from tele_quant.finnhub_client import fetch_finnhub_news
        from tele_quant.settings import Settings

        settings = Settings()
        api_key = getattr(settings, "finnhub_api_key", "") or ""
        if not api_key:
            return []
        items = fetch_finnhub_news(
            symbols=[symbol],
            api_key=api_key,
            lookback_days=days,
            max_per_symbol=max_items,
        )
        results: list[RecentIssue] = []
        for item in items:
            title = (item.title or "").strip()
            if not title or _is_broker_report(title, item.source_name or ""):
                continue
            results.append(RecentIssue(
                title=title[:160],
                source=str(item.source_name or "Finnhub"),
                url=str(item.url or ""),
                published_at=str(item.published_at or ""),
                sentiment="neutral",
                issue_type=_classify_issue_type(title),
                confidence="MEDIUM",
            ))
        return results
    except Exception as exc:
        log.debug("[issue_collector] finnhub 조회 실패 %s: %s", symbol, exc)
        return []


def _fetch_from_yfinance_news(
    symbol: str,
    max_items: int,
) -> list[RecentIssue]:
    try:
        import yfinance as yf
        ticker = yf.Ticker(symbol)
        raw_news = ticker.news or []
        results: list[RecentIssue] = []
        for art in raw_news[:max_items]:
            title = (art.get("title") or "").strip()
            if not title:
                continue
            pub = art.get("providerPublishTime", 0)
            pub_str = datetime.fromtimestamp(pub, tz=UTC).isoformat() if pub else ""
            results.append(RecentIssue(
                title=title[:160],
                source=str(art.get("publisher") or "yfinance"),
                url=str(art.get("link") or ""),
                published_at=pub_str,
                sentiment="neutral",
                issue_type=_classify_issue_type(title),
                confidence="LOW",
            ))
        return results
    except Exception as exc:
        log.debug("[issue_collector] yfinance news 조회 실패 %s: %s", symbol, exc)
        return []


def collect_recent_issues(
    symbol: str,
    name: str = "",
    market: str = "",
    sector_id: str = "",
    store: Store | None = None,
    days: int = 14,
    max_items: int = 5,
) -> list[RecentIssue]:
    """DB → Finnhub → yfinance 순으로 최신 이슈를 수집해 최신순 반환."""
    all_issues: list[RecentIssue] = []

    if store is not None:
        all_issues.extend(_fetch_from_db(symbol, store, days, max_items))

    if len(all_issues) < max_items:
        all_issues.extend(_fetch_from_finnhub(symbol, market, days, max_items))

    if len(all_issues) < max_items:
        all_issues.extend(_fetch_from_yfinance_news(symbol, max_items))

    deduped = _dedupe(all_issues)

    def _sort_key(iss: RecentIssue) -> str:
        return iss.published_at or "0000"

    deduped.sort(key=_sort_key, reverse=True)
    return deduped[:max_items]


def format_recent_issues(issues: list[RecentIssue], title: str = "📰 최근 이슈") -> str:
    """RecentIssue 목록 → Telegram 출력 문자열."""
    if not issues:
        return ""
    lines = [f"{title}:"]
    for iss in issues:
        label = _sentiment_emoji(iss.sentiment)
        type_tag = f"[{iss.issue_type}] " if iss.issue_type and iss.issue_type != "general" else ""
        lines.append(f"  {label} {type_tag}{iss.title[:100]}")
        if iss.source:
            lines[-1] += f" ({iss.source})"
    return "\n".join(lines)


def _sentiment_emoji(sentiment: str) -> str:
    s = (sentiment or "").lower()
    if s in ("bullish", "positive", "pos"):
        return "✅"
    if s in ("bearish", "negative", "neg"):
        return "⚠"
    return "•"
