"""Ticker Universe — KR/US 5000+ 종목 메타데이터 관리.

데이터 소스 (무료·공개):
- KR: pykrx (KOSPI + KOSDAQ + KONEX) — 한국거래소 공개 데이터
- US: NASDAQ Trader (nasdaqtrader.com) — 무료 TSV, API 키 불필요
- 섹터: yfinance GICS + config/ticker_sector_overrides.yml override

자동 갱신:
- 주 1회 universe rebuild (systemd 타이머)
- 일 1회 상위 500종목 fundamentals refresh (bulk_refresher)
"""

from __future__ import annotations

import logging
import re
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from tele_quant.db import Store

log = logging.getLogger(__name__)

_CONF_DIR = Path(__file__).parent.parent.parent / "config"
_OVERRIDE_PATH = _CONF_DIR / "ticker_sector_overrides.yml"

# NASDAQ Trader 파일 URL — 주 URL + fallback (WSL 환경에서 ftp subdomain 차단 사례 있음)
_NASDAQ_LISTED_URLS = [
    "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt",
    "https://ftp.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt",
]
_OTHER_LISTED_URLS = [
    "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt",
    "https://ftp.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt",
]

# SEC EDGAR 전 상장사 티커 JSON (무료·공식, NASDAQ Trader 실패 시 fallback)
_SEC_COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"

# ── GICS sector/industry → sector_id 매핑 ──────────────────────────────────

