"""빠른 워치리스트 스크리너 — 30초 이내 병렬 수집.

전체 analyze_single 대신 yfinance 캐시를 직접 활용해
가격·기술·펀더멘탈 핵심 지표만 빠르게 수집한다.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

log = logging.getLogger(__name__)

_MAX_WORKERS = 16
_PRICE_PERIOD = "3mo"


@dataclass
class QuickQuote:
    symbol: str
    name: str = ""
    market: str = "US"

    # 가격
    price: float | None = None
    currency: str = "USD"

    # 변동률
    chg_1d: float | None = None
    chg_1w: float | None = None
    chg_1m: float | None = None

    # 기술
    rsi_14: float | None = None
    ma20_pct: float | None = None   # (price/MA20 - 1) * 100
    vol_ratio: float | None = None  # 최근 5일 평균 거래량 / 20일 평균

    # 펀더멘탈
    pe_trailing: float | None = None
    pb: float | None = None
    market_cap_b: float | None = None  # 십억 단위

    # 점수 (0-100)
    score: float = 0.0
    signal: str = "NEUTRAL"   # STRONG_WATCH | WATCH | NEUTRAL | AVOID

    # 오류
    error: str = ""
    fetched_at: datetime = field(default_factory=lambda: datetime.now(UTC))


def _fetch_one(symbol: str) -> QuickQuote:
    """단일 종목 빠른 수집."""
    market = "KR" if symbol.endswith((".KS", ".KQ")) else "US"
    q = QuickQuote(symbol=symbol, market=market)
    try:
        from tele_quant.stock_data_provider import get_ohlcv, get_ticker_info

        info: dict[str, Any] = get_ticker_info(symbol) or {}
        q.name = info.get("longName") or info.get("shortName") or symbol
        q.currency = info.get("currency", "KRW" if market == "KR" else "USD")
        q.pe_trailing = _safe_float(info.get("trailingPE"))
        q.pb = _safe_float(info.get("priceToBook"))
        mc = info.get("marketCap")
        if mc:
            q.market_cap_b = mc / 1e9

        df = get_ohlcv(symbol, period=_PRICE_PERIOD, interval="1d")
        if df is None or df.empty:
            q.error = "no_price_data"
            return q

        closes = df["Close"].dropna()
        vols = df["Volume"].dropna() if "Volume" in df.columns else None
        n = len(closes)
        if n < 2:
            q.error = "insufficient_data"
            return q

        q.price = float(closes.iloc[-1])

        def _pct(lb: int) -> float | None:
            return (
                (float(closes.iloc[-1]) - float(closes.iloc[-(lb + 1)]))
                / float(closes.iloc[-(lb + 1)])
                * 100
            ) if n > lb and closes.iloc[-(lb + 1)] else None

        q.chg_1d = _pct(1)
        q.chg_1w = _pct(5)
        q.chg_1m = _pct(21)

        # MA20 괴리율
        if n >= 20:
            ma20 = float(closes.rolling(20).mean().iloc[-1])
            if ma20:
                q.ma20_pct = (q.price / ma20 - 1) * 100

        # RSI 14
        if n >= 15:
            delta = closes.diff()
            gain = delta.clip(lower=0).rolling(14).mean()
            loss = (-delta.clip(upper=0)).rolling(14).mean()
            g = float(gain.iloc[-1])
            lo = float(loss.iloc[-1])
            if lo and lo != 0:
                q.rsi_14 = 100.0 - (100.0 / (1.0 + g / lo))

        # 거래량 비율 (최근 5일 평균 / 20일 평균)
        if vols is not None and len(vols) >= 20:
            v20 = float(vols.rolling(20).mean().iloc[-1])
            v5 = float(vols.tail(5).mean())
            if v20:
                q.vol_ratio = v5 / v20

        q.score, q.signal = _quick_score(q)

    except Exception as exc:
        q.error = str(exc)[:120]
        log.debug("[screener] %s error: %s", symbol, exc)

    return q


def _safe_float(v: Any) -> float | None:
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _quick_score(q: QuickQuote) -> tuple[float, str]:
    """간단한 5차원 점수 (0-100) 산출."""
    # ── 모멘텀 (RSI + MA괴리 + 거래량) ──────────────────────────────────────
    mom = 50.0
    if q.rsi_14 is not None:
        rsi = q.rsi_14
        if 40 <= rsi <= 65:
            mom += 15
        elif rsi < 30:
            mom += 10   # 과매도 반등 기대
        elif rsi > 75:
            mom -= 20
    if q.ma20_pct is not None:
        diff = q.ma20_pct
        if -5 <= diff <= 10:
            mom += 10   # MA20 근방 지지 또는 돌파 초기
        elif diff > 20:
            mom -= 15   # 과열
        elif diff < -15:
            mom -= 10
    if q.vol_ratio is not None and q.vol_ratio > 1.5:
        mom += 10
    mom = max(0.0, min(100.0, mom))

    # ── 최근 가격 추세 ────────────────────────────────────────────────────────
    trend = 50.0
    if q.chg_1d is not None:
        trend += min(10, max(-10, q.chg_1d * 2))
    if q.chg_1w is not None:
        trend += min(15, max(-15, q.chg_1w))
    if q.chg_1m is not None:
        trend += min(15, max(-20, q.chg_1m * 0.5))
    trend = max(0.0, min(100.0, trend))

    # ── 밸류에이션 ────────────────────────────────────────────────────────────
    val = 50.0
    if q.pe_trailing is not None and q.pe_trailing > 0:
        if q.market == "KR":
            if q.pe_trailing < 10:
                val += 20
            elif q.pe_trailing < 18:
                val += 10
            elif q.pe_trailing > 35:
                val -= 15
        else:
            if q.pe_trailing < 18:
                val += 15
            elif q.pe_trailing < 28:
                val += 5
            elif q.pe_trailing > 50:
                val -= 15
    if q.pb is not None and q.pb > 0:
        if q.pb < 1.5:
            val += 10
        elif q.pb > 5:
            val -= 10
    val = max(0.0, min(100.0, val))

    # ── 종합 ─────────────────────────────────────────────────────────────────
    total = mom * 0.40 + trend * 0.35 + val * 0.25
    total = round(total, 1)

    if total >= 72:
        signal = "STRONG_WATCH"
    elif total >= 58:
        signal = "WATCH"
    elif total >= 42:
        signal = "NEUTRAL"
    else:
        signal = "AVOID"

    return total, signal


def run_screener(
    symbols: list[str],
    max_workers: int = _MAX_WORKERS,
    timeout: float = 28.0,
) -> list[QuickQuote]:
    """워치리스트 전체 병렬 수집. timeout 초 내에 완료된 것만 반환."""
    results: list[QuickQuote] = []
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futs = {pool.submit(_fetch_one, sym): sym for sym in symbols}
        for fut in as_completed(futs, timeout=timeout):
            try:
                results.append(fut.result())
            except Exception as exc:
                sym = futs[fut]
                log.warning("[screener] %s timeout/error: %s", sym, exc)
                results.append(QuickQuote(symbol=sym, error=str(exc)[:80]))

    results.sort(key=lambda x: x.score, reverse=True)
    return results
