"""Sector-Specific Analysis — 섹터별 특화 가치분석.

valuation_playbooks.yml + sector_playbooks.yml 실제 반영.
24개 sector_id 전체 매핑.
공개 정보 기반 리서치 보조. 투자 판단 책임은 사용자에게 있음.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from tele_quant.analysis.report_models import SectorSpecificAnalysis

log = logging.getLogger(__name__)

_CONF_DIR = Path(__file__).parent.parent.parent.parent / "config"
_VAL_PATH = _CONF_DIR / "valuation_playbooks.yml"
_PLAY_PATH = _CONF_DIR / "sector_playbooks.yml"


def _load_yaml(path: Path) -> dict:
    try:
        import yaml  # type: ignore[import-untyped]

        with path.open(encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception as exc:
        log.warning("[sector_spec] yaml load failed %s: %s", path.name, exc)
        return {}


_VAL_PB: dict | None = None
_PLAY_PB: dict | None = None


def _val_playbook() -> dict:
    global _VAL_PB
    if _VAL_PB is None:
        _VAL_PB = _load_yaml(_VAL_PATH)
    return _VAL_PB


def _sector_playbook() -> dict:
    global _PLAY_PB
    if _PLAY_PB is None:
        _PLAY_PB = _load_yaml(_PLAY_PATH)
    return _PLAY_PB


# ── sector_id → valuation_key 매핑 ──────────────────────────────────────────

_SECTOR_TO_VAL: dict[str, str] = {
    # 24개 sector_id → valuation_playbooks.yml 키
    "ai_semiconductor_hbm_foundry": "ai_semiconductor_hbm_foundry",
    "semicap_equipment_materials_osat": "semiconductor_equipment_materials",
    "ai_software_cloud_cybersecurity": "saas_software_cloud",
    "ai_power_grid_copper_nuclear": "industrials_robots",
    "biotech_pharma_clinical_medtech": "bio_pharma_clinical",
    "cdmo_bioproduction_adc": "cdmo_bio_manufacturing",
    "shipbuilding_shipping_lng_equipment": "shipbuilding_lng",
    "defense_space_aerospace_drone": "defense_aerospace",
    "auto_ev_autonomous_robotaxi": "auto_ev_robotaxi",
    "battery_materials_lithium_recycling": "battery_materials_lithium",
    "financials_banks_insurance_brokers": "financial_banking",
    "energy_oil_lng_renewables": "energy_oil_lng_renewable",
    "materials_chemicals_steel": "materials_chemicals_steel",
    "construction_infra_reits_cement": "construction_reit",
    "kbeauty_cosmetics_odm_consumer": "kbeauty_consumer",
    "retail_ecommerce_logistics_travel_airline_casino": "retail_travel_casino",
    "media_content_gaming_entertainment_ads": "media_content_entertainment",
    "telecom_network_smartphone_equipment": "telecom_network_optical",
    "food_agriculture_fertilizer_staples": "food_agriculture",
    "industrials_machinery_automation_robotics": "industrials_robots",
    "payments_crypto_exchange_brokerage": "financial_banking",
    "healthcare_services_hospitals_diagnostics": "bio_pharma_clinical",
    "environment_waste_water_carbon_infra": "construction_reit",
    "macro_sensitive_rates_fx_commodities": "energy_oil_lng_renewable",
}

# sector_id → label 한국어
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


# ── yfinance에서 PER 추출 ─────────────────────────────────────────────────────


def _get_pe(symbol: str) -> float | None:
    try:
        from tele_quant.stock_data_provider import get_ticker_info

        info = get_ticker_info(symbol) or {}
        return info.get("trailingPE") or info.get("forwardPE")
    except Exception:
        return None


def _get_pbr(symbol: str) -> float | None:
    try:
        from tele_quant.stock_data_provider import get_ticker_info

        info = get_ticker_info(symbol) or {}
        return info.get("priceToBook")
    except Exception:
        return None


# ── PER 코멘트 ─────────────────────────────────────────────────────────────


def _pe_comment(pe: float | None, normal_range: list | None, pe_note: str) -> str:
    if pe is None:
        return "PER 확인 제한"
    if normal_range and len(normal_range) == 2:
        lo, hi = normal_range
        if lo <= pe <= hi:
            return f"PER {pe:.1f}배 — 섹터 정상 범위({lo}~{hi}배) 내"
        elif pe < lo:
            return f"PER {pe:.1f}배 — 섹터 기준({lo}배) 하회 (저평가 또는 이익 급증)"
        else:
            return f"PER {pe:.1f}배 — 섹터 기준({hi}배) 상회 (성장 프리미엄 또는 이익 감소)"
    return f"PER {pe:.1f}배 ({pe_note or '참고'})"


# ── peer 비교 (간단) ─────────────────────────────────────────────────────────


def _peer_lines(sector_id: str, play_pb: dict) -> list[str]:
    """sector_playbook의 key_metrics와 catalysts를 peer 비교로 활용."""
    pb = play_pb.get(sector_id, {})
    peers: list[str] = []
    for q in pb.get("key_questions", [])[:2]:
        peers.append(f"• 확인 포인트: {q}")
    for m in pb.get("key_metrics", [])[:2]:
        peers.append(f"• 핵심 지표: {m} (확인 제한 — 직접 조회 권장)")
    return peers


# ── 메인 ────────────────────────────────────────────────────────────────────


def build_sector_specific_analysis(
    symbol: str,
    sector_id: str,
) -> SectorSpecificAnalysis:  # type: ignore[name-defined]
    """섹터별 특화 가치분석 빌드."""
    from tele_quant.analysis.report_models import SectorSpecificAnalysis

    val_pb = _val_playbook()
    play_pb = _sector_playbook()

    sa = SectorSpecificAnalysis()
    sa.sector_id = sector_id
    sa.sector_label = _SECTOR_LABELS.get(sector_id, sector_id)

    val_key = _SECTOR_TO_VAL.get(sector_id, "")
    val_data = val_pb.get(val_key, {})

    # primary metrics
    for m in val_data.get("primary_metrics", []):
        sa.primary_metrics.append({"name": str(m), "value": "확인 제한", "signal": "중립"})

    # secondary metrics
    for m in val_data.get("secondary_metrics", [])[:3]:
        sa.secondary_metrics.append({"name": str(m), "value": "확인 제한", "signal": "중립"})

    # PER
    sa.pe_note = val_data.get("pe_note", "")
    nr = val_data.get("normal_pe_range")
    if nr and len(nr) == 2:
        sa.normal_pe_range = (float(nr[0]), float(nr[1]))
    sa.current_pe = _get_pe(symbol)
    sa.pe_comment = _pe_comment(sa.current_pe, nr, sa.pe_note)

    # PBR (금융 섹터)
    if "financial" in val_key or sector_id in ("financials_banks_insurance_brokers", "payments_crypto_exchange_brokerage"):
        pbr = _get_pbr(symbol)
        if pbr is not None:
            nr_pbr = val_data.get("normal_pbr_range")
            if nr_pbr and len(nr_pbr) == 2:
                lo, hi = nr_pbr
                signal = "저평가" if pbr < lo else ("적정" if pbr <= hi else "고평가")
                sa.secondary_metrics.insert(
                    0, {"name": "PBR", "value": f"{pbr:.2f}배", "signal": signal}
                )

    # peer comparison
    sa.peer_comparison = _peer_lines(sector_id, play_pb)

    # 섹터 valuation score (playbook 기반 단순 추정)
    score = 50.0
    # PE 범위 내면 +10
    if sa.current_pe is not None and sa.normal_pe_range:
        lo, hi = sa.normal_pe_range
        if lo <= sa.current_pe <= hi:
            score += 10
        elif sa.current_pe < lo:
            score += 15  # 저평가 가능성
        else:
            score -= 5   # 고평가 가능성
    sa.sector_valuation_score = min(max(score, 0), 100)

    # key watchpoints
    pb_play = play_pb.get(sector_id, {})
    sa.key_watchpoints = pb_play.get("swing_checkpoints", [])[:3]

    return sa


def detect_sector_id(symbol: str, store: Any = None) -> str:
    """sector_id 탐지. override → DB universe → yfinance GICS → detect_seed_sector 순."""
    try:
        from tele_quant.ticker_universe import get_sector_id
        return get_sector_id(symbol, store)
    except Exception as exc:
        log.debug("[sector_spec] detect failed %s: %s", symbol, exc)
        # 최종 fallback
        try:
            from tele_quant.sector_macro import detect_seed_sector
            return detect_seed_sector(symbol, store) or ""
        except Exception:
            return ""