_GICS_INDUSTRY_TO_SECTOR: dict[str, str] = {
    # 반도체
    "Semiconductors": "ai_semiconductor_hbm_foundry",
    "Semiconductor Equipment & Materials": "semicap_equipment_materials_osat",
    "Electronic Components": "semicap_equipment_materials_osat",
    "Electronics": "semicap_equipment_materials_osat",
    # AI/소프트웨어/클라우드
    "Software—Infrastructure": "ai_software_cloud_cybersecurity",
    "Software—Application": "ai_software_cloud_cybersecurity",
    "Information Technology Services": "ai_software_cloud_cybersecurity",
    "Internet Content & Information": "ai_software_cloud_cybersecurity",
    "Cloud Computing": "ai_software_cloud_cybersecurity",
    "Cybersecurity": "ai_software_cloud_cybersecurity",
    # 바이오/제약
    "Biotechnology": "biotech_pharma_clinical_medtech",
    "Drug Manufacturers—General": "biotech_pharma_clinical_medtech",
    "Drug Manufacturers—Specialty & Generic": "biotech_pharma_clinical_medtech",
    "Pharmaceutical Retailers": "biotech_pharma_clinical_medtech",
    "Life Sciences Tools & Services": "cdmo_bioproduction_adc",
    "Diagnostics & Research": "healthcare_services_hospitals_diagnostics",
    "Medical Devices": "healthcare_services_hospitals_diagnostics",
    "Medical Instruments & Supplies": "healthcare_services_hospitals_diagnostics",
    "Health Information Services": "healthcare_services_hospitals_diagnostics",
    "Healthcare Plans": "healthcare_services_hospitals_diagnostics",
    "Medical Care Facilities": "healthcare_services_hospitals_diagnostics",
    # 전력/원전
    "Utilities—Regulated Electric": "ai_power_grid_copper_nuclear",
    "Utilities—Renewable": "ai_power_grid_copper_nuclear",
    "Utilities—Independent Power Producers": "ai_power_grid_copper_nuclear",
    "Electrical Equipment & Parts": "ai_power_grid_copper_nuclear",
    # 방산/우주
    "Aerospace & Defense": "defense_space_aerospace_drone",
    # 자동차/EV
    "Auto Manufacturers": "auto_ev_autonomous_robotaxi",
    "Auto Parts": "auto_ev_autonomous_robotaxi",
    "Auto & Truck Dealerships": "auto_ev_autonomous_robotaxi",
    # 배터리/소재
    "Specialty Chemicals": "battery_materials_lithium_recycling",
    "Basic Materials": "materials_chemicals_steel",
    "Chemicals": "materials_chemicals_steel",
    "Steel": "materials_chemicals_steel",
    "Other Industrial Metals & Mining": "materials_chemicals_steel",
    "Copper": "ai_power_grid_copper_nuclear",
    "Aluminum": "materials_chemicals_steel",
    "Gold": "materials_chemicals_steel",
    "Silver": "materials_chemicals_steel",
    # 조선/해운
    "Marine Shipping": "shipbuilding_shipping_lng_equipment",
    "Integrated Freight & Logistics": "shipbuilding_shipping_lng_equipment",
    # 금융
    "Banks—Regional": "financials_banks_insurance_brokers",
    "Banks—Diversified": "financials_banks_insurance_brokers",
    "Insurance—Diversified": "financials_banks_insurance_brokers",
    "Insurance—Life": "financials_banks_insurance_brokers",
    "Insurance—Property & Casualty": "financials_banks_insurance_brokers",
    "Asset Management": "financials_banks_insurance_brokers",
    "Capital Markets": "financials_banks_insurance_brokers",
    "Financial Conglomerates": "financials_banks_insurance_brokers",
    "Credit Services": "payments_crypto_exchange_brokerage",
    "Financial Data & Stock Exchanges": "payments_crypto_exchange_brokerage",
    # 에너지
    "Oil & Gas Integrated": "energy_oil_lng_renewables",
    "Oil & Gas E&P": "energy_oil_lng_renewables",
    "Oil & Gas Refining & Marketing": "energy_oil_lng_renewables",
    "Oil & Gas Midstream": "energy_oil_lng_renewables",
    "Oil & Gas Equipment & Services": "energy_oil_lng_renewables",
    # 건설/리츠
    "Real Estate—General": "construction_infra_reits_cement",
    "REIT—Industrial": "construction_infra_reits_cement",
    "REIT—Office": "construction_infra_reits_cement",
    "REIT—Retail": "construction_infra_reits_cement",
    "REIT—Residential": "construction_infra_reits_cement",
    "REIT—Diversified": "construction_infra_reits_cement",
    "REIT—Healthcare Facilities": "construction_infra_reits_cement",
    "Engineering & Construction": "construction_infra_reits_cement",
    # 통신
    "Telecom Services": "telecom_network_smartphone_equipment",
    "Communication Equipment": "telecom_network_smartphone_equipment",
    "Consumer Electronics": "telecom_network_smartphone_equipment",
    # 미디어/게임/엔터
    "Entertainment": "media_content_gaming_entertainment_ads",
    "Electronic Gaming & Multimedia": "media_content_gaming_entertainment_ads",
    "Broadcasting": "media_content_gaming_entertainment_ads",
    "Publishing": "media_content_gaming_entertainment_ads",
    "Advertising Agencies": "media_content_gaming_entertainment_ads",
    "Internet Advertising": "media_content_gaming_entertainment_ads",
    # 유통/여행/카지노
    "Specialty Retail": "retail_ecommerce_logistics_travel_airline_casino",
    "Internet Retail": "retail_ecommerce_logistics_travel_airline_casino",
    "Department Stores": "retail_ecommerce_logistics_travel_airline_casino",
    "Grocery Stores": "retail_ecommerce_logistics_travel_airline_casino",
    "Airlines": "retail_ecommerce_logistics_travel_airline_casino",
    "Hotels & Motels": "retail_ecommerce_logistics_travel_airline_casino",
    "Resorts & Casinos": "retail_ecommerce_logistics_travel_airline_casino",
    "Restaurants": "retail_ecommerce_logistics_travel_airline_casino",
    # 음식료
    "Packaged Foods": "food_agriculture_fertilizer_staples",
    "Farm Products": "food_agriculture_fertilizer_staples",
    "Agricultural Inputs": "food_agriculture_fertilizer_staples",
    "Beverages—Non-Alcoholic": "food_agriculture_fertilizer_staples",
    "Beverages—Brewers": "food_agriculture_fertilizer_staples",
    "Tobacco Products": "food_agriculture_fertilizer_staples",
    # 산업재/기계/로봇
    "Specialty Industrial Machinery": "industrials_machinery_automation_robotics",
    "Industrial Conglomerates": "industrials_machinery_automation_robotics",
    "Farm & Heavy Construction Machinery": "industrials_machinery_automation_robotics",
    "Tools & Accessories": "industrials_machinery_automation_robotics",
    # K뷰티/소비재
    "Personal Products": "kbeauty_cosmetics_odm_consumer",
    "Household & Personal Products": "kbeauty_cosmetics_odm_consumer",
    # 환경
    "Waste Management": "environment_waste_water_carbon_infra",
    "Water Utilities": "environment_waste_water_carbon_infra",
}

