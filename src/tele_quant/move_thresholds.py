"""Move Thresholds — 시가총액 규모별 '의미 있는 급등' 기준 모듈.

시총 구간(Tier)에 따라 단순 등락률 필터를 적용하면 초소형주 노이즈를
걸러내고 메가캡 대형 이슈를 포착하는 데 도움이 됩니다.

주의: 공개 정보 기반 리서치 보조. 투자 판단 책임은 사용자에게 있음.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

log = logging.getLogger(__name__)

__all__ = [
    "MoveTier",
    "format_tier_label",
    "get_move_tier",
    "get_significant_move_threshold",
    "is_significant_mover",
]


# ── Tier 정의 ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class MoveTier:
    """시가총액 구간별 급등 임계치.

    Attributes:
        label:    사람이 읽기 좋은 레이블 (예: "Mega", "초대형")
        low_pct:  '의미 있는 움직임' 하한 (%)
        high_pct: '강한 급등' 상한 (%)
        note:     부가 설명 (빈 문자열 허용)
    """

    label: str
    low_pct: float
    high_pct: float
    note: str = ""


# ── US 티어 (내림차순 min_cap 기준) ──────────────────────────────────────────
#   (min_cap_usd, MoveTier)
#   min_cap_usd 단위: USD (달러)

_US_TIERS: list[tuple[float, MoveTier]] = [
    (
        500_000_000_000.0,
        MoveTier(label="Mega", low_pct=5.0, high_pct=10.0),
    ),  # $500B+  — M7 등
    (
        50_000_000_000.0,
        MoveTier(label="Large", low_pct=8.0, high_pct=15.0),
    ),  # $50B~$500B
    (
        5_000_000_000.0,
        MoveTier(label="Mid", low_pct=10.0, high_pct=20.0),
    ),  # $5B~$50B
    (
        500_000_000.0,
        MoveTier(label="Small", low_pct=20.0, high_pct=30.0),
    ),  # $500M~$5B
    (
        0.0,
        MoveTier(label="Micro", low_pct=30.0, high_pct=50.0),
    ),  # <$500M
]

# ── KR 티어 (내림차순 min_cap 기준) ──────────────────────────────────────────
#   min_cap_krw 단위: KRW (원)

_KR_TIERS: list[tuple[float, MoveTier]] = [
    (
        50_000_000_000_000.0,
        MoveTier(label="초대형", low_pct=5.0, high_pct=10.0),
    ),  # 50조+
    (
        10_000_000_000_000.0,
        MoveTier(label="대형", low_pct=8.0, high_pct=15.0),
    ),  # 10조~50조
    (
        1_000_000_000_000.0,
        MoveTier(label="중형", low_pct=10.0, high_pct=20.0),
    ),  # 1조~10조
    (
        300_000_000_000.0,
        MoveTier(label="소형", low_pct=20.0, high_pct=30.0),
    ),  # 3,000억~1조
    (
        0.0,
        MoveTier(
            label="초소형",
            low_pct=30.0,
            high_pct=50.0,
            note="상한가(30%) 주의",
        ),
    ),  # <3,000억
]

# 마켓 코드 → 티어 테이블 매핑
_TIER_MAP: dict[str, list[tuple[float, MoveTier]]] = {
    "US": _US_TIERS,
    "KR": _KR_TIERS,
}

# 마켓별 기본 티어 (시총 정보 없을 때 fallback)
_DEFAULT_TIER: dict[str, MoveTier] = {
    "US": MoveTier(label="Mid", low_pct=10.0, high_pct=20.0),
    "KR": MoveTier(label="중형", low_pct=10.0, high_pct=20.0),
}


# ── 공개 함수 ─────────────────────────────────────────────────────────────────


def get_move_tier(market_cap: float | None, market: str = "US") -> MoveTier:
    """시총(market_cap)과 마켓 코드로 해당 MoveTier를 반환한다.

    Args:
        market_cap: 시가총액 (USD or KRW). None 이면 기본 Mid 티어 반환.
        market:     "US" 또는 "KR".

    Returns:
        해당 구간 MoveTier 인스턴스.
    """
    market = market.upper()
    tiers = _TIER_MAP.get(market, _US_TIERS)
    default = _DEFAULT_TIER.get(market, _DEFAULT_TIER["US"])

    if market_cap is None or market_cap < 0:
        log.debug("market_cap 정보 없음 — 기본 티어(%s) 사용", default.label)
        return default

    for min_cap, tier in tiers:
        if market_cap >= min_cap:
            return tier

    # 이론상 도달 불가 (0.0 기준이 항상 존재하지만 방어적 반환)
    return default


def get_significant_move_threshold(
    symbol: str,
    market_cap: float | None,
    market: str = "US",
) -> float:
    """'의미 있는 급등' 최소 등락률(%) 임계치를 반환한다.

    Args:
        symbol:     종목 티커 (로깅 용도).
        market_cap: 시가총액.
        market:     "US" 또는 "KR".

    Returns:
        low_pct 값 (예: 5.0, 10.0, 20.0 …).
    """
    tier = get_move_tier(market_cap, market)
    log.debug(
        "%s (%s) 티어=%s → 임계치=%.1f%%",
        symbol,
        market,
        tier.label,
        tier.low_pct,
    )
    return tier.low_pct


def is_significant_mover(
    symbol: str,
    move_pct: float,
    market_cap: float | None,
    market: str = "US",
) -> bool:
    """등락률이 해당 시총 구간의 '의미 있는 움직임' 기준을 초과하는지 판단한다.

    절댓값 비교: |move_pct| >= low_pct

    Args:
        symbol:    종목 티커.
        move_pct:  등락률 (%). 음수 급락도 지원.
        market_cap: 시가총액.
        market:    "US" 또는 "KR".

    Returns:
        True if |move_pct| >= threshold.
    """
    threshold = get_significant_move_threshold(symbol, market_cap, market)
    result = abs(move_pct) >= threshold
    if result:
        log.debug(
            "%s 의미 있는 이동 감지: %.1f%% >= %.1f%%",
            symbol,
            move_pct,
            threshold,
        )
    return result


def format_tier_label(tier: MoveTier) -> str:
    """사람이 읽기 좋은 티어 레이블 문자열을 반환한다.

    예시:
        "Mega (5%~10%)"
        "초소형 (30%~50%) — 상한가(30%) 주의"
    """
    base = f"{tier.label} ({tier.low_pct:.0f}%~{tier.high_pct:.0f}%)"
    if tier.note:
        return f"{base} — {tier.note}"
    return base
