"""Tests for sector_macro module — no real network calls."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd

from tele_quant.sector_macro import (
    SECTOR_MACRO_MAP,
    SectorMacroItem,
    SectorMacroSnapshot,
    _compute_signal,
    _fmt_value,
    detect_seed_sector,
    fetch_sector_macro_snapshot,
    format_sector_macro,
    guess_sector_id,
)

# ── Fixtures ──────────────────────────────────────────────────────────────────


def _make_store(tmp_path: Path):
    from tele_quant.db import Store

    return Store(tmp_path / "test.db")


def _fake_history(last_price: float, prev_price: float) -> pd.DataFrame:
    """10일 히스토리 DataFrame — 마지막 값이 last, 5거래일 전이 prev."""
    n = 10
    closes = [prev_price] * (n - 1) + [last_price]
    idx = pd.date_range("2026-05-01", periods=n, freq="B")
    return pd.DataFrame({"Close": closes, "Volume": [1e6] * n}, index=idx)


# ── SECTOR_MACRO_MAP ─────────────────────────────────────────────────────────


def test_sector_macro_map_all_24_sectors():
    """24개 섹터 ID가 모두 존재해야 한다."""
    expected = {
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
    }
    for sector_id in expected:
        assert sector_id in SECTOR_MACRO_MAP, f"Missing sector: {sector_id}"


def test_sector_macro_map_items_have_ticker():
    for sector_id, items in SECTOR_MACRO_MAP.items():
        assert len(items) >= 2, f"{sector_id} has fewer than 2 indicators"
        for item in items:
            assert item.ticker, f"{sector_id}: item '{item.label}' has no ticker"
            assert item.label, f"{sector_id}: item missing label"


# ── _compute_signal ───────────────────────────────────────────────────────────


def test_compute_signal_up_positive_large():
    assert _compute_signal(3.0, True) == "✅ 호재"


def test_compute_signal_up_positive_small():
    assert _compute_signal(1.0, True) == "—"


def test_compute_signal_up_negative_large_drop():
    assert _compute_signal(-3.0, False) == "✅ 호재"


def test_compute_signal_up_negative_large_rise():
    assert _compute_signal(3.0, False) == "⚠ 주의"


def test_compute_signal_none_change():
    assert _compute_signal(None, True) == "—"


def test_compute_signal_none_direction():
    assert _compute_signal(5.0, None) == "—"


def test_compute_signal_down_is_warning():
    assert _compute_signal(-3.0, True) == "⚠ 주의"


# ── _fmt_value ────────────────────────────────────────────────────────────────


def test_fmt_value_pct():
    assert _fmt_value(4.52, "%") == "4.52%"


def test_fmt_value_dollar():
    assert _fmt_value(75.5, "$") == "$75.50"


def test_fmt_value_none():
    assert _fmt_value(None, "%") == "—"


def test_fmt_value_krw():
    assert _fmt_value(1380.0, "원/$") == "1,380원"


def test_fmt_value_pt():
    assert _fmt_value(4.31, "pt") == "4.31pt"


# ── guess_sector_id ─────────────────────────────────────────────────────────


def testguess_sector_id_semiconductor():
    result = guess_sector_id("Semiconductor")
    assert result == "ai_semiconductor_hbm_foundry"


def testguess_sector_id_technology():
    result = guess_sector_id("Technology")
    assert result == "ai_software_cloud_cybersecurity"


def testguess_sector_id_financial():
    result = guess_sector_id("Financial Services")
    assert result == "financials_banks_insurance_brokers"


def testguess_sector_id_healthcare():
    result = guess_sector_id("Healthcare")
    assert result == "healthcare_services_hospitals_diagnostics"


def testguess_sector_id_empty():
    assert guess_sector_id("") is None


def testguess_sector_id_unknown():
    assert guess_sector_id("Quantum Entanglement") is None


def testguess_sector_id_consumer_cyclical():
    result = guess_sector_id("Consumer Cyclical")
    assert result == "retail_ecommerce_logistics_travel_airline_casino"


# ── detect_seed_sector ────────────────────────────────────────────────────────


def test_detect_seed_sector_no_edges(tmp_path):
    store = _make_store(tmp_path)
    result = detect_seed_sector("NVDA", store)
    assert result is None


def test_detect_seed_sector_with_edge(tmp_path):
    store = _make_store(tmp_path)
    _ts = "2026-05-18T00:00:00+00:00"
    with store.connect() as conn:
        conn.execute(
            """INSERT INTO relation_edges
               (source_symbol, source_market, target_symbol, target_market,
                relation_type, direction, confidence, relation_score, active, rule_id,
                created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                "NVDA", "US", "MU", "US", "PEER_MOMENTUM", "UP_LEADS_UP",
                "HIGH", 85.0, 1, "seed:ai_semiconductor_hbm_foundry",
                _ts, _ts,
            ),
        )
    result = detect_seed_sector("NVDA", store)
    assert result == "ai_semiconductor_hbm_foundry"


