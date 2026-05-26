"""Relation target filter — source 이벤트 기반 swing 후보 필터링.

source event가 확실하고, relation confidence가 MEDIUM 이상이며,
target 차트가 조건을 만족할 때만 LONG/SHORT 관찰 후보를 반환한다.
FLOW_ONLY / UNKNOWN source는 WATCH_ONLY 처리.

공개 정보 기반 리서치 보조. 투자 판단 책임은 사용자에게 있음.
"매수 권장" / "매도 권장" 표현 금지.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from tele_quant.catalyst_classifier import CatalystConfidence, CatalystResult

log = logging.getLogger(__name__)

__all__ = [
    "RelationCandidate",
    "TargetTechnicals",
    "filter_relation_targets_for_swing",
    "score_target_technical",
]


@dataclass
class TargetTechnicals:
    """target 종목의 기술지표 스냅샷."""
    rsi_4h: float | None = None
    obv_trend_4h: str = ""          # "상승" | "하락" | "횡보"
    bb_position_4h: str = ""        # "중단 회복" | "중단 이탈" | "상단" | "하단" | "수축"
    rsi_3d: float | None = None
    trend_3d: str = ""              # "상승" | "하락" | "횡보"
    volume_ratio_4h: float | None = None
    return_1m_pct: float | None = None  # 최근 1개월 수익률 (과열 감지용)
    return_1d_pct: float | None = None
    market_cap_krw: float | None = None  # KR 시총 (억 원)
    market_cap_usd: float | None = None  # US 시총 (백만 달러)


@dataclass
class RelationCandidate:
    """filter 결과 — LONG/SHORT/WATCH_ONLY 관찰 후보."""
    symbol: str
    name: str = ""
    market: str = ""
    side: str = "WATCH_ONLY"   # LONG_OBSERVE | SHORT_OBSERVE | WATCH_ONLY | EXIT_CHECK
    score: float = 0.0
    confidence: str = ""        # HIGH | MEDIUM | LOW
    source_event_symbol: str = ""
    source_event_reason: str = ""
    relation_type: str = ""
    direction: str = ""
    expected_lag_hours: int = 24
    entry_ref_price: float | None = None
    invalidation_price: float | None = None
    target_zone_price: float | None = None
    horizon: str = "1D~1M"
    thesis: str = ""
    caution_flags: list[str] = field(default_factory=list)
    policy_note: str = ""


# ── 기술 점수 계산 ───────────────────────────────────────────────────────────

def score_target_technical(tech: TargetTechnicals, side: str) -> tuple[float, list[str]]:
    """LONG / SHORT 방향 기준 기술점수 및 주의사항 반환.

    Returns:
        (tech_score 0~30, caution_flags)
    """
    score = 0.0
    cautions: list[str] = []

    if side == "LONG_OBSERVE":
        # RSI 4H: 45~65 구간이 이상적
        if tech.rsi_4h is not None:
            if 45 <= tech.rsi_4h <= 65:
                score += 8.0
            elif 35 <= tech.rsi_4h < 45:
                score += 5.0  # 반등 가능 구간
            elif tech.rsi_4h > 70:
                score -= 5.0
                cautions.append(f"4H RSI {tech.rsi_4h:.0f} 과열 — LONG 추격주의")
            elif tech.rsi_4h < 30:
                score += 3.0  # 과매도 반등 가능성

        # OBV 4H
        if tech.obv_trend_4h == "상승":
            score += 8.0
        elif tech.obv_trend_4h == "하락":
            score -= 4.0
            cautions.append("OBV4H 하락 — 매집 미확인")

        # BB 위치
        if tech.bb_position_4h in ("중단 회복", "수축 후 상단 접근"):
            score += 7.0
        elif tech.bb_position_4h == "중단 이탈":
            score -= 3.0
            cautions.append("BB 중단 이탈")

        # 3D 추세
        if tech.trend_3d == "상승":
            score += 5.0
        elif tech.trend_3d == "하락":
            score -= 3.0
            cautions.append("3D 약세 추세")

        # 1개월 급등 페널티
        if tech.return_1m_pct is not None and tech.return_1m_pct > 30:
            score -= 8.0
            cautions.append(f"1M +{tech.return_1m_pct:.0f}% 급등 — 추격주의")

    elif side == "SHORT_OBSERVE":
        # RSI 4H: 70 이상 후 꺾임이 이상적
        if tech.rsi_4h is not None:
            if tech.rsi_4h >= 70:
                score += 8.0
            elif 60 <= tech.rsi_4h < 70:
                score += 4.0
            elif tech.rsi_4h < 45:
                score -= 5.0
                cautions.append(f"4H RSI {tech.rsi_4h:.0f} — SHORT 기준 미충족")

        # OBV 4H 하락
        if tech.obv_trend_4h == "하락":
            score += 8.0
        elif tech.obv_trend_4h == "상승":
            score -= 4.0
            cautions.append("OBV4H 상승 — SHORT 역방향")

        # BB 이탈
        if tech.bb_position_4h == "중단 이탈":
            score += 7.0
        elif tech.bb_position_4h in ("중단 회복", "수축 후 상단 접근"):
            score -= 3.0

        # 3D 약세
        if tech.trend_3d == "하락":
            score += 5.0
        elif tech.trend_3d == "상승":
            score -= 3.0
            cautions.append("3D 상승 추세 — SHORT 역방향")

    return max(0.0, min(30.0, score)), cautions


# ── 주요 필터 함수 ───────────────────────────────────────────────────────────

def filter_relation_targets_for_swing(
    source_event: dict[str, Any],
    relation_edges: list[dict[str, Any]],
    technicals_map: dict[str, TargetTechnicals] | None = None,
    slot: str = "weekday_4h",
    now: Any = None,
) -> list[RelationCandidate]:
    """source 이벤트 기반 relation target 후보 필터링.

    Args:
        source_event: {
            "symbol": str,
            "catalyst_result": CatalystResult,
            "return_pct": float,   # source 종목 급등/급락 비율
            "reason": str,
        }
        relation_edges: [{"target_symbol", "target_name", "market", "relation_type",
                          "direction", "confidence", "expected_lag_hours"}, ...]
        technicals_map: symbol → TargetTechnicals (없으면 기술점수 0)
        slot: monday_open | weekday_4h | weekend_issue | sunday_review
        now: datetime (없으면 현재)

    Returns:
        RelationCandidate 리스트 (score 내림차순)
    """
    from tele_quant.calendar_score_policy import CalendarMode, get_current_policy

    catalyst: CatalystResult | None = source_event.get("catalyst_result")  # type: ignore[assignment]
    source_sym = source_event.get("symbol", "")
    source_reason = source_event.get("reason", "")
    results: list[RelationCandidate] = []

    # source 이벤트가 FLOW_ONLY / UNKNOWN이면 전부 WATCH_ONLY
    if catalyst is None or not catalyst.is_actionable:
        for edge in relation_edges[:3]:
            results.append(RelationCandidate(
                symbol=edge.get("target_symbol", ""),
                name=edge.get("target_name", ""),
                market=edge.get("market", ""),
                side="WATCH_ONLY",
                score=0.0,
                confidence="LOW",
                source_event_symbol=source_sym,
                source_event_reason=source_reason,
                relation_type=edge.get("relation_type", ""),
                direction=edge.get("direction", ""),
                expected_lag_hours=int(edge.get("expected_lag_hours") or 24),
                thesis="source 이벤트 미확인 (FLOW_ONLY/UNKNOWN) — 기록만, 추천 없음",
            ))
        return results

    # 캘린더 정책 확인
    adj = get_current_policy(now=now)
    is_monday_strict = adj.mode == CalendarMode.MONDAY_LONG_STRICT
    is_friday_exit = adj.mode == CalendarMode.FRIDAY_EXIT_STRICT
    is_weekend = slot in ("weekend_issue", "sunday_review")

    for edge in relation_edges:
        edge_conf_str = (edge.get("confidence") or "LOW").upper()
        edge_conf = CatalystConfidence.HIGH if edge_conf_str == "HIGH" else (
            CatalystConfidence.MEDIUM if edge_conf_str == "MEDIUM" else CatalystConfidence.LOW
        )
        target_sym = edge.get("target_symbol", "")
        target_name = edge.get("target_name", "")
        market = edge.get("market", "")
        direction = (edge.get("direction") or "").upper()
        relation_type = edge.get("relation_type", "")
        lag_h = int(edge.get("expected_lag_hours") or 24)

        # LOW confidence는 WATCH_ONLY
        if edge_conf == CatalystConfidence.LOW:
            results.append(RelationCandidate(
                symbol=target_sym, name=target_name, market=market,
                side="WATCH_ONLY", score=5.0, confidence="LOW",
                source_event_symbol=source_sym, source_event_reason=source_reason,
                relation_type=relation_type, direction=direction,
                expected_lag_hours=lag_h,
                thesis="relation confidence LOW — 관찰만",
            ))
            continue

        # 주말에는 신규 LONG/SHORT 추천 없음
        if is_weekend:
            results.append(RelationCandidate(
                symbol=target_sym, name=target_name, market=market,
                side="WATCH_ONLY", score=10.0, confidence=edge_conf_str,
                source_event_symbol=source_sym, source_event_reason=source_reason,
                relation_type=relation_type, direction=direction,
                expected_lag_hours=lag_h,
                thesis="주말 — 차트 기반 LONG/SHORT 추천 제외",
            ))
            continue

        # 기술 점수
        tech = (technicals_map or {}).get(target_sym, TargetTechnicals())
        base_side = "LONG_OBSERVE" if direction in ("POSITIVE", "UP", "LONG") else (
            "SHORT_OBSERVE" if direction in ("NEGATIVE", "DOWN", "SHORT") else "WATCH_ONLY"
        )

        if base_side == "WATCH_ONLY":
            results.append(RelationCandidate(
                symbol=target_sym, name=target_name, market=market,
                side="WATCH_ONLY", score=10.0, confidence=edge_conf_str,
                source_event_symbol=source_sym, source_event_reason=source_reason,
                relation_type=relation_type, direction=direction,
                expected_lag_hours=lag_h,
                thesis="방향 불명확 — 관찰만",
            ))
            continue

        tech_score, cautions = score_target_technical(tech, base_side)

        # 기본 점수: catalyst 신뢰도 + relation 신뢰도 + 기술점수
        cat_base = 30.0 if catalyst.confidence == CatalystConfidence.HIGH else 20.0
        rel_base = 20.0 if edge_conf == CatalystConfidence.HIGH else 10.0
        total_score = cat_base + rel_base + tech_score

        policy_note = ""

        # 월요일 엄격 모드: LONG 하향/제외
        if is_monday_strict and base_side == "LONG_OBSERVE":
            total_score -= 5.0
            policy_note = "⚠ 월요일 오전 보수 모드 — LONG 점수 하향"
            if adj.require_direct_evidence and catalyst.confidence != CatalystConfidence.HIGH:
                base_side = "WATCH_ONLY"
                policy_note += " (직접 증거 없음 → WATCH_ONLY)"
            if tech.return_1d_pct and tech.return_1d_pct >= (adj.avoid_gap_chase_pct or 8.0):
                base_side = "WATCH_ONLY"
                policy_note += f" (갭 +{tech.return_1d_pct:.1f}% → WATCH_ONLY)"
            if tech.rsi_4h and tech.rsi_4h >= (adj.overheat_rsi or 70.0):
                base_side = "WATCH_ONLY"
                policy_note += f" (RSI {tech.rsi_4h:.0f} 과열 → WATCH_ONLY)"

        # 금요일 EXIT 강화
        if is_friday_exit and base_side == "LONG_OBSERVE" and tech.rsi_4h and tech.rsi_4h >= (adj.overheat_rsi or 72.0):
            cautions.append(f"금요일 RSI {tech.rsi_4h:.0f} → EXIT_CHECK 우선")
            base_side = "EXIT_CHECK"
            policy_note = "⚠ 금요일 리스크 점검 모드"

        # 최소 기술점수 미달이면 WATCH_ONLY
        if tech_score < 5.0 and base_side in ("LONG_OBSERVE", "SHORT_OBSERVE"):
            cautions.append("기술 조건 미달 → 관찰만")
            base_side = "WATCH_ONLY"

        results.append(RelationCandidate(
            symbol=target_sym,
            name=target_name,
            market=market,
            side=base_side,
            score=max(0.0, total_score),
            confidence=edge_conf_str,
            source_event_symbol=source_sym,
            source_event_reason=source_reason,
            relation_type=relation_type,
            direction=direction,
            expected_lag_hours=lag_h,
            thesis=(
                f"source={source_sym}({label_catalyst(catalyst)}) "
                f"rel={relation_type}/{edge_conf_str} "
                f"tech={tech_score:.0f}pt"
            ),
            caution_flags=cautions,
            policy_note=policy_note,
        ))

    results.sort(key=lambda c: -c.score)
    return results


def label_catalyst(result: CatalystResult) -> str:
    from tele_quant.catalyst_classifier import label_for_display
    return label_for_display(result)
