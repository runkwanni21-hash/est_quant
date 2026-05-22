"""티커 해소기 — 변경/신규 상장/OTC/마이크로캡 처리.

yfinance 조회 실패 시 SEC EDGAR 공개 API로 fallback 검색.
공개 정보 기반 리서치 보조. 투자 판단 책임은 사용자에게 있음.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

log = logging.getLogger(__name__)

__all__ = [
    "TickerResolution",
    "cap_bucket_label",
    "resolve_ticker",
]

_OTC_EXCHANGES = frozenset({"OTC", "PNK", "PINK", "OTCBB", "OTCQB", "OTCQX"})

# (시총 USD 하한, 레이블)  — 내림차순
_CAP_BUCKETS: list[tuple[float, str]] = [
    (200_000_000_000, "메가캡 ($200B+)"),
    (10_000_000_000,  "대형주 ($10B+)"),
    (2_000_000_000,   "중형주 ($2B+)"),
    (300_000_000,     "소형주 ($300M+)"),
    (50_000_000,      "마이크로캡 ($50M+)"),
    (0,               "나노캡 (<$50M)"),
]


@dataclass
class TickerResolution:
    original_symbol: str
    resolved_symbol: str
    long_name: str = ""
    exchange: str = ""            # NYSE / NASDAQ / OTC / …
    cap_bucket: str = ""          # 대형주 / 마이크로캡 / …
    is_otc: bool = False
    is_recent_ipo: bool = False   # IPO 90일 이내
    ticker_changed: bool = False  # SEC EDGAR에서 다른 티커 발견
    data_available: bool = True
    warnings: list[str] = field(default_factory=list)


def cap_bucket_label(market_cap_usd: float | None) -> str:
    """시총(USD) → 버킷 레이블."""
    if market_cap_usd is None:
        return "시총 미확인"
    for threshold, label in _CAP_BUCKETS:
        if market_cap_usd >= threshold:
            return label
    return "나노캡 (<$50M)"


def resolve_ticker(symbol: str, market: str = "") -> TickerResolution:
    """심볼 유효성 + 시장 분류 + 티커 변경 탐지.

    1. yfinance info 조회
    2. 데이터 없으면 SEC EDGAR 공개 API fallback (US only)
    3. OTC/Pink sheet, 마이크로캡 유동성 경고
    4. 최근 IPO (90일 이내) 감지
    """
    res = TickerResolution(original_symbol=symbol, resolved_symbol=symbol)

    try:
        from tele_quant.stock_data_provider import get_ticker_info

        info = get_ticker_info(symbol)

        # 유효성: 가격 또는 사명이 있어야 함
        price = (
            info.get("currentPrice")
            or info.get("regularMarketPrice")
            or info.get("previousClose")
        )
        has_name = bool(info.get("longName") or info.get("shortName"))

        if not price and not has_name:
            if market.upper() != "KR":
                # SEC EDGAR fallback (US 전용)
                new_sym = _sec_edgar_lookup(symbol)
                if new_sym and new_sym != symbol.upper():
                    res.resolved_symbol = new_sym
                    res.ticker_changed = True
                    res.warnings.append(f"티커 변경 감지: {symbol} → {new_sym}")
                    from tele_quant.stock_data_provider import invalidate
                    invalidate(symbol)
                    info = get_ticker_info(new_sym)
                else:
                    res.data_available = False
                    res.warnings.append(
                        f"⚠ 티커 '{symbol}' — 데이터 없음. 변경·상폐·오타 확인 필요."
                    )
            else:
                res.data_available = False
                res.warnings.append(
                    f"⚠ 티커 '{symbol}' — yfinance KR 데이터 없음."
                )

        raw_long = info.get("longName") or ""
        raw_short = info.get("shortName") or ""
        # shortName sometimes comes back as "222420.KS,0P00016I29,14567" (yfinance bug)
        clean_name = ""
        for candidate in (raw_long, raw_short):
            if candidate and "," not in candidate and candidate != symbol:
                clean_name = candidate
                break
        # KR stocks: fall back to pykrx → DART if yfinance has no clean name
        if not clean_name and market.upper() == "KR":
            bare = symbol.split(".")[0]
            try:
                from pykrx import stock as _pykrx
                pykrx_name = _pykrx.get_market_ticker_name(bare)
                if pykrx_name and pykrx_name != bare:
                    clean_name = pykrx_name
            except Exception as _pykrx_exc:
                log.debug("[ticker_resolver] pykrx name fallback failed %s: %s", symbol, _pykrx_exc)
            if not clean_name:
                try:
                    from tele_quant.opendart_client import fetch_dart_corp_name
                    from tele_quant.settings import Settings as _Cfg
                    _dart_key = getattr(_Cfg(), "opendart_api_key", "") or ""
                    dart_name = fetch_dart_corp_name(bare, _dart_key) if _dart_key else None
                    if dart_name:
                        clean_name = dart_name
                except Exception as _dart_exc:
                    log.debug("[ticker_resolver] DART name fallback failed %s: %s", symbol, _dart_exc)
        res.long_name = clean_name or symbol

        # 거래소 분류
        exchange = (info.get("exchange") or info.get("exchangeShortName") or "").upper()
        res.exchange = exchange
        res.is_otc = exchange in _OTC_EXCHANGES

        if res.is_otc:
            res.warnings.append(
                f"OTC/Pink sheet ({exchange}) — 규제·공시·유동성 제한적"
            )

        # 시총 버킷
        mc = info.get("marketCap")
        if mc:
            mc_usd = float(mc)
            res.cap_bucket = cap_bucket_label(mc_usd)
            if mc_usd < 50_000_000:
                res.warnings.append("나노캡 — 변동성 극심, 유동성 매우 제한")
            elif mc_usd < 300_000_000:
                res.warnings.append("마이크로캡 — bid-ask 스프레드·슬리피지 주의")
        else:
            res.cap_bucket = "시총 미확인"

        # 최근 IPO 감지 (90일 이내)
        first_ms = info.get("firstTradeDateMilliseconds") or info.get("firstTradeDateEpochUtc")
        if first_ms:
            import time as _time

            age_days = (_time.time() * 1000 - float(first_ms)) / (1000 * 86400)
            if age_days < 90:
                res.is_recent_ipo = True
                res.warnings.append(
                    f"최근 IPO (약 {int(age_days)}일 전) — 실적 데이터 제한적"
                )

    except Exception as exc:
        log.debug("[ticker_resolver] 조회 실패 %s: %s", symbol, exc)
        res.data_available = False
        res.warnings.append(f"티커 조회 실패: {exc}")

    return res


def _sec_edgar_lookup(symbol: str) -> str | None:
    """SEC EDGAR 공개 검색 API로 현재 유효 티커 파악.

    3초 타임아웃. 실패 시 None 반환.
    """
    import json
    import urllib.request

    try:
        enc = symbol.upper().replace(" ", "+")
        url = (
            "https://efts.sec.gov/LATEST/search-index"
            f"?q=%22{enc}%22&forms=10-K&dateRange=custom&startdt=2020-01-01"
        )
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "tele_quant/1.0 research@tele-quant.local"},
        )
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read())

        hits = (data.get("hits") or {}).get("hits") or []
        for hit in hits[:5]:
            src = hit.get("_source") or {}
            tickers = src.get("tickers") or []
            if tickers:
                return str(tickers[0]).upper()

        return None
    except Exception as exc:
        log.debug("[ticker_resolver] SEC EDGAR lookup 실패 %s: %s", symbol, exc)
        return None