def test_detect_seed_sector_picks_most_common(tmp_path):
    store = _make_store(tmp_path)
    _ts = "2026-05-18T00:00:00+00:00"
    with store.connect() as conn:
        for _i, (src, tgt, rule) in enumerate([
            ("NVDA", "MU", "seed:ai_semiconductor_hbm_foundry"),
            ("NVDA", "AMD", "seed:ai_semiconductor_hbm_foundry"),
            ("NVDA", "GOOGL", "seed:ai_software_cloud_cybersecurity"),
        ]):
            conn.execute(
                """INSERT INTO relation_edges
                   (source_symbol, source_market, target_symbol, target_market,
                    relation_type, direction, confidence, relation_score, active, rule_id,
                    created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (src, "US", tgt, "US", "PEER_MOMENTUM", "UP_LEADS_UP",
                 "HIGH", 80.0, 1, rule, _ts, _ts),
            )
    result = detect_seed_sector("NVDA", store)
    assert result == "ai_semiconductor_hbm_foundry"


# ── fetch_sector_macro_snapshot ───────────────────────────────────────────────


def test_fetch_sector_macro_snapshot_returns_list():
    with patch("yfinance.Ticker") as MockTicker:
        instance = MagicMock()
        instance.history.return_value = _fake_history(110.0, 100.0)
        MockTicker.return_value = instance

        result = fetch_sector_macro_snapshot("financials_banks_insurance_brokers")

    assert isinstance(result, list)
    assert len(result) == len(SECTOR_MACRO_MAP["financials_banks_insurance_brokers"])
    for snap in result:
        assert isinstance(snap, SectorMacroSnapshot)


def test_fetch_sector_macro_snapshot_positive_change():
    with patch("yfinance.Ticker") as MockTicker:
        instance = MagicMock()
        instance.history.return_value = _fake_history(110.0, 100.0)
        MockTicker.return_value = instance

        result = fetch_sector_macro_snapshot("financials_banks_insurance_brokers")

    # 10Y 금리 (+10%) → up_is_positive=True → ✅ 호재
    tnx_snap = next((s for s in result if s.item.ticker == "^TNX"), None)
    assert tnx_snap is not None
    assert tnx_snap.change_1w_pct is not None
    assert tnx_snap.change_1w_pct > 0


def test_fetch_sector_macro_snapshot_unknown_sector():
    result = fetch_sector_macro_snapshot("nonexistent_sector_xyz")
    assert result == []


def test_fetch_sector_macro_snapshot_yfinance_failure():
    with patch("yfinance.Ticker") as MockTicker:
        instance = MagicMock()
        instance.history.side_effect = RuntimeError("network error")
        MockTicker.return_value = instance

        result = fetch_sector_macro_snapshot("energy_oil_lng_renewables")

    assert isinstance(result, list)
    for snap in result:
        assert snap.current is None
        assert snap.change_1w_pct is None


# ── format_sector_macro ───────────────────────────────────────────────────────


def test_format_sector_macro_returns_string():
    snapshots = [
        SectorMacroSnapshot(
            item=SectorMacroItem("10Y 국채금리", "^TNX", "pt", True),
            current=4.31,
            change_1w_pct=5.2,
            signal="✅ 호재",
        )
    ]
    result = format_sector_macro("financials_banks_insurance_brokers", snapshots)
    assert isinstance(result, str)
    assert "10Y 국채금리" in result
    assert "✅ 호재" in result


def test_format_sector_macro_contains_header():
    snapshots = [
        SectorMacroSnapshot(
            item=SectorMacroItem("WTI 원유", "CL=F", "$", True),
            current=75.5,
            change_1w_pct=-1.0,
            signal="—",
        )
    ]
    result = format_sector_macro("energy_oil_lng_renewables", snapshots)
    assert "섹터 매크로 지표" in result


def test_format_sector_macro_unknown_sector_empty():
    result = format_sector_macro("does_not_exist")
    assert result == ""


def test_format_sector_macro_no_forbidden_words():
    snapshots = [
        SectorMacroSnapshot(
            item=SectorMacroItem("VIX", "^VIX", "pt", False),
            current=18.0,
            change_1w_pct=3.5,
            signal="⚠ 주의",
        )
    ]
    result = format_sector_macro("biotech_pharma_clinical_medtech", snapshots)
    forbidden = ["매수 권장", "확정 수익", "반드시 상승", "자동매매"]
    for word in forbidden:
        assert word not in result


def test_format_sector_macro_with_note():
    snapshots = [
        SectorMacroSnapshot(
            item=SectorMacroItem("천연가스(NG)", "NG=F", "$", False, "비료(암모니아) 원가"),
            current=2.1,
            change_1w_pct=-5.0,
            signal="✅ 호재",
        )
    ]
    result = format_sector_macro("food_agriculture_fertilizer_staples", snapshots)
    assert "비료(암모니아) 원가" in result


def test_format_sector_macro_fetches_when_no_snapshots_given():
    with patch("yfinance.Ticker") as MockTicker:
        instance = MagicMock()
        instance.history.return_value = _fake_history(100.0, 98.0)
        MockTicker.return_value = instance

        result = format_sector_macro("energy_oil_lng_renewables")

    assert isinstance(result, str)
    assert "WTI 원유" in result


# ── stock_snapshot integration ────────────────────────────────────────────────


def test_build_stock_snapshot_has_sector_macro_field(tmp_path):
    """StockAnalysisSnapshot에 sector_macro_text 필드가 있어야 한다."""
    from tele_quant.stock_snapshot import StockAnalysisSnapshot

    snap = StockAnalysisSnapshot(symbol="NVDA", market="US")
    assert hasattr(snap, "sector_macro_text")
    assert snap.sector_macro_text == ""


def test_build_stock_snapshot_sector_macro_in_output(tmp_path):
    """build_stock_snapshot + format_stock_snapshot 에 섹터 매크로 텍스트가 포함돼야 한다."""
    from tele_quant.stock_snapshot import StockAnalysisSnapshot, format_stock_snapshot

    snap = StockAnalysisSnapshot(symbol="NVDA", market="US")
    snap.sector_macro_text = "🌐 섹터 매크로 지표 (1주 변화):\n  • WTI 원유: $75.50 (+1.2%)"
    output = format_stock_snapshot(snap)
    assert "섹터 매크로 지표" in output


def testguess_sector_id_energy():
    result = guess_sector_id("Energy")
    assert result == "energy_oil_lng_renewables"


def testguess_sector_id_defense():
    result = guess_sector_id("Defense")
    assert result == "defense_space_aerospace_drone"