_GICS_SECTOR_TO_SECTOR: dict[str, str] = {
    "Technology": "ai_software_cloud_cybersecurity",
    "Healthcare": "biotech_pharma_clinical_medtech",
    "Communication Services": "media_content_gaming_entertainment_ads",
    "Consumer Discretionary": "retail_ecommerce_logistics_travel_airline_casino",
    "Consumer Staples": "food_agriculture_fertilizer_staples",
    "Financials": "financials_banks_insurance_brokers",
    "Industrials": "industrials_machinery_automation_robotics",
    "Energy": "energy_oil_lng_renewables",
    "Materials": "materials_chemicals_steel",
    "Real Estate": "construction_infra_reits_cement",
    "Utilities": "ai_power_grid_copper_nuclear",
}

# ── sector_id → label ─────────────────────────────────────────────────────

_SECTOR_LABELS: dict[str, str] = {
    "ai_semiconductor_hbm_foundry": "AI 반도체/HBM/파운드리",
    "semicap_equipment_materials_osat": "반도체 장비/소재/OSAT",
    "ai_software_cloud_cybersecurity": "AI 소프트웨어/클라우드/보안",
    "ai_power_grid_copper_nuclear": "AI 전력/전선/원전",
    "biotech_pharma_clinical_medtech": "바이오/제약/임상",
    "cdmo_bioproduction_adc": "CDMO/바이오생산/ADC",
    "shipbuilding_shipping_lng_equipment": "조선/해운/LNG",
    "defense_space_aerospace_drone": "방산/우주/드론",
    "auto_ev_autonomous_robotaxi": "자동차/EV/로봇택시",
    "battery_materials_lithium_recycling": "배터리/소재/리튬",
    "financials_banks_insurance_brokers": "금융/은행/보험/증권",
    "energy_oil_lng_renewables": "에너지/정유/재생",
    "materials_chemicals_steel": "소재/화학/철강",
    "construction_infra_reits_cement": "건설/인프라/리츠",
    "kbeauty_cosmetics_odm_consumer": "K뷰티/소비재",
    "retail_ecommerce_logistics_travel_airline_casino": "유통/여행/항공/카지노",
    "media_content_gaming_entertainment_ads": "미디어/게임/엔터",
    "telecom_network_smartphone_equipment": "통신/네트워크/광통신",
    "food_agriculture_fertilizer_staples": "음식료/농업/비료",
    "industrials_machinery_automation_robotics": "산업재/기계/로봇",
    "payments_crypto_exchange_brokerage": "결제/크립토/브로커리지",
    "healthcare_services_hospitals_diagnostics": "의료서비스/병원/진단",
    "environment_waste_water_carbon_infra": "환경/수처리/탄소",
    "macro_sensitive_rates_fx_commodities": "매크로 민감주",
}

# ── override 로딩 ─────────────────────────────────────────────────────────

_OVERRIDES: dict[str, str] | None = None


def _load_overrides() -> dict[str, str]:
    global _OVERRIDES
    if _OVERRIDES is not None:
        return _OVERRIDES
    try:
        import yaml
        data = yaml.safe_load(_OVERRIDE_PATH.read_text(encoding="utf-8")) or {}
        _OVERRIDES = data.get("overrides", {})
    except Exception as exc:
        log.warning("[universe] override load failed: %s", exc)
        _OVERRIDES = {}
    return _OVERRIDES  # type: ignore[return-value]


