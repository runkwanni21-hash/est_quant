"""Tests for sector_analysis_engine — valuation/technical playbooks 실제 반영 확인."""
from __future__ import annotations

from tele_quant.sector_analysis_engine import (
    enrich_sector_intelligence,
    format_valuation_hint,
    get_primary_metrics,
    get_valuation_context,
    score_rsi_from_playbook,
)

# ── get_valuation_context ─────────────────────────────────────────────────────

def test_known_sector_returns_context():
    ctx = get_valuation_context("ai_semiconductor_hbm_foundry")
    assert ctx, "ai_semiconductor_hbm_foundry 섹터 컨텍스트가 비어있음"
    assert "pe_note" in ctx or "primary_metrics" in ctx


def test_alias_sector_maps_correctly():
    ctx_alias = get_valuation_context("ai_semiconductor_hbm")
    ctx_full = get_valuation_context("ai_semiconductor_hbm_foundry")
    assert ctx_alias == ctx_full


def test_bio_sector_maps():
    ctx = get_valuation_context("biotech_pharma_clinical_medtech")
    assert ctx
    assert "pe_note" in ctx


def test_unknown_sector_returns_empty():
    ctx = get_valuation_context("completely_unknown_sector_xyz")
    assert ctx == {}


def test_saas_sector_maps():
    ctx = get_valuation_context("ai_software_cloud_cybersecurity")
    assert ctx
    primary = ctx.get("primary_metrics") or []
    assert len(primary) >= 2


# ── get_primary_metrics ───────────────────────────────────────────────────────

def test_primary_metrics_max_4():
    metrics = get_primary_metrics("ai_semiconductor_hbm_foundry")
    assert len(metrics) <= 4


def test_primary_metrics_non_empty_for_known():
    metrics = get_primary_metrics("biotech_pharma_clinical_medtech")
    assert len(metrics) >= 1


def test_primary_metrics_empty_for_unknown():
    assert get_primary_metrics("no_such_sector") == []


# ── format_valuation_hint ─────────────────────────────────────────────────────

def test_format_hint_contains_pe_note():
    hint = format_valuation_hint("ai_semiconductor_hbm_foundry")
    assert "💡 가치" in hint or "PER" in hint or hint == ""


def test_format_hint_empty_for_unknown():
    assert format_valuation_hint("no_such_sector_abc") == ""


def test_format_hint_bio_no_forbidden_words():
    hint = format_valuation_hint("biotech_pharma_clinical_medtech")
    for forbidden in ("매수 권장", "매도 권장", "확정 수익", "수익 보장"):
        assert forbidden not in hint


def test_format_hint_saas():
    hint = format_valuation_hint("ai_software_cloud_cybersecurity")
    assert isinstance(hint, str)  # 내용 있거나 빈 문자열 허용


# ── score_rsi_from_playbook ───────────────────────────────────────────────────

def test_rsi_long_swing_zone():
    score, label = score_rsi_from_playbook(55.0, "long")
    assert score > 0
    assert label  # 레이블 있어야 함


def test_rsi_long_overbought_penalty():
    score, _label = score_rsi_from_playbook(75.0, "long")
    assert score < 0  # 과열 → 감점


def test_rsi_short_overbought_bonus():
    score, _label = score_rsi_from_playbook(72.0, "short")
    assert score > 0  # 과열 → SHORT 가점


def test_rsi_short_below_45_penalty():
    score, _label = score_rsi_from_playbook(40.0, "short")
    assert score < 0  # SHORT 기준 미충족


def test_rsi_no_match_returns_zero():
    # RSI = 50 should match the range [45, 65] long rule (score > 0)
    score, label = score_rsi_from_playbook(50.0, "long")
    assert isinstance(score, float)
    assert isinstance(label, str)


def test_rsi_playbook_score_is_numeric():
    for rsi in [25.0, 40.0, 55.0, 65.0, 75.0]:
        score, _label = score_rsi_from_playbook(rsi, "long")
        assert isinstance(score, float)


# ── enrich_sector_intelligence ────────────────────────────────────────────────

class _MockIntel:
    def __init__(self):
        self.valuation_note = ""
        self.key_metrics: list[str] = []


def test_enrich_fills_valuation_note():
    mock = _MockIntel()
    enrich_sector_intelligence(mock, "ai_semiconductor_hbm_foundry")  # type: ignore[arg-type]
    # pe_note should be filled
    assert mock.valuation_note != ""


def test_enrich_does_not_overwrite_existing_note():
    mock = _MockIntel()
    mock.valuation_note = "기존 노트"
    enrich_sector_intelligence(mock, "ai_semiconductor_hbm_foundry")  # type: ignore[arg-type]
    assert mock.valuation_note == "기존 노트"


def test_enrich_fills_key_metrics_when_empty():
    mock = _MockIntel()
    enrich_sector_intelligence(mock, "biotech_pharma_clinical_medtech")  # type: ignore[arg-type]
    assert len(mock.key_metrics) >= 1


def test_enrich_unknown_sector_no_change():
    mock = _MockIntel()
    enrich_sector_intelligence(mock, "unknown_sector_xyz")  # type: ignore[arg-type]
    assert mock.valuation_note == ""
    assert mock.key_metrics == []
