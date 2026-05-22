"""Analyst Consensus — 증권사 리포트·애널리스트 컨센서스 요약.

데이터 소스 우선순위:
1. yfinance analyst data (info.recommendationMean, targetMeanPrice 등)
2. DB raw_items / report_items — 리서치/목표가/투자의견 키워드 검색
3. Finnhub 추천 (API 키 있을 때)

목표가 없으면 지어내지 않고 "확인 제한" 표기.
공개 정보 기반 리서치 보조. 투자 판단 책임은 사용자에게 있음.
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from tele_quant.analysis.report_models import AnalystConsensus
    from tele_quant.db import Store

log = logging.getLogger(__name__)

# 투자의견 정규화
_BUY_PATTERNS = re.compile(
    r"\b(buy|strong\s*buy|매수|outperform|overweight|적극\s*매수|비중\s*확대)\b",
    re.IGNORECASE,
)
_SELL_PATTERNS = re.compile(
    r"\b(sell|strong\s*sell|매도|underperform|underweight|비중\s*축소)\b",
    re.IGNORECASE,
)
_HOLD_PATTERNS = re.compile(
    r"\b(hold|neutral|market\s*perform|중립|보유|비중\s*유지)\b",
    re.IGNORECASE,
)

_TARGET_RE = re.compile(r"목표\s*(?:주가|가)?[:\s]*([0-9,]+)\s*원")
_TARGET_USD_RE = re.compile(r"(?:target|price\s*target)[:\s]*\$?([0-9.]+)", re.IGNORECASE)


# ── yfinance 컨센서스 ─────────────────────────────────────────────────────────


def _from_yfinance(symbol: str) -> dict[str, Any]:
    """yfinance info에서 애널리스트 컨센서스 추출."""
    result: dict[str, Any] = {}
    try:
        from tele_quant.stock_data_provider import get_ticker_info

        info = get_ticker_info(symbol) or {}
        result["target_mean"] = info.get("targetMeanPrice")
        result["target_low"] = info.get("targetLowPrice")
        result["target_high"] = info.get("targetHighPrice")
        result["target_median"] = info.get("targetMedianPrice")
        result["analyst_count"] = info.get("numberOfAnalystOpinions") or info.get("recommendationKey")
        result["current_price"] = info.get("currentPrice") or info.get("regularMarketPrice")

        # recommendationMean: 1=강매수, 3=중립, 5=강매도
        rec_mean = info.get("recommendationMean")
        if rec_mean is not None:
            result["rec_mean"] = float(rec_mean)
        result["data_source"] = "yfinance"
    except Exception as exc:
        log.debug("[consensus] yfinance failed %s: %s", symbol, exc)
    return result


# ── Finnhub 추천 ─────────────────────────────────────────────────────────────


def _from_finnhub(symbol: str) -> dict[str, Any]:
    """Finnhub 추천 데이터 (API 키 있을 때만)."""
    result: dict[str, Any] = {}
    try:
        from tele_quant.settings import Settings

        s = Settings()
        key = getattr(s, "finnhub_api_key", None)
        if not key:
            return result
        from tele_quant.finnhub_client import FinnhubClient

        client = FinnhubClient(key)
        recs = client.recommendation_trends(symbol)
        if not recs:
            return result
        latest = recs[0]
        result["buy_count"] = latest.get("buy", 0) + latest.get("strongBuy", 0)
        result["hold_count"] = latest.get("hold", 0)
        result["sell_count"] = latest.get("sell", 0) + latest.get("strongSell", 0)
        result["data_source"] = "finnhub"
    except Exception as exc:
        log.debug("[consensus] finnhub failed %s: %s", symbol, exc)
    return result


# ── DB raw_items 검색 ─────────────────────────────────────────────────────────


def _from_db(symbol: str, store: Store | None) -> dict[str, Any]:
    """DB에서 목표가/투자의견/리포트 키워드 검색."""
    result: dict[str, Any] = {
        "bull_theses": [], "bear_theses": [], "report_count": 0,
        "recent_upgrade": 0, "recent_downgrade": 0, "targets_krw": [],
        "buy_count": 0, "hold_count": 0, "sell_count": 0,
    }
    if store is None:
        return result

    bare = symbol.split(".")[0]
    name_from_map: str = ""
    try:
        from tele_quant.relation_feed import _NAME_MAP
        name_from_map = _NAME_MAP.get(symbol, "")
    except Exception:
        pass

    keywords = [bare]
    if name_from_map:
        keywords.append(name_from_map)

    try:
        from datetime import timedelta

        from tele_quant.models import utc_now

        since = utc_now() - timedelta(days=30)
        items = store.search_raw_items(keywords, since=since, limit=50)

        for item in items:
            text = (item.get("text", "") or "") + " " + (item.get("title", "") or "")
            if not text.strip():
                continue
            result["report_count"] += 1

            # 투자의견
            if _BUY_PATTERNS.search(text):
                result["buy_count"] += 1
                # "상향" 감지
                if "상향" in text or "upgrade" in text.lower():
                    result["recent_upgrade"] += 1
            elif _SELL_PATTERNS.search(text):
                result["sell_count"] += 1
                if "하향" in text or "downgrade" in text.lower():
                    result["recent_downgrade"] += 1
            elif _HOLD_PATTERNS.search(text):
                result["hold_count"] += 1

            # 목표가 (KRW)
            for m in _TARGET_RE.finditer(text):
                try:
                    val = float(m.group(1).replace(",", ""))
                    if 100 < val < 10_000_000:
                        result["targets_krw"].append(val)
                except ValueError:
                    pass

            # bull/bear thesis 추출 (간단: 첫 70자)
            if _BUY_PATTERNS.search(text):
                thesis = text[:70].strip().replace("\n", " ")
                if thesis and thesis not in result["bull_theses"]:
                    result["bull_theses"].append(thesis)
            elif _SELL_PATTERNS.search(text):
                thesis = text[:70].strip().replace("\n", " ")
                if thesis and thesis not in result["bear_theses"]:
                    result["bear_theses"].append(thesis)

    except Exception as exc:
        log.debug("[consensus] db search failed: %s", exc)

    return result


# ── 의견 레이블 ─────────────────────────────────────────────────────────────


def _opinion_label(buy: int, hold: int, sell: int, rec_mean: float | None) -> str:
    if rec_mean is not None:
        if rec_mean <= 2.0:
            return "BUY 우세"
        elif rec_mean >= 4.0:
            return "SELL 우세"
        elif rec_mean <= 2.5:
            return "BUY-HOLD 혼재"
        elif rec_mean >= 3.5:
            return "HOLD-SELL 혼재"
        return "HOLD 우세"
    total = buy + hold + sell
    if total == 0:
        return "확인 제한"
    if buy > total * 0.6:
        return "BUY 우세"
    if sell > total * 0.4:
        return "SELL 우세"
    return "HOLD 우세"


# ── 상승여력 ────────────────────────────────────────────────────────────────


def _upside(current: float | None, target_mean: float | None) -> float | None:
    if current and target_mean and current > 0:
        return (target_mean - current) / current * 100
    return None


# ── 메인 ────────────────────────────────────────────────────────────────────


def build_analyst_consensus(symbol: str, store: Store | None = None) -> AnalystConsensus:  # type: ignore[name-defined]
    """애널리스트 컨센서스 빌드.

    실패해도 부분 결과 반환. 없는 데이터는 '확인 제한'.
    """
    from tele_quant.analysis.report_models import AnalystConsensus

    cons = AnalystConsensus()

    yf = _from_yfinance(symbol)
    fh = _from_finnhub(symbol)
    db = _from_db(symbol, store)

    cons.target_mean = yf.get("target_mean")
    cons.target_median = yf.get("target_median")
    cons.target_low = yf.get("target_low")
    cons.target_high = yf.get("target_high")
    cons.current_price = yf.get("current_price")
    cons.data_source = yf.get("data_source", "yfinance")

    # 목표가 없으면 DB에서 추출한 KRW 목표가 사용
    if cons.target_mean is None and db.get("targets_krw"):
        targets = sorted(db["targets_krw"])
        n = len(targets)
        cons.target_mean = sum(targets) / n
        cons.target_median = float(targets[n // 2])
        cons.target_low = targets[0]
        cons.target_high = targets[-1]
        cons.data_source = "db_reports"

    # analyst count
    raw_count = yf.get("analyst_count")
    if isinstance(raw_count, (int, float)):
        cons.analyst_count = int(raw_count)

    # 투자의견 분포
    rec_mean = yf.get("rec_mean")
    buy = (fh.get("buy_count") or 0) + (db.get("buy_count") or 0)
    hold = (fh.get("hold_count") or 0) + (db.get("hold_count") or 0)
    sell = (fh.get("sell_count") or 0) + (db.get("sell_count") or 0)
    cons.buy_count = buy
    cons.hold_count = hold
    cons.sell_count = sell
    cons.opinion_label = _opinion_label(buy, hold, sell, rec_mean)

    # 상승여력
    cons.upside_pct = _upside(cons.current_price, cons.target_mean)

    # report_count
    cons.report_count = db.get("report_count", 0)

    # bull/bear theses
    cons.bull_theses = db.get("bull_theses", [])[:3]
    cons.bear_theses = db.get("bear_theses", [])[:3]

    # 상향/하향
    cons.recent_upgrade = db.get("recent_upgrade", 0)
    cons.recent_downgrade = db.get("recent_downgrade", 0)

    # note
    if cons.target_mean is None:
        cons.note = "목표가 확인 제한 (공개자료 부재)"
    elif cons.report_count == 0:
        cons.note = "최근 30일 내 리포트 없음"

    return cons
