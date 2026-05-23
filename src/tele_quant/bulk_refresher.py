"""Bulk Refresher — 상위 N종목 펀더멘탈·섹터 자동 갱신.

nightly 타이머로 실행:
- universe 상위 500종목 yfinance 섹터 + 시총 갱신
- Finnhub 컨센서스 갱신 (API 키 보유 시)
- 각 요청 사이 rate limit 배려

공개 정보 기반 리서치 보조. 투자 판단 책임은 사용자에게 있음.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tele_quant.db import Store

log = logging.getLogger(__name__)

_YFINANCE_SLEEP = 0.3   # yfinance 요청 간 대기 (초)
_FINNHUB_SLEEP  = 1.2   # Finnhub free 60 req/min 제한 배려


# ── yfinance 섹터·시총 갱신 ───────────────────────────────────────────────


def _refresh_sector_and_cap(symbol: str) -> dict:
    """yfinance info에서 sector_id + market_cap 추출."""
    try:
        from tele_quant.stock_data_provider import get_ticker_info
        from tele_quant.ticker_universe import detect_sector_from_yfinance

        info = get_ticker_info(symbol) or {}
        sid, label, industry = detect_sector_from_yfinance(symbol)
        mc = info.get("marketCap")
        mc_usd: float | None = None
        if mc:
            # KR 종목은 KRW 단위 → USD 대략 환산 (1400원 기준)
            mc_usd = float(mc) / 1400 if symbol.endswith((".KS", ".KQ", ".KN")) else float(mc)
        return {
            "symbol": symbol,
            "sector_id": sid,
            "sector_label": label,
            "industry": industry,
            "market_cap_usd": mc_usd,
            "name_en": info.get("shortName") or info.get("longName") or "",
        }
    except Exception as exc:
        log.debug("[bulk] sector/cap failed %s: %s", symbol, exc)
        return {"symbol": symbol}


# ── Finnhub 컨센서스 갱신 ─────────────────────────────────────────────────


def _refresh_finnhub_consensus(symbol: str, api_key: str) -> dict | None:
    """Finnhub price target + recommendation 조회."""
    try:
        import json as _json
        import urllib.request

        # KR 종목은 Finnhub 지원 제한 — 기본 US ticker 형식만
        sym = symbol.split(".")[0] if "." in symbol else symbol
        url = (
            f"https://finnhub.io/api/v1/stock/price-target"
            f"?symbol={sym}&token={api_key}"
        )
        with urllib.request.urlopen(url, timeout=10) as r:
            data = _json.loads(r.read())
        if data.get("targetMean"):
            return {
                "symbol": symbol,
                "target_mean": data.get("targetMean"),
                "target_high": data.get("targetHigh"),
                "target_low": data.get("targetLow"),
                "analyst_count": data.get("numberOfAnalysts"),
            }
    except Exception as exc:
        log.debug("[bulk] finnhub failed %s: %s", symbol, exc)
    return None


# ── 메인 갱신 함수 ────────────────────────────────────────────────────────


def run_bulk_refresh(
    store: Store,  # type: ignore[name-defined]
    market: str = "ALL",
    limit: int = 500,
    finnhub_api_key: str = "",
) -> dict[str, int]:
    """universe 상위 N종목 섹터·시총 갱신.

    Returns: {"updated": n, "failed": n}
    """
    symbols = store.get_universe_symbols(market=market if market != "ALL" else "", limit=limit)
    log.info("[bulk] 갱신 대상: %d 종목 (market=%s, limit=%d)", len(symbols), market, limit)

    updated = 0
    failed = 0
    batch: list[dict] = []

    for sym in symbols:
        result = _refresh_sector_and_cap(sym)
        if result.get("sector_id") or result.get("market_cap_usd"):
            batch.append(result)
        else:
            failed += 1

        # 100개마다 DB 일괄 저장
        if len(batch) >= 100:
            store.upsert_ticker_universe(batch)
            updated += len(batch)
            log.info("[bulk] %d/%d 저장", updated, len(symbols))
            batch.clear()

        time.sleep(_YFINANCE_SLEEP)

        # Finnhub 컨센서스 (US 종목 + API 키 있을 때)
        if finnhub_api_key and not sym.endswith((".KS", ".KQ", ".KN")):
            _refresh_finnhub_consensus(sym, finnhub_api_key)
            time.sleep(_FINNHUB_SLEEP)

    if batch:
        store.upsert_ticker_universe(batch)
        updated += len(batch)

    log.info("[bulk] 완료 — updated=%d failed=%d", updated, failed)
    return {"updated": updated, "failed": failed}


def run_nightly_refresh(store: Store, settings: object | None = None) -> dict[str, int]:  # type: ignore[name-defined]
    """systemd nightly 타이머에서 호출하는 진입점."""
    finnhub_key = ""
    if settings is not None:
        finnhub_key = getattr(settings, "finnhub_api_key", "") or ""

    result = run_bulk_refresh(store, market="ALL", limit=500, finnhub_api_key=finnhub_key)
    return result
