"""Sector Analysis Engine — valuation_playbooks.yml / technical_playbooks.yml 실제 반영.

sector_intelligence.py 와 stock_snapshot.py 에서 호출한다.
공개 정보 기반 리서치 보조. 투자 판단 책임은 사용자에게 있음.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from tele_quant.sector_intelligence import SectorIntelligence

log = logging.getLogger(__name__)

_CFG = Path(__file__).parent.parent.parent / "config"

__all__ = [
    "enrich_sector_intelligence",
    "format_valuation_hint",
    "get_primary_metrics",
    "get_valuation_context",
    "score_rsi_from_playbook",
]


# ── YAML 로더 ─────────────────────────────────────────────────────────────────


@lru_cache(maxsize=1)
def _load_valuation_playbooks() -> dict[str, Any]:
    try:
        import yaml

        p = _CFG / "valuation_playbooks.yml"
        return yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        log.debug("[sector_engine] valuation_playbooks 로드 실패: %s", exc)
        return {}


@lru_cache(maxsize=1)
def _load_tech_playbooks() -> dict[str, Any]:
    try:
        import yaml

        p = _CFG / "technical_playbooks.yml"
        return yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        log.debug("[sector_engine] technical_playbooks 로드 실패: %s", exc)
        return {}


# ── sector_macro sector_id → valuation_playbooks.yml key ─────────────────────

_VALUATION_KEY_MAP: dict[str, str] = {
    "ai_semiconductor_hbm_foundry":               "ai_semiconductor_hbm_foundry",
    "ai_semiconductor_hbm":                       "ai_semiconductor_hbm_foundry",
    "semicap_equipment_materials_osat":            "semiconductor_equipment_materials",
    "ai_software_cloud_cybersecurity":             "saas_software_cloud",
    "ai_power_grid_copper_nuclear":                "industrials_robots",
    "biotech_pharma_clinical_medtech":             "bio_pharma_clinical",
    "cdmo_bioproduction_adc":                      "cdmo_bio_manufacturing",
    "shipbuilding_shipping_lng_equipment":         "shipbuilding_lng",
    "defense_space_aerospace_drone":               "defense_aerospace",
    "auto_ev_autonomous_robotaxi":                 "auto_ev_robotaxi",
    "auto_ev_battery_robotaxi":                    "auto_ev_robotaxi",    # legacy alias
    "battery_materials_lithium_recycling":         "battery_materials_lithium",
    "financials_banks_insurance_brokers":          "financial_banking",
    "financial_banking_insurance":                 "financial_banking",   # legacy alias
    "energy_oil_lng_renewables":                   "energy_oil_lng_renewable",
    "materials_chem_steel_metals_rareearth":       "materials_chemicals_steel",
    "construction_infra_reits_cement":             "construction_reit",
    "kbeauty_cosmetics_odm_consumer":              "kbeauty_consumer",
    "retail_ecommerce_logistics_travel_airline_casino": "retail_travel_casino",
    "media_content_gaming_entertainment_ads":      "media_content_entertainment",
    "telecom_network_smartphone_equipment":        "telecom_network_optical",
    "food_agriculture_fertilizer_staples":         "food_agriculture",
    "industrials_machinery_automation_robotics":   "industrials_robots",
}


# ── Public API ────────────────────────────────────────────────────────────────


def get_valuation_context(sector_id: str) -> dict[str, Any]:
    """sector_id에 맞는 valuation playbook dict 반환. 없으면 {}."""
    playbooks = _load_valuation_playbooks()
    key = _VALUATION_KEY_MAP.get(sector_id, sector_id)
    return playbooks.get(key) or {}


def get_primary_metrics(sector_id: str) -> list[str]:
    """primary_metrics 목록 (최대 4개)."""
    ctx = get_valuation_context(sector_id)
    return list(ctx.get("primary_metrics") or [])[:4]


def format_valuation_hint(sector_id: str) -> str:
    """pe_note + primary_metrics + key_watchpoints → 출력 텍스트.

    sector_intelligence 없을 때 fallback으로 사용 가능.
    """
    ctx = get_valuation_context(sector_id)
    if not ctx:
        return ""
    lines: list[str] = []
    pe_note = ctx.get("pe_note")
    if pe_note:
        lines.append(f"  💡 가치: {pe_note}")
    primary = ctx.get("primary_metrics") or []
    if primary:
        lines.append("  핵심 관찰:")
        for m in list(primary)[:3]:
            lines.append(f"    • {m}")
    watchpoints = ctx.get("key_watchpoints") or []
    for w in list(watchpoints)[:2]:
        lines.append(f"  📌 {w}")
    return "\n".join(lines)


def score_rsi_from_playbook(rsi_val: float, side: str = "long") -> tuple[float, str]:
    """technical_playbooks.yml RSI 규칙 → (score_delta, label).

    Returns (0.0, "") if playbook unavailable or no rule matches.
    """
    tech = _load_tech_playbooks()
    rsi_rules = ((tech.get("rsi") or {}).get("score_rules") or {})
    rules: list[dict] = rsi_rules.get(side.lower()) or []
    for rule in rules:
        if "range" in rule:
            lo, hi = rule["range"]
            if lo <= rsi_val <= hi:
                return float(rule.get("score", 0)), str(rule.get("label", ""))
        elif "threshold_above" in rule:
            if rsi_val > rule["threshold_above"]:
                return float(rule.get("score", 0)), str(rule.get("label", ""))
        elif "threshold_below" in rule:
            if rsi_val < rule["threshold_below"]:
                return float(rule.get("score", 0)), str(rule.get("label", ""))
    return 0.0, ""


def enrich_sector_intelligence(intel: SectorIntelligence, sector_id: str) -> None:
    """SectorIntelligence 객체를 valuation_playbooks 데이터로 보강 (in-place).

    - valuation_note 가 비어있으면 pe_note 로 채움
    - key_metrics 가 부족하면 primary_metrics 로 보완
    """
    ctx = get_valuation_context(sector_id)
    if not ctx:
        return
    if not intel.valuation_note:
        pe_note = ctx.get("pe_note")
        if pe_note:
            intel.valuation_note = pe_note
    primary = list(ctx.get("primary_metrics") or [])[:4]
    if not intel.key_metrics and primary:
        intel.key_metrics = primary
    elif primary and len(intel.key_metrics) < 2:
        merged = list(dict.fromkeys(intel.key_metrics + primary))[:4]
        intel.key_metrics = merged
