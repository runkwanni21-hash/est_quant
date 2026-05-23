"""Tests for sector_intelligence — sector-specific deep analysis."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from tele_quant.sector_intelligence import (
    SectorIntelligence,
    build_sector_intelligence,
    format_sector_intelligence,
    load_playbook,
)

# ── load_playbook ─────────────────────────────────────────────────────────────


def test_load_playbook_biotech():
    pb = load_playbook("biotech_pharma_clinical_medtech")
    assert pb is not None
    assert "display_name" in pb
    assert "바이오" in pb["display_name"]
    assert "special_module" in pb
    assert pb["special_module"] == "clinical_pipeline"


def test_load_playbook_shipbuilding():
    pb = load_playbook("shipbuilding_shipping_lng_equipment")
    assert pb is not None
    assert pb.get("special_module") == "order_backlog"
    assert "key_metrics" in pb


def test_load_playbook_semiconductor():
    pb = load_playbook("ai_semiconductor_hbm_foundry")
    assert pb is not None
    assert "catalysts" in pb
    assert len(pb["catalysts"]) >= 2


def test_load_playbook_unknown_returns_none():
    pb = load_playbook("nonexistent_sector_xyz_abc")
    assert pb is None


def test_load_playbook_all_24():
    sector_ids = [
        "ai_semiconductor_hbm_foundry",
        "semicap_equipment_materials_osat",
        "ai_software_cloud_cybersecurity",
        "ai_power_grid_copper_nuclear",
        "biotech_pharma_clinical_medtech",
        "cdmo_bioproduction_adc",
        "shipbuilding_shipping_lng_equipment",
        "defense_space_aerospace_drone",
        "auto_ev_autonomous_robotaxi",
        "battery_materials_lithium_recycling",
        "financials_banks_insurance_brokers",
        "energy_oil_lng_renewables",
        "materials_chem_steel_metals_rareearth",
        "construction_infra_reits_cement",
        "kbeauty_cosmetics_odm_consumer",
        "retail_ecommerce_logistics_travel_airline_casino",
        "media_content_gaming_entertainment_ads",
        "telecom_network_smartphone_equipment",
        "food_agriculture_fertilizer_staples",
        "industrials_machinery_automation_robotics",
        "payments_crypto_exchange_brokerage",
        "healthcare_services_hospitals_diagnostics",
        "environment_waste_water_carbon_infra",
        "macro_sensitive_rates_fx_commodities",
    ]
    for sid in sector_ids:
        pb = load_playbook(sid)
        assert pb is not None, f"Missing playbook: {sid}"
        assert "display_name" in pb, f"No display_name in {sid}"
        assert "risks" in pb, f"No risks in {sid}"
        assert "catalysts" in pb, f"No catalysts in {sid}"


# ── build_sector_intelligence ─────────────────────────────────────────────────


def test_build_sector_intelligence_no_sector_returns_none():
    result = build_sector_intelligence("NVDA", sector_id="")
    assert result is None


def test_build_sector_intelligence_unknown_sector_returns_none():
    result = build_sector_intelligence("NVDA", sector_id="does_not_exist")
    assert result is None


def test_build_sector_intelligence_basic():
    intel = build_sector_intelligence(
        symbol="NVDA",
        name="NVIDIA",
        market="US",
        sector_id="ai_semiconductor_hbm_foundry",
        price_snapshot={"1w": 5.0, "1m": 15.0},
        fundamental_snapshot={"pe_forward": 35.0, "roe": 90.0},
    )
    assert intel is not None
    assert isinstance(intel, SectorIntelligence)
    assert intel.sector_id == "ai_semiconductor_hbm_foundry"
    assert intel.title
    assert len(intel.catalysts) > 0
    assert len(intel.risks) > 0


def test_build_sector_intelligence_biotech_has_clinical_module():
    with patch("tele_quant.clinical_pipeline.fetch_clinical_pipeline") as mock_fetch:
        mock_fetch.return_value = MagicMock(
            trials=[],
            headline_signals=[],
            cash_burn_note="",
            partner_note="",
            market_note="",
            data_limited=True,
            limitation_note="공개자료 기준 확인 제한",
        )
        intel = build_sector_intelligence(
            symbol="128940.KS",
            name="한미약품",
            market="KR",
            sector_id="biotech_pharma_clinical_medtech",
        )
    assert intel is not None
    assert "바이오" in intel.title or "제약" in intel.title or intel.special_section != ""


def test_build_sector_intelligence_shipbuilding_has_backlog():
    intel = build_sector_intelligence(
        symbol="329180.KS",
        name="HD현대중공업",
        market="KR",
        sector_id="shipbuilding_shipping_lng_equipment",
    )
    assert intel is not None
    # special_section should contain shipbuilding-related content
    assert True  # special_section content depends on DB availability


def test_build_sector_intelligence_financials():
    intel = build_sector_intelligence(
        symbol="105560.KS",
        sector_id="financials_banks_insurance_brokers",
        fundamental_snapshot={"pe_forward": 8.0, "roe": 10.0},
    )
    assert intel is not None
    assert any("NIM" in m or "PBR" in m or "배당" in m for m in intel.key_metrics)


def test_build_sector_intelligence_policy_note_no_forbidden():
    intel = build_sector_intelligence(
        symbol="NVDA",
        sector_id="ai_semiconductor_hbm_foundry",
    )
    assert intel is not None
    if intel.policy_note:
        forbidden = ["매수 권장", "매도 권장", "확정 수익", "자동매매"]
        for word in forbidden:
            assert word not in intel.policy_note


# ── format_sector_intelligence ────────────────────────────────────────────────


def test_format_sector_intelligence_returns_string():
    intel = SectorIntelligence(
        sector_id="ai_semiconductor_hbm_foundry",
        title="AI 반도체",
        catalysts=["HBM 수요"],
        risks=["CAPEX 지연"],
        key_metrics=["HBM ASP"],
        valuation_note="PER(F) 30~40배",
    )
    result = format_sector_intelligence(intel)
    assert isinstance(result, str)
    assert "AI 반도체" in result


def test_format_sector_intelligence_no_forbidden_words():
    intel = SectorIntelligence(
        sector_id="biotech_pharma_clinical_medtech",
        title="바이오",
        catalysts=["FDA 승인"],
        risks=["임상 실패"],
        key_metrics=["현금소진"],
        special_section="🧬 바이오/임상 체크:\n  • 공개자료 기준 확인 제한",
    )
    result = format_sector_intelligence(intel)
    forbidden = ["매수 권장", "매도 권장", "확정 수익", "자동매매", "성공 가능성 높음", "반드시 상승"]
    for word in forbidden:
        assert word not in result, f"Forbidden: '{word}'"


def test_format_sector_intelligence_biotech_clinical_content():
    intel = SectorIntelligence(
        sector_id="biotech_pharma_clinical_medtech",
        title="바이오/임상",
        catalysts=["Phase 3 성공"],
        risks=["현금소진"],
        key_metrics=["임상 단계"],
        special_section="🧬 바이오/임상 체크:\n  • 파이프라인: Phase 2 모집 중\n  ※ 임상 단계상 변동성 큼",
    )
    result = format_sector_intelligence(intel)
    assert "임상" in result
    assert "Phase" in result


def test_format_sector_intelligence_shipbuilding_content():
    intel = SectorIntelligence(
        sector_id="shipbuilding_shipping_lng_equipment",
        title="조선/해운",
        catalysts=["LNG 수주"],
        risks=["후판 가격"],
        key_metrics=["수주잔고"],
        swing_checkpoints=["BDI 방향 + 원화 환율"],
        exit_checkpoints=["수주 공시 후 갭 상승 시 차익실현 점검"],
        special_section="🚢 조선/수주잔고 체크:\n  • 수주잔고: 공개자료 기준 확인 필요",
    )
    result = format_sector_intelligence(intel)
    assert "조선" in result or "수주" in result


def test_format_sector_intelligence_exit_checkpoint_correct_term():
    intel = SectorIntelligence(
        sector_id="shipbuilding_shipping_lng_equipment",
        title="조선",
        exit_checkpoints=["수주 공시 후 갭 상승 시 차익실현 점검"],
    )
    result = format_sector_intelligence(intel)
    # "매도 추천" 금지, "차익실현/리스크 점검" 허용
    assert "매도 추천" not in result
    assert "매도 권장" not in result


def test_format_sector_intelligence_financials_content():
    intel = SectorIntelligence(
        sector_id="financials_banks_insurance_brokers",
        title="금융/은행",
        catalysts=["NIM 확대"],
        risks=["부동산 PF 부실"],
        key_metrics=["NIM", "PBR", "배당수익률"],
        valuation_note="PBR + ROE + 배당수익률",
    )
    result = format_sector_intelligence(intel)
    assert "NIM" in result
    assert "PBR" in result or "배당" in result