# ── 섹터 감지 ─────────────────────────────────────────────────────────────


def detect_sector_from_yfinance(symbol: str) -> tuple[str, str, str]:
    """yfinance GICS → (sector_id, sector_label, industry).

    Returns 빈 문자열 튜플 on failure.
    """
    try:
        from tele_quant.stock_data_provider import get_ticker_info

        info = get_ticker_info(symbol) or {}
        industry = info.get("industry", "") or ""
        gics_sector = info.get("sector", "") or ""

        overrides = _load_overrides()
        # 1순위: override
        if symbol in overrides:
            sid = overrides[symbol]
            return sid, _SECTOR_LABELS.get(sid, sid), industry

        # 2순위: industry (더 세밀)
        sid = _GICS_INDUSTRY_TO_SECTOR.get(industry, "")
        if not sid:
            # 3순위: broad GICS sector
            sid = _GICS_SECTOR_TO_SECTOR.get(gics_sector, "")

        label = _SECTOR_LABELS.get(sid, gics_sector or industry)
        return sid, label, industry
    except Exception as exc:
        log.debug("[universe] yfinance sector failed %s: %s", symbol, exc)
        return "", "", ""


def get_sector_id(symbol: str, store: Store | None = None) -> str:  # type: ignore[name-defined]
    """sector_id 조회. override → DB universe → yfinance GICS → detect_seed_sector 순."""
    # 1순위: override 파일
    overrides = _load_overrides()
    if symbol in overrides:
        return overrides[symbol]

    # 2순위: DB universe 캐시
    if store is not None:
        try:
            sid = store.get_ticker_sector(symbol)
            if sid:
                return sid
        except Exception:
            pass

    # 3순위: yfinance GICS
    sid, _, _ = detect_sector_from_yfinance(symbol)
    if sid:
        return sid

    # 4순위: 기존 detect_seed_sector fallback
    try:
        from tele_quant.sector_macro import detect_seed_sector
        return detect_seed_sector(symbol, store) or ""
    except Exception:
        return ""


def get_display_name(symbol: str, store: Store | None = None) -> str:  # type: ignore[name-defined]
    """종목명 조회. DB universe → 기존 _NAME_MAP → symbol."""
    if store is not None:
        try:
            name = store.get_ticker_name(symbol)
            if name and name != symbol:
                return name
        except Exception:
            pass
    try:
        from tele_quant.relation_feed import _NAME_MAP
        return _NAME_MAP.get(symbol, symbol)
    except Exception:
        return symbol


# ── KR universe 빌드 ──────────────────────────────────────────────────────


def _build_kr_universe() -> list[dict[str, Any]]:
    """pykrx로 KOSPI + KOSDAQ + KONEX 전 종목 수집."""
    rows: list[dict[str, Any]] = []
    try:
        from pykrx import stock

        overrides = _load_overrides()
        for market_code, exch in [("KOSPI", "KS"), ("KOSDAQ", "KQ"), ("KONEX", "KN")]:
            try:
                tickers = stock.get_market_ticker_list(market=market_code)
            except Exception as exc:
                log.warning("[universe] pykrx %s list failed: %s", market_code, exc)
                continue

            log.info("[universe] KR %s: %d tickers", market_code, len(tickers))
            for ticker in tickers:
                if not ticker or not ticker.isdigit():
                    continue
                symbol = f"{ticker}.{exch}"
                try:
                    name = stock.get_market_ticker_name(ticker) or ticker
                except Exception:
                    name = ticker

                sid = overrides.get(symbol, "")
                rows.append({
                    "symbol": symbol,
                    "name_ko": name,
                    "name_en": "",
                    "market": "KR",
                    "exchange": market_code,
                    "sector_id": sid,
                    "sector_label": _SECTOR_LABELS.get(sid, ""),
                    "industry": "",
                    "market_cap_usd": None,
                    "is_active": True,
                    "is_etf": False,
                })
                time.sleep(0.01)  # pykrx rate limit 배려

    except ImportError:
        log.warning("[universe] pykrx not available — KR universe skipped")
    except Exception as exc:
        log.warning("[universe] KR universe failed: %s", exc)
    return rows


