"""Sector-specific macro indicator snapshot for /분석.

섹터별 핵심 매크로 지표(yfinance 티커)를 가져와 1주 변화율과 함께
호재/주의 신호를 Telegram 텍스트로 포맷한다.

공개 정보 기반 리서치 보조. 투자 판단 책임은 사용자에게 있음.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tele_quant.db import Store

log = logging.getLogger(__name__)

__all__ = [
    "SECTOR_MACRO_MAP",
    "SectorMacroItem",
    "detect_seed_sector",
    "fetch_sector_macro_snapshot",
    "format_sector_macro",
    "guess_sector_id",
]


# ── Data model ────────────────────────────────────────────────────────────────


@dataclass
class SectorMacroItem:
    """단일 매크로 지표 정의."""

    label: str                      # 표시 이름 (예: "10Y 국채금리")
    ticker: str                     # yfinance 티커 (예: "^TNX")
    unit: str = "%"                 # 값 단위 (%, pt, $, ...)
    up_is_positive: bool | None = None  # True=상승 호재, False=상승 악재, None=중립
    note: str = ""                  # 추가 설명


@dataclass
class SectorMacroSnapshot:
    """실시간 조회 결과 + 포맷용 데이터."""

    item: SectorMacroItem
    current: float | None = None
    change_1w_pct: float | None = None   # 1주 변화율(%)
    change_1w_abs: float | None = None   # 1주 절대 변화량
    signal: str = ""                     # ✅ 호재 / ⚠ 주의 / —


# ── 섹터별 매크로 지표 맵 ─────────────────────────────────────────────────────


SECTOR_MACRO_MAP: dict[str, list[SectorMacroItem]] = {
    # AI 반도체 / HBM / 파운드리
    "ai_semiconductor_hbm_foundry": [
        SectorMacroItem("SOXX (반도체ETF)", "SOXX", "%", True),
        SectorMacroItem("NVDA", "NVDA", "%", True),
        SectorMacroItem("10Y 국채금리", "^TNX", "pt", False, "금리 상승 → 성장주 할인율 확대"),
        SectorMacroItem("달러인덱스(DXY)", "DX-Y.NYB", "pt", None),
    ],
    # 반도체 장비 / 소재 / OSAT
    "semicap_equipment_materials_osat": [
        SectorMacroItem("SOXX (반도체ETF)", "SOXX", "%", True),
        SectorMacroItem("AMAT (장비 리더)", "AMAT", "%", True),
        SectorMacroItem("구리선물(HG)", "HG=F", "$", True, "DRAM 패키징·기판 원재료"),
        SectorMacroItem("10Y 국채금리", "^TNX", "pt", False),
    ],
    # AI 소프트웨어 / 클라우드 / 사이버보안
    "ai_software_cloud_cybersecurity": [
        SectorMacroItem("QQQ (나스닥100)", "QQQ", "%", True),
        SectorMacroItem("10Y 국채금리", "^TNX", "pt", False, "DCF 할인율 직결"),
        SectorMacroItem("VIX (공포지수)", "^VIX", "pt", False),
        SectorMacroItem("달러인덱스(DXY)", "DX-Y.NYB", "pt", False, "글로벌 SaaS 환헤지"),
    ],
    # AI 전력그리드 / 구리 / 원전
    "ai_power_grid_copper_nuclear": [
        SectorMacroItem("구리선물(HG)", "HG=F", "$", True, "전력 인프라 핵심 소재"),
        SectorMacroItem("천연가스(NG)", "NG=F", "$", None),
        SectorMacroItem("XLU (유틸리티ETF)", "XLU", "%", True),
        SectorMacroItem("10Y 국채금리", "^TNX", "pt", False, "인프라 부채비용"),
    ],
    # 바이오테크 / 제약 / 임상 / 의료기기
    "biotech_pharma_clinical_medtech": [
        SectorMacroItem("XBI (바이오테크ETF)", "XBI", "%", True),
        SectorMacroItem("10Y 국채금리", "^TNX", "pt", False, "성장주 할인율"),
        SectorMacroItem("달러인덱스(DXY)", "DX-Y.NYB", "pt", False, "해외매출 환위험"),
        SectorMacroItem("VIX (공포지수)", "^VIX", "pt", False),
    ],
    # CDMO / 바이오프로덕션 / ADC
    "cdmo_bioproduction_adc": [
        SectorMacroItem("XBI (바이오테크ETF)", "XBI", "%", True),
        SectorMacroItem("10Y 국채금리", "^TNX", "pt", False),
        SectorMacroItem("달러인덱스(DXY)", "DX-Y.NYB", "pt", False),
    ],
    # 조선 / 해운 / LNG 기자재
    "shipbuilding_shipping_lng_equipment": [
        SectorMacroItem("발틱건화물지수(BDI)", "BDRY", "%", True, "벌크선 수요 대리지표"),
        SectorMacroItem("천연가스(NG)", "NG=F", "$", True, "LNG 수요"),
        SectorMacroItem("WTI 원유", "CL=F", "$", True, "유조선 수익성"),
        SectorMacroItem("달러/원(KRW)", "KRW=X", "원/$", False, "수주 달러 환차익"),
    ],
    # 방산 / 우주 / 드론
    "defense_space_aerospace_drone": [
        SectorMacroItem("ITA (방산ETF)", "ITA", "%", True),
        SectorMacroItem("VIX (공포지수)", "^VIX", "pt", True, "지정학 리스크 ↑ → 방산 수혜"),
        SectorMacroItem("10Y 국채금리", "^TNX", "pt", None),
        SectorMacroItem("달러인덱스(DXY)", "DX-Y.NYB", "pt", True, "방산 수출 달러 강세 유리"),
    ],
    # 자동차 / EV / 자율주행 / 로보택시
    "auto_ev_autonomous_robotaxi": [
        SectorMacroItem("TSLA", "TSLA", "%", True),
        SectorMacroItem("구리선물(HG)", "HG=F", "$", None, "EV 전선 소재"),
        SectorMacroItem("리튬선물(LIT)", "LIT", "%", True, "배터리 원가 대리지표"),
        SectorMacroItem("WTI 원유", "CL=F", "$", None, "내연기관 경쟁 vs EV 전환"),
    ],
    # 배터리 / 소재 / 리튬 / 리사이클
    "battery_materials_lithium_recycling": [
        SectorMacroItem("LIT (리튬ETF)", "LIT", "%", True),
        SectorMacroItem("구리선물(HG)", "HG=F", "$", True),
        SectorMacroItem("니켈선물(NI)", "NI=F", "$", True),
        SectorMacroItem("달러인덱스(DXY)", "DX-Y.NYB", "pt", False),
    ],
    # 금융 / 은행 / 보험 / 증권
    "financials_banks_insurance_brokers": [
        SectorMacroItem("10Y 국채금리", "^TNX", "pt", True, "NIM(순이자마진) 확대"),
        SectorMacroItem("2Y 국채금리", "^IRX", "pt", None, "단기 조달비용"),
        SectorMacroItem("VIX (공포지수)", "^VIX", "pt", False, "신용리스크 프리미엄"),
        SectorMacroItem("KRW/USD (달러/원)", "KRW=X", "원/$", None),
    ],
    # 에너지 / 원유 / LNG / 재생에너지
    "energy_oil_lng_renewables": [
        SectorMacroItem("WTI 원유", "CL=F", "$", True),
        SectorMacroItem("천연가스(NG)", "NG=F", "$", True),
        SectorMacroItem("달러인덱스(DXY)", "DX-Y.NYB", "pt", False, "원자재 역상관"),
        SectorMacroItem("XLE (에너지ETF)", "XLE", "%", True),
    ],
    # 소재 / 화학 / 철강 / 희토류
    "materials_chem_steel_metals_rareearth": [
        SectorMacroItem("구리선물(HG)", "HG=F", "$", True),
        SectorMacroItem("철강 ETF(SLX)", "SLX", "%", True),
        SectorMacroItem("달러인덱스(DXY)", "DX-Y.NYB", "pt", False),
        SectorMacroItem("중국 CSI300", "000300.SS", "pt", True, "철강·화학 수요"),
    ],
    # 건설 / 인프라 / 리츠 / 시멘트
    "construction_infra_reits_cement": [
        SectorMacroItem("10Y 국채금리", "^TNX", "pt", False, "리츠 할인율·모기지 직결"),
        SectorMacroItem("IYR (부동산ETF)", "IYR", "%", True),
        SectorMacroItem("구리선물(HG)", "HG=F", "$", None),
        SectorMacroItem("VIX (공포지수)", "^VIX", "pt", False),
    ],
    # K-뷰티 / 코스메틱 / ODM / 소비재
    "kbeauty_cosmetics_odm_consumer": [
        SectorMacroItem("XLY (소비재ETF)", "XLY", "%", True),
        SectorMacroItem("미국 CPI (XLP proxy)", "XLP", "%", True, "소비 안정성 대리지표"),
        SectorMacroItem("달러/원(KRW)", "KRW=X", "원/$", True, "수출 환차익"),
        SectorMacroItem("중국 CSI300", "000300.SS", "pt", True, "중국 소비 수요"),
    ],
    # 유통 / 이커머스 / 물류 / 여행 / 항공 / 카지노
    "retail_ecommerce_logistics_travel_airline_casino": [
        SectorMacroItem("XLY (소비재ETF)", "XLY", "%", True),
        SectorMacroItem("WTI 원유", "CL=F", "$", False, "항공·물류 원가"),
        SectorMacroItem("10Y 국채금리", "^TNX", "pt", False),
        SectorMacroItem("달러인덱스(DXY)", "DX-Y.NYB", "pt", None),
    ],
    # 미디어 / 콘텐츠 / 게임 / 광고
    "media_content_gaming_entertainment_ads": [
        SectorMacroItem("QQQ (나스닥100)", "QQQ", "%", True),
        SectorMacroItem("XLY (소비재ETF)", "XLY", "%", True),
        SectorMacroItem("달러인덱스(DXY)", "DX-Y.NYB", "pt", False, "글로벌 광고 환위험"),
        SectorMacroItem("VIX (공포지수)", "^VIX", "pt", False),
    ],
    # 통신 / 네트워크 / 스마트폰 / 장비
    "telecom_network_smartphone_equipment": [
        SectorMacroItem("10Y 국채금리", "^TNX", "pt", False, "설비투자 부채비용"),
        SectorMacroItem("달러인덱스(DXY)", "DX-Y.NYB", "pt", False),
        SectorMacroItem("구리선물(HG)", "HG=F", "$", None, "통신장비 소재"),
        SectorMacroItem("XLK (기술ETF)", "XLK", "%", True),
    ],
    # 식품 / 농업 / 비료 / 필수소비재
    "food_agriculture_fertilizer_staples": [
        SectorMacroItem("XLP (필수소비재ETF)", "XLP", "%", True),
        SectorMacroItem("밀선물(ZW)", "ZW=F", "$", None, "식품 원가"),
        SectorMacroItem("천연가스(NG)", "NG=F", "$", False, "비료(암모니아) 원가"),
        SectorMacroItem("달러인덱스(DXY)", "DX-Y.NYB", "pt", False, "수입 곡물 가격"),
    ],
    # 산업재 / 기계 / 자동화 / 로보틱스
    "industrials_machinery_automation_robotics": [
        SectorMacroItem("XLI (산업재ETF)", "XLI", "%", True),
        SectorMacroItem("구리선물(HG)", "HG=F", "$", True),
        SectorMacroItem("WTI 원유", "CL=F", "$", None),
        SectorMacroItem("달러인덱스(DXY)", "DX-Y.NYB", "pt", False, "수출 경쟁력"),
    ],
    # 페이먼트 / 크립토 / 거래소 / 증권사
    "payments_crypto_exchange_brokerage": [
        SectorMacroItem("BTC-USD", "BTC-USD", "$", True),
        SectorMacroItem("VIX (공포지수)", "^VIX", "pt", False),
        SectorMacroItem("10Y 국채금리", "^TNX", "pt", False, "성장주 할인율"),
        SectorMacroItem("달러인덱스(DXY)", "DX-Y.NYB", "pt", None),
    ],
    # 의료서비스 / 병원 / 진단
    "healthcare_services_hospitals_diagnostics": [
        SectorMacroItem("XLV (헬스케어ETF)", "XLV", "%", True),
        SectorMacroItem("10Y 국채금리", "^TNX", "pt", False),
        SectorMacroItem("달러인덱스(DXY)", "DX-Y.NYB", "pt", False),
        SectorMacroItem("VIX (공포지수)", "^VIX", "pt", False),
    ],
    # 환경 / 폐기물 / 수처리 / 탄소 인프라
    "environment_waste_water_carbon_infra": [
        SectorMacroItem("XLU (유틸리티ETF)", "XLU", "%", True),
        SectorMacroItem("10Y 국채금리", "^TNX", "pt", False, "인프라 부채비용"),
        SectorMacroItem("탄소배출권(KRBN)", "KRBN", "$", True),
        SectorMacroItem("달러인덱스(DXY)", "DX-Y.NYB", "pt", False),
    ],
    # 매크로 민감주 / 금리 / 환율 / 원자재
    "macro_sensitive_rates_fx_commodities": [
        SectorMacroItem("10Y 국채금리", "^TNX", "pt", None),
        SectorMacroItem("달러인덱스(DXY)", "DX-Y.NYB", "pt", None),
        SectorMacroItem("금(GLD)", "GLD", "$", True, "위험회피 지표"),
        SectorMacroItem("VIX (공포지수)", "^VIX", "pt", False),
    ],
    # ai_semiconductor_hbm_foundry alias (missing sector)
    "ai_semiconductor_hbm": [
        SectorMacroItem("SOXX (반도체ETF)", "SOXX", "%", True),
        SectorMacroItem("NVDA", "NVDA", "%", True),
        SectorMacroItem("10Y 국채금리", "^TNX", "pt", False),
        SectorMacroItem("달러인덱스(DXY)", "DX-Y.NYB", "pt", None),
    ],
}


# ── DB 기반 섹터 탐지 ─────────────────────────────────────────────────────────


def detect_seed_sector(symbol: str, store: Store) -> str | None:
    """relation_edges DB에서 symbol이 속하는 섹터 ID를 탐지한다.

    rule_id 형식: 'seed:<sector_id>' — 가장 많이 등장하는 섹터를 반환.
    """
    try:
        edges = store.get_all_relation_edges(active_only=False)
        counts: dict[str, int] = {}
        for edge in edges:
            rule_id = str(edge.get("rule_id") or "")
            if not rule_id.startswith("seed:"):
                continue
            src = str(edge.get("source_symbol") or "")
            tgt = str(edge.get("target_symbol") or "")
            if symbol not in (src, tgt):
                continue
            sector_id = rule_id[5:]  # 'seed:' 제거
            counts[sector_id] = counts.get(sector_id, 0) + 1
        if not counts:
            return None
        return max(counts, key=lambda k: counts[k])
    except Exception as exc:
        log.debug("[sector_macro] detect_seed_sector failed for %s: %s", symbol, exc)
        return None


# yfinance가 잘못 분류하는 KR 종목 심볼 → sector_id 오버라이드
# (특히 조선주가 "Aerospace & Defense"로 오분류되는 케이스)
_SYMBOL_SECTOR_OVERRIDES: dict[str, str] = {
    # 조선 / 해운 / LNG
    "329180.KS": "shipbuilding_shipping_lng_equipment",  # HD현대중공업
    "010140.KS": "shipbuilding_shipping_lng_equipment",  # 삼성중공업
    "009540.KS": "shipbuilding_shipping_lng_equipment",  # HD현대마린솔루션
    "267250.KS": "shipbuilding_shipping_lng_equipment",  # HD현대
    "006360.KS": "shipbuilding_shipping_lng_equipment",  # GS건설 (해양플랜트)
    "000150.KS": "shipbuilding_shipping_lng_equipment",  # 두산에너빌리티
    "011200.KS": "shipbuilding_shipping_lng_equipment",  # HMM
    "028670.KS": "shipbuilding_shipping_lng_equipment",  # 팬오션
    # 방산 (정확하게 분류된 경우 그대로)
    "012450.KS": "defense_space_aerospace_drone",        # 한화에어로스페이스
    "079550.KS": "defense_space_aerospace_drone",        # LIG넥스원
    "064350.KS": "defense_space_aerospace_drone",        # 현대로템
    "047810.KS": "defense_space_aerospace_drone",        # 한국항공우주
}


def symbol_sector_override(symbol: str) -> str | None:
    """yfinance 오분류 보정용 심볼 → sector_id 직접 오버라이드.

    우선순위: ticker_sector_overrides.yml → _SYMBOL_SECTOR_OVERRIDES(하드코딩)
    """
    try:
        from tele_quant.ticker_universe import _load_overrides
        yaml_val = _load_overrides().get(symbol)
        if yaml_val:
            return yaml_val
    except Exception:
        pass
    return _SYMBOL_SECTOR_OVERRIDES.get(symbol)


def guess_sector_id(sector_str: str) -> str | None:
    """yfinance sector 문자열에서 가장 가까운 sector_id를 추정한다 (fallback)."""
    s = (sector_str or "").lower()
    if not s:
        return None
    mapping = [
        # 세밀한 industry 키워드 먼저 (broad sector 키워드보다 우선)
        ("semiconductor", "ai_semiconductor_hbm_foundry"),
        ("biotechnology", "biotech_pharma_clinical_medtech"),
        ("pharmaceutical", "biotech_pharma_clinical_medtech"),
        ("drug manufacturer", "biotech_pharma_clinical_medtech"),
        ("biopharmaceutical", "biotech_pharma_clinical_medtech"),
        ("cdmo", "cdmo_bioproduction_adc"),
        ("contract research", "cdmo_bioproduction_adc"),
        ("medical device", "biotech_pharma_clinical_medtech"),
        ("diagnostics", "healthcare_services_hospitals_diagnostics"),
        ("hospital", "healthcare_services_hospitals_diagnostics"),
        ("healthcare", "healthcare_services_hospitals_diagnostics"),  # broad — 바이오 다음에
        ("software", "ai_software_cloud_cybersecurity"),
        ("internet", "ai_software_cloud_cybersecurity"),
        ("cloud", "ai_software_cloud_cybersecurity"),
        ("technology", "ai_software_cloud_cybersecurity"),           # broad — software 다음에
        ("financial", "financials_banks_insurance_brokers"),
        ("bank", "financials_banks_insurance_brokers"),
        ("insurance", "financials_banks_insurance_brokers"),
        ("energy", "energy_oil_lng_renewables"),
        ("oil", "energy_oil_lng_renewables"),
        ("lng", "shipbuilding_shipping_lng_equipment"),
        ("shipping", "shipbuilding_shipping_lng_equipment"),
        ("marine", "shipbuilding_shipping_lng_equipment"),
        ("material", "materials_chem_steel_metals_rareearth"),
        ("chemical", "materials_chem_steel_metals_rareearth"),
        ("steel", "materials_chem_steel_metals_rareearth"),
        ("defense", "defense_space_aerospace_drone"),
        ("aerospace", "defense_space_aerospace_drone"),
        ("auto", "auto_ev_autonomous_robotaxi"),
        ("electric vehicle", "auto_ev_autonomous_robotaxi"),
        ("battery", "battery_materials_lithium_recycling"),
        ("lithium", "battery_materials_lithium_recycling"),
        ("real estate", "construction_infra_reits_cement"),
        ("construction", "construction_infra_reits_cement"),
        ("consumer discretionary", "retail_ecommerce_logistics_travel_airline_casino"),
        ("consumer cyclical", "retail_ecommerce_logistics_travel_airline_casino"),
        ("consumer defensive", "food_agriculture_fertilizer_staples"),
        ("consumer staple", "food_agriculture_fertilizer_staples"),
        ("communication", "media_content_gaming_entertainment_ads"),
        ("entertainment", "media_content_gaming_entertainment_ads"),
        ("gaming", "media_content_gaming_entertainment_ads"),
        ("utilities", "environment_waste_water_carbon_infra"),
        ("industrial", "industrials_machinery_automation_robotics"),  # broad — 마지막
    ]
    for keyword, sector_id in mapping:
        if keyword in s:
            return sector_id
    return None


# ── yfinance 데이터 조회 ───────────────────────────────────────────────────────


def _fetch_1w_change(ticker: str) -> tuple[float | None, float | None]:
    """yfinance로 1주 가격 변화 (현재값, 변화율%) 반환. 실패 시 (None, None)."""
    try:
        import yfinance as yf

        hist = yf.Ticker(ticker).history(period="10d", auto_adjust=True)
        if hist is None or hist.empty:
            return None, None
        closes = hist["Close"].dropna()
        if len(closes) < 2:
            return None, None
        last = float(closes.iloc[-1])
        # 5 거래일 전(1주) 기준
        lookback = min(5, len(closes) - 1)
        prev = float(closes.iloc[-(lookback + 1)])
        if prev == 0:
            return last, None
        change_pct = (last - prev) / prev * 100
        return last, change_pct
    except Exception as exc:
        log.debug("[sector_macro] _fetch_1w_change(%s) failed: %s", ticker, exc)
        return None, None


def fetch_sector_macro_snapshot(sector_id: str) -> list[SectorMacroSnapshot]:
    """섹터 ID에 해당하는 모든 지표의 현재값과 1주 변화율을 조회한다."""
    items = SECTOR_MACRO_MAP.get(sector_id, [])
    results: list[SectorMacroSnapshot] = []
    for item in items:
        current, change_pct = _fetch_1w_change(item.ticker)
        signal = _compute_signal(change_pct, item.up_is_positive)
        snap = SectorMacroSnapshot(
            item=item,
            current=current,
            change_1w_pct=change_pct,
            signal=signal,
        )
        results.append(snap)
    return results


def _compute_signal(change_pct: float | None, up_is_positive: bool | None) -> str:
    """1주 변화율과 방향성 기반 호재/주의 신호 문자열 반환."""
    if change_pct is None or up_is_positive is None:
        return "—"
    if up_is_positive:
        if change_pct >= 2.0:
            return "✅ 호재"
        if change_pct <= -2.0:
            return "⚠ 주의"
    else:
        if change_pct <= -2.0:
            return "✅ 호재"
        if change_pct >= 2.0:
            return "⚠ 주의"
    return "—"


# ── 포맷터 ────────────────────────────────────────────────────────────────────


def format_sector_macro(sector_id: str, snapshots: list[SectorMacroSnapshot] | None = None) -> str:
    """Telegram 출력용 섹터 매크로 섹션 문자열 반환.

    snapshots가 None이면 내부에서 fetch_sector_macro_snapshot()을 호출한다.
    """
    if sector_id not in SECTOR_MACRO_MAP:
        return ""
    if snapshots is None:
        snapshots = fetch_sector_macro_snapshot(sector_id)
    if not snapshots:
        return ""

    lines = ["🌐 섹터 매크로 지표 (1주 변화):"]
    for s in snapshots:
        label = s.item.label
        unit = s.item.unit
        current_str = _fmt_value(s.current, unit)
        change_str = f"{s.change_1w_pct:+.1f}%" if s.change_1w_pct is not None else "—"
        sig = s.signal if s.signal != "—" else ""
        note = f"  ({s.item.note})" if s.item.note else ""
        sig_suffix = f" {sig}" if sig else ""
        lines.append(f"  • {label}: {current_str} ({change_str}){sig_suffix}{note}")

    return "\n".join(lines)


def _fmt_value(value: float | None, unit: str) -> str:
    if value is None:
        return "—"
    if unit in ("%", "pt"):
        return f"{value:.2f}{unit}"
    if unit == "$":
        return f"${value:,.2f}"
    if unit == "원/$":
        return f"{value:,.0f}원"
    return f"{value:.2f}"
