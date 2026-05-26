"""Calendar-aware score policy — Monday strict LONG / Friday EXIT check.

공개 정보 기반 리서치 보조. 투자 판단 책임은 사용자에게 있음.
"매수 권장" / "매도 권장" / "확정 수익" 표현 금지.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

log = logging.getLogger(__name__)

__all__ = [
    "CalendarMode",
    "CalendarScorePolicy",
    "PolicyAdjustment",
    "apply_policy_to_score",
    "format_policy_note",
    "get_current_policy",
]

_KST_OFFSET = 9  # UTC+9


def _now_kst() -> datetime:
    from datetime import timedelta, timezone
    return datetime.now(timezone(timedelta(hours=_KST_OFFSET)))


class CalendarMode(str, Enum):  # noqa: UP042
    NORMAL = "NORMAL"
    MONDAY_LONG_STRICT = "MONDAY_LONG_STRICT"
    FRIDAY_EXIT_STRICT = "FRIDAY_EXIT_STRICT"


@dataclass
class CalendarScorePolicy:
    """스코어 정책 설정값."""

    # 월요일 오전 LONG 엄격 모드
    monday_long_strict_enabled: bool = True
    monday_long_strict_start_hour: int = 6    # KST
    monday_long_strict_end_hour: int = 12     # KST (11:30 반올림)
    monday_long_score_penalty: float = 5.0
    monday_long_min_score: float = 78.0
    monday_require_direct_evidence: bool = True
    monday_avoid_gap_chase_pct: float = 8.0    # 갭 +8% 이상 추격 주의
    monday_overheat_rsi: float = 70.0

    # 금요일 저녁 EXIT 관찰 모드
    friday_exit_strict_enabled: bool = True
    friday_exit_start_hour: int = 14          # KST
    friday_exit_end_hour: int = 20            # KST (18:30 + 마감 후)
    friday_weekly_winner_pct: float = 8.0     # 주간 수익률 이 이상이면 EXIT 강화
    friday_exit_score_boost: float = 8.0      # EXIT 관찰 점수 부스트
    friday_overheat_rsi: float = 72.0
    friday_volume_climax_ratio: float = 2.5
    friday_profit_target_pct: float = 5.0     # 5% 기대 보상 구간 도달 여부 체크


_DEFAULT_POLICY = CalendarScorePolicy()


@dataclass
class PolicyAdjustment:
    """스코어 조정 결과."""

    mode: CalendarMode
    long_penalty: float = 0.0          # LONG 점수에서 차감
    exit_boost: float = 0.0            # EXIT 관찰 점수에 가산
    min_score_for_action: float = 70.0
    require_direct_evidence: bool = False
    avoid_gap_chase_pct: float | None = None
    overheat_rsi: float | None = None
    profit_target_pct: float | None = None
    note: str = ""
    active: bool = False


def get_current_policy(
    now: datetime | None = None,
    policy: CalendarScorePolicy | None = None,
) -> PolicyAdjustment:
    """현재 KST 시각에 맞는 PolicyAdjustment 반환."""
    cfg = policy or _DEFAULT_POLICY
    dt = now if now is not None else _now_kst()

    # KST 요일: Monday=0, Friday=4, Saturday=5, Sunday=6
    weekday = dt.weekday()
    hour = dt.hour

    # ── 월요일 오전 LONG 엄격 ─────────────────────────────────────────────────
    if (
        cfg.monday_long_strict_enabled
        and weekday == 0  # Monday
        and cfg.monday_long_strict_start_hour <= hour < cfg.monday_long_strict_end_hour
    ):
        return PolicyAdjustment(
            mode=CalendarMode.MONDAY_LONG_STRICT,
            long_penalty=cfg.monday_long_score_penalty,
            min_score_for_action=cfg.monday_long_min_score,
            require_direct_evidence=cfg.monday_require_direct_evidence,
            avoid_gap_chase_pct=cfg.monday_avoid_gap_chase_pct,
            overheat_rsi=cfg.monday_overheat_rsi,
            note=(
                "⚠ 월요일 오전 엄격 모드: 주말 뉴스/갭 리스크로 LONG 기준을 보수적으로 적용 "
                f"(점수 -{cfg.monday_long_score_penalty:.0f}, 최소 {cfg.monday_long_min_score:.0f}점 필요)"
            ),
            active=True,
        )

    # ── 금요일 저녁 EXIT 관찰 ─────────────────────────────────────────────────
    if (
        cfg.friday_exit_strict_enabled
        and weekday == 4  # Friday
        and cfg.friday_exit_start_hour <= hour < cfg.friday_exit_end_hour
    ):
        return PolicyAdjustment(
            mode=CalendarMode.FRIDAY_EXIT_STRICT,
            exit_boost=cfg.friday_exit_score_boost,
            overheat_rsi=cfg.friday_overheat_rsi,
            profit_target_pct=cfg.friday_profit_target_pct,
            note=(
                "⚠ 금요일 리스크 점검 모드: 주간 급등 종목은 주말 갭 리스크를 고려해 "
                "차익실현/무효화 체크를 강화"
            ),
            active=True,
        )

    return PolicyAdjustment(mode=CalendarMode.NORMAL, active=False)


def apply_policy_to_score(
    score: float,
    side: str,  # "LONG" | "SHORT" | "EXIT"
    price_change_1d: float | None = None,
    rsi_4h: float | None = None,
    price_change_1w: float | None = None,
    now: datetime | None = None,
    policy: CalendarScorePolicy | None = None,
) -> tuple[float, str]:
    """스코어를 정책에 따라 조정하고 (adjusted_score, note) 반환."""
    adj = get_current_policy(now=now, policy=policy)
    note = adj.note if adj.active else ""

    if adj.mode == CalendarMode.MONDAY_LONG_STRICT and side == "LONG":
        score -= adj.long_penalty
        if rsi_4h and adj.overheat_rsi and rsi_4h > adj.overheat_rsi:
            score -= 3.0
            note += f" (4H RSI {rsi_4h:.0f} 과열 -3)"
        if price_change_1d and adj.avoid_gap_chase_pct and price_change_1d >= adj.avoid_gap_chase_pct:
            score -= 5.0
            note += f" (갭 +{price_change_1d:.1f}% 추격 주의 -5)"

    elif adj.mode == CalendarMode.FRIDAY_EXIT_STRICT and side in ("LONG", "EXIT"):
        if price_change_1w and price_change_1w >= (policy or _DEFAULT_POLICY).friday_weekly_winner_pct:
            score -= adj.exit_boost
            note += f" (주간 +{price_change_1w:.1f}% 급등 — 차익실현/리스크 점검 점수 강화)"
        if rsi_4h and adj.overheat_rsi and rsi_4h > adj.overheat_rsi:
            score -= 3.0
            note += f" (4H RSI {rsi_4h:.0f} → 리스크 점검)"

    return max(0.0, score), note


def format_policy_note(now: datetime | None = None) -> str:
    """현재 정책 노트 문자열 반환. 정책 비활성이면 빈 문자열."""
    adj = get_current_policy(now=now)
    return adj.note if adj.active else ""