# ── US universe 빌드 ──────────────────────────────────────────────────────


def _parse_nasdaq_trader_file(urls: list[str], market: str) -> list[dict[str, Any]]:
    """NASDAQ Trader TSV 파싱. 여러 URL 순서대로 시도."""
    rows: list[dict[str, Any]] = []
    import urllib.request
    content = ""
    for url in urls:
        try:
            with urllib.request.urlopen(url, timeout=15) as resp:
                content = resp.read().decode("utf-8", errors="replace")
            if content:
                break
        except Exception as exc:
            log.debug("[universe] NASDAQ Trader %s failed: %s", url, exc)
    if not content:
        log.warning("[universe] NASDAQ Trader all URLs failed for market=%s", market)
        return rows
    try:

        lines = content.splitlines()
        if not lines:
            return rows

        header = lines[0].split("|")
        header = [h.strip() for h in header]

        for line in lines[1:]:
            if not line.strip() or line.startswith("File Creation"):
                continue
            parts = line.split("|")
            if len(parts) < len(header):
                continue
            row = dict(zip(header, parts, strict=False))

            sym = (row.get("Symbol") or row.get("ACT Symbol") or "").strip()
            if not sym or sym == "Symbol":
                continue

            # 테스트 이슈 제외
            if (row.get("Test Issue") or "").strip().upper() == "Y":
                continue

            # ETF 여부
            is_etf = (row.get("ETF") or "").strip().upper() == "Y"

            name = (row.get("Security Name") or "").strip()
            # 주식 유형 약칭 제거 (Common Stock, ADR, etc.)
            name = re.sub(r"\s*[- ]\s*Common Stock.*$", "", name, flags=re.I)
            name = re.sub(r"\s*[- ]\s*Class [A-Z].*$", "", name, flags=re.I)

            # 거래소 코드
            exch_code = (row.get("Exchange") or row.get("Market Category") or "").strip()

            rows.append({
                "symbol": sym,
                "name_ko": "",
                "name_en": name,
                "market": "US",
                "exchange": market,
                "sector_id": "",
                "sector_label": "",
                "industry": "",
                "market_cap_usd": None,
                "is_active": True,
                "is_etf": is_etf,
                "_exch_code": exch_code,
            })
    except Exception as exc:
        log.warning("[universe] NASDAQ Trader parse failed: %s", exc)
    return rows


def _fetch_sec_edgar_tickers() -> list[dict[str, Any]]:
    """SEC EDGAR company_tickers.json → US 상장사 목록 (NASDAQ Trader fallback)."""
    rows: list[dict[str, Any]] = []
    try:
        import json
        import urllib.request

        req = urllib.request.Request(
            _SEC_COMPANY_TICKERS_URL,
            headers={"User-Agent": "tele-quant research@example.com"},
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read())

        overrides = _load_overrides()
        for entry in data.values():
            sym = (entry.get("ticker") or "").strip().upper()
            if not sym or re.fullmatch(r"\d+", sym):
                continue
            if len(sym) >= 5 and re.search(r"[WRU]$", sym):
                continue
            name = (entry.get("title") or "").strip()
            sid = overrides.get(sym, "")
            rows.append({
                "symbol": sym,
                "name_ko": "",
                "name_en": name,
                "market": "US",
                "exchange": "US",
                "sector_id": sid,
                "sector_label": _SECTOR_LABELS.get(sid, ""),
                "industry": "",
                "market_cap_usd": None,
                "is_active": True,
                "is_etf": False,
            })
        log.info("[universe] SEC EDGAR: %d tickers", len(rows))
    except Exception as exc:
        log.warning("[universe] SEC EDGAR fallback failed: %s", exc)
    return rows


