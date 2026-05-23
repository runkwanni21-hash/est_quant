from __future__ import annotations

from datetime import datetime, timezone

from tele_quant.catalyst_classifier import CatalystConfidence, CatalystResult, CatalystType
from tele_quant.relation_target_filter import (
    TargetTechnicals,
    filter_relation_targets_for_swing,
    score_target_technical,
)

KST = timezone(__import__("datetime").timedelta(hours=9))


def _make_catalyst(cat_type=CatalystType.DART_CONTRACT, conf=CatalystConfidence.HIGH):
    return CatalystResult(catalyst_type=cat_type, confidence=conf, reason="test")


def _make_edge(direction="POSITIVE", confidence="HIGH", symbol="005935.KS", name="삼성전자우"):
    return {
        "target_symbol": symbol,
        "target_name": name,
        "market": "KR",
        "relation_type": "supply_chain",
        "direction": direction,
        "confidence": confidence,
        "expected_lag_hours": 24,
    }


def _good_long_tech():
    return TargetTechnicals(
        rsi_4h=55.0,
        obv_trend_4h="상승",
        bb_position_4h="중단 회복",
        trend_3d="상승",
        return_1m_pct=10.0,
    )


def _good_short_tech():
    return TargetTechnicals(
        rsi_4h=75.0,
        obv_trend_4h="하락",
        bb_position_4h="중단 이탈",
        trend_3d="하락",
    )


# ── catalyst 기반 필터 테스트 ─────────────────────────────────────────────────

def test_high_event_high_relation_good_chart_gives_long_observe():
    source = {
        "symbol": "NVDA",
        "catalyst_result": _make_catalyst(CatalystType.EARNINGS, CatalystConfidence.HIGH),
        "return_pct": 8.0,
        "reason": "earnings beat",
    }
    edges = [_make_edge(direction="POSITIVE", confidence="HIGH")]
    tech_map = {edges[0]["target_symbol"]: _good_long_tech()}
    results = filter_relation_targets_for_swing(source, edges, tech_map, slot="weekday_4h")
    assert results
    assert results[0].side == "LONG_OBSERVE"
    assert results[0].score > 40


def test_flow_only_source_gives_watch_only():
    source = {
        "symbol": "XYZ",
        "catalyst_result": _make_catalyst(CatalystType.FLOW_ONLY, CatalystConfidence.LOW),
        "return_pct": 5.0,
        "reason": "이유 불명",
    }
    edges = [_make_edge()]
    results = filter_relation_targets_for_swing(source, edges, slot="weekday_4h")
    assert all(r.side == "WATCH_ONLY" for r in results)


def test_low_relation_confidence_gives_watch_only():
    source = {
        "symbol": "NVDA",
        "catalyst_result": _make_catalyst(CatalystType.EARNINGS, CatalystConfidence.HIGH),
        "return_pct": 8.0,
        "reason": "earnings",
    }
    edges = [_make_edge(confidence="LOW")]
    results = filter_relation_targets_for_swing(source, edges, slot="weekday_4h")
    assert results
    assert results[0].side == "WATCH_ONLY"


def test_overheated_target_excluded_from_long():
    """RSI 80 + 1M +40% → 추격주의 → WATCH_ONLY."""
    source = {
        "symbol": "NVDA",
        "catalyst_result": _make_catalyst(CatalystType.EARNINGS, CatalystConfidence.HIGH),
        "return_pct": 8.0,
        "reason": "earnings",
    }
    edges = [_make_edge()]
    overheated = TargetTechnicals(
        rsi_4h=82.0,
        obv_trend_4h="상승",
        bb_position_4h="상단",
        trend_3d="상승",
        return_1m_pct=42.0,
    )
    results = filter_relation_targets_for_swing(
        source, edges, {edges[0]["target_symbol"]: overheated}, slot="weekday_4h"
    )
    assert results
    # 과열 페널티 적용 — LONG이라도 WATCH_ONLY이거나 score 낮음
    r = results[0]
    assert r.side == "WATCH_ONLY" or any("추격주의" in f or "과열" in f for f in r.caution_flags)


def test_weak_chart_short_observe():
    source = {
        "symbol": "INTC",
        "catalyst_result": _make_catalyst(CatalystType.EARNINGS, CatalystConfidence.MEDIUM),
        "return_pct": -8.0,
        "reason": "earnings miss",
    }
    edges = [_make_edge(direction="NEGATIVE", confidence="HIGH")]
    tech_map = {edges[0]["target_symbol"]: _good_short_tech()}
    results = filter_relation_targets_for_swing(source, edges, tech_map, slot="weekday_4h")
    assert results
    assert results[0].side == "SHORT_OBSERVE"
    assert results[0].score > 30


def test_monday_morning_long_excluded():
    """월요일 오전 직접 증거 없는 LONG → WATCH_ONLY."""
    # Mon 07:30 KST
    mon_morning = datetime(2026, 5, 18, 7, 30, tzinfo=KST)
    source = {
        "symbol": "NVDA",
        "catalyst_result": _make_catalyst(CatalystType.RELATION_READTHROUGH, CatalystConfidence.MEDIUM),
        "return_pct": 5.0,
        "reason": "read-through",
    }
    edges = [_make_edge(direction="POSITIVE", confidence="HIGH")]
    tech_map = {edges[0]["target_symbol"]: _good_long_tech()}
    results = filter_relation_targets_for_swing(
        source, edges, tech_map, slot="monday_open", now=mon_morning
    )
    assert results
    r = results[0]
    # 월요일 오전 + MEDIUM confidence → require_direct_evidence → WATCH_ONLY
    assert r.side == "WATCH_ONLY" or r.policy_note


def test_weekend_no_long_short():
    """주말 슬롯은 LONG/SHORT 없음 → WATCH_ONLY."""
    source = {
        "symbol": "NVDA",
        "catalyst_result": _make_catalyst(CatalystType.EARNINGS, CatalystConfidence.HIGH),
        "return_pct": 10.0,
        "reason": "earnings",
    }
    edges = [_make_edge(direction="POSITIVE", confidence="HIGH")]
    tech_map = {edges[0]["target_symbol"]: _good_long_tech()}
    results = filter_relation_targets_for_swing(
        source, edges, tech_map, slot="weekend_issue"
    )
    assert results
    assert all(r.side == "WATCH_ONLY" for r in results)


# ── 기술 점수 테스트 ──────────────────────────────────────────────────────────

def test_score_target_long_good():
    tech = _good_long_tech()
    score, cautions = score_target_technical(tech, "LONG_OBSERVE")
    assert score >= 15.0
    assert not any("과열" in c for c in cautions)


def test_score_target_long_overheated():
    tech = TargetTechnicals(rsi_4h=80.0, obv_trend_4h="상승", return_1m_pct=35.0)
    _score, cautions = score_target_technical(tech, "LONG_OBSERVE")
    assert any("과열" in c or "급등" in c for c in cautions)


def test_score_target_short_good():
    tech = _good_short_tech()
    score, _cautions = score_target_technical(tech, "SHORT_OBSERVE")
    assert score >= 15.0


def test_score_target_short_wrong_direction():
    tech = TargetTechnicals(rsi_4h=40.0, obv_trend_4h="상승", trend_3d="상승")
    _score, cautions = score_target_technical(tech, "SHORT_OBSERVE")
    assert any("역방향" in c or "미충족" in c for c in cautions)