def _build_us_universe(include_etf: bool = False) -> list[dict[str, Any]]:
    """NASDAQ + NYSE + AMEX 전 종목 수집. NASDAQ Trader 실패 시 SEC EDGAR fallback."""
    overrides = _load_overrides()

    nasdaq_rows = _parse_nasdaq_trader_file(_NASDAQ_LISTED_URLS, "NASDAQ")
    other_rows = _parse_nasdaq_trader_file(_OTHER_LISTED_URLS, "NYSE")

    # NASDAQ Trader 둘 다 실패 시 SEC EDGAR fallback
    if not nasdaq_rows and not other_rows:
        log.info("[universe] NASDAQ Trader 불가 → SEC EDGAR fallback 시도")
        return _fetch_sec_edgar_tickers()

    all_rows: list[dict[str, Any]] = []
    seen: set[str] = set()

    for r in nasdaq_rows + other_rows:
        sym = r["symbol"]
        if not sym or sym in seen:
            continue

        # 숫자만 있는 심볼 제외 (가격 오인 방지)
        if re.fullmatch(r"\d+", sym):
            continue
        # 5자 이상 + 특수 suffix는 warrant/right/unit — 제외
        if re.search(r"[WRU+]$", sym) and len(sym) >= 5:
            continue

        if r.get("is_etf") and not include_etf:
            continue

        seen.add(sym)
        # override 적용
        if sym in overrides:
            r["sector_id"] = overrides[sym]
            r["sector_label"] = _SECTOR_LABELS.get(overrides[sym], "")

        r.pop("_exch_code", None)
        all_rows.append(r)

    log.info("[universe] US: %d tickers (ETF 포함: %s)", len(all_rows), include_etf)
    return all_rows


# ── 메인 빌드 함수 ────────────────────────────────────────────────────────


def build_universe(
    market: str = "ALL",
    store: Store | None = None,  # type: ignore[name-defined]
    include_etf: bool = False,
) -> dict[str, int]:
    """전체 ticker universe 빌드 → DB 저장.

    Returns: {"KR": n, "US": n, "total": n}
    """
    rows: list[dict[str, Any]] = []

    if market.upper() in ("ALL", "KR"):
        kr = _build_kr_universe()
        rows.extend(kr)
        log.info("[universe] KR collected: %d", len(kr))

    if market.upper() in ("ALL", "US"):
        us = _build_us_universe(include_etf=include_etf)
        rows.extend(us)
        log.info("[universe] US collected: %d", len(us))

    if store is None:
        log.warning("[universe] store=None — DB 저장 생략")
        return {"KR": sum(1 for r in rows if r["market"] == "KR"),
                "US": sum(1 for r in rows if r["market"] == "US"),
                "total": len(rows)}

    store.upsert_ticker_universe(rows)
    counts = store.get_universe_count()
    log.info("[universe] DB 저장 완료: %s", counts)
    return counts


# ── symbol 유효성 검사 ────────────────────────────────────────────────────


_NUMERIC_RE = re.compile(r"^\d+$")
_VALID_US_RE = re.compile(r"^[A-Z]{1,5}(-[A-Z])?$")
_VALID_KR_RE = re.compile(r"^\d{6}\.(KS|KQ|KN)$")


def is_valid_symbol(symbol: str) -> bool:
    """체인 후보 등에서 숫자만/이상한 심볼 필터링."""
    if not symbol:
        return False
    # KR 심볼 우선 처리 (KR 티커는 6자리 숫자가 정상)
    if symbol.endswith((".KS", ".KQ", ".KN")):
        return bool(_VALID_KR_RE.fullmatch(symbol))
    # 숫자만으로 이루어진 심볼 제외 ($432, 17856 등 가격 오인)
    bare = symbol.split(".")[0]
    if _NUMERIC_RE.fullmatch(bare):
        return False
    # 5자 이상 + W/R/U suffix → warrant/right/unit 제외
    if len(symbol) >= 5 and re.search(r"[WRU]$", symbol):
        return False
    # US: 1~5자 대문자 (BRK-B 등 하이픈 허용)
    return bool(_VALID_US_RE.fullmatch(symbol))
