"""실적-주가 괴리 감지기 (Mispricing / Turnaround Detector).

흑자 턴어라운드·실적 개선이 주가에 선반영되지 않은 종목을 탐지한다.

탐지 시나리오:
  1. 적자→흑자 턴어라운드 (net_income 음→양 전환)
  2. 영업이익 급반등 (전년대비 +50% 이상)
  3. EPS 서프라이즈 연속 비트 (3분기 이상) + 주가 52주 저점권
  4. 매출 성장 가속화 + 주가 횡보

주가 미반응 판단 기준:
  - 실적 개선 시점으로부터 6개월 이내 주가 변동 < +10%
  - 현재 주가가 52주 범위 하위 40% 이내

출력: MispricingResult dataclass + format_mispricing() 텍스트

주의: 매수·매도 확정 표현 금지. 투자 판단 책임은 사용자에게 있음.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger(__name__)

__all__ = [
    "MispricingResult",
    "detect_mispricing",
    "format_mispricing",
]


@dataclass
class MispricingSignal:
    """개별 괴리 신호."""

    signal_type: str           # "turnaround" | "op_rebound" | "beat_streak" | "rev_accel"
    label: str                 # 표시 텍스트
    strength: float            # 0~1 (강도)
    detail: str = ""


@dataclass
class MispricingResult:
    """실적-주가 괴리 분석 결과."""

    symbol: str
    signals: list[MispricingSignal] = field(default_factory=list)
    price_position_pct: float | None = None   # 52주 범위 내 위치 (0=저점, 100=고점)
    price_6m_chg_pct: float | None = None     # 6개월 주가 변동율 %
    total_score: float = 0.0                  # 0~100 (실적-주가 괴리 점수)
    conclusion: str = "해당없음"               # "강한괴리" | "괴리가능" | "보통" | "해당없음"
    summary: str = ""


def detect_mispricing(
    symbol: str,
    market: str = "",
    *,
    price_position_pct: float | None = None,
    price_6m_chg_pct: float | None = None,
) -> MispricingResult:
    """실적-주가 괴리 탐지.

    Args:
        symbol: 종목 코드
        market: "KR" | "US"
        price_position_pct: 52주 범위 내 위치 (stock_snapshot에서 전달)
        price_6m_chg_pct: 6개월 주가 변동율 % (stock_snapshot에서 전달)
    """
    result = MispricingResult(symbol=symbol)
    result.price_position_pct = price_position_pct
    result.price_6m_chg_pct = price_6m_chg_pct

    try:
        from tele_quant.earnings_history import fetch_earnings_history
        history = fetch_earnings_history(symbol, market=market, years=4)
        if not history.data_limited and history.results:
            _check_turnaround(result, history)
            _check_op_rebound(result, history)
            _check_rev_acceleration(result, history)
    except Exception as exc:
        log.debug("[mispricing] earnings_history 실패 %s: %s", symbol, exc)

    try:
        from tele_quant.earnings_surprise import fetch_earnings_surprise
        es = fetch_earnings_surprise(symbol)
        _check_beat_streak(result, es)
    except Exception as exc:
        log.debug("[mispricing] earnings_surprise 실패 %s: %s", symbol, exc)

    _compute_score(result)
    return result


def _check_turnaround(result: MispricingResult, history: Any) -> None:  # type: ignore[name-defined]
    """적자→흑자 전환 감지 (최근 1년 흑자, 전전년 적자)."""
    results = history.results  # 최신 first
    if len(results) < 2:
        return
    latest = results[0]
    prev = results[1]
    if latest.net_income_bn is None or prev.net_income_bn is None:
        return
    if latest.net_income_bn > 0 and prev.net_income_bn <= 0:
        result.signals.append(MispricingSignal(
            signal_type="turnaround",
            label="흑자 턴어라운드",
            strength=0.9,
            detail="전년 순이익 적자 → 최근 연도 흑자 전환",
        ))
    elif (
        len(results) >= 3
        and results[2].net_income_bn is not None
        and latest.net_income_bn > 0
        and prev.net_income_bn <= 0
        and results[2].net_income_bn <= 0
        and result.signals
    ):
        result.signals[-1].strength = 1.0
        result.signals[-1].label = "2년 연속 적자 → 흑자 전환"


def _check_op_rebound(result: MispricingResult, history: Any) -> None:  # type: ignore[name-defined]
    """영업이익 급반등 감지 (+50% 이상 또는 적자→흑자)."""
    results = history.results
    if len(results) < 2:
        return
    latest = results[0]
    prev = results[1]
    if latest.operating_income_bn is None or prev.operating_income_bn is None:
        return

    # 적자→흑자
    if latest.operating_income_bn > 0 and prev.operating_income_bn <= 0:
        result.signals.append(MispricingSignal(
            signal_type="op_rebound",
            label="영업이익 적자→흑자",
            strength=0.8,
            detail="전년 영업손실 → 흑자 전환",
        ))
        return

    # 급반등 +50%
    if prev.operating_income_bn > 0:
        chg = (latest.operating_income_bn - prev.operating_income_bn) / abs(prev.operating_income_bn)
        if chg >= 0.5:
            result.signals.append(MispricingSignal(
                signal_type="op_rebound",
                label=f"영업이익 급반등 +{chg*100:.0f}%",
                strength=min(chg * 0.6, 0.8),
                detail=f"영업이익 전년대비 +{chg*100:.0f}% 성장",
            ))


def _check_rev_acceleration(result: MispricingResult, history: Any) -> None:  # type: ignore[name-defined]
    """매출 성장 가속화 감지 (YoY 성장률 확대)."""
    results = history.results
    if len(results) < 2:
        return
    latest = results[0]
    prev = results[1]
    if latest.revenue_yoy_pct is None or prev.revenue_yoy_pct is None:
        return
    # 성장률 가속: 최신이 전년보다 10%p 이상 높고, 최신이 양수
    gap = latest.revenue_yoy_pct - prev.revenue_yoy_pct
    if latest.revenue_yoy_pct > 5 and gap > 10:
        result.signals.append(MispricingSignal(
            signal_type="rev_accel",
            label=f"매출 성장 가속 ({latest.revenue_yoy_pct:+.1f}%)",
            strength=min(gap / 50, 0.6),
            detail=f"매출 성장률 {prev.revenue_yoy_pct:+.1f}% → {latest.revenue_yoy_pct:+.1f}%로 확대",
        ))


def _check_beat_streak(result: MispricingResult, es: Any) -> None:  # type: ignore[name-defined]
    """EPS 연속 비트 감지 (3분기 이상 컨센서스 상회)."""
    if not es.quarters:
        return
    total = [q for q in es.quarters if q.surprise_pct is not None]
    if len(total) < 3:
        return
    # 최근 3분기 연속 비트
    recent3 = total[:3]
    recent_beats = [q for q in recent3 if q.surprise_pct is not None and q.surprise_pct > 0]
    if len(recent_beats) >= 3:
        avg_beat = sum(q.surprise_pct for q in recent_beats) / len(recent_beats)
        result.signals.append(MispricingSignal(
            signal_type="beat_streak",
            label=f"EPS 3분기 연속 비트 (평균 +{avg_beat:.1f}%)",
            strength=min(avg_beat / 20, 0.7),
            detail=f"최근 3분기 컨센서스 상회, 평균 +{avg_beat:.1f}%",
        ))


def _compute_score(result: MispricingResult) -> None:
    """시그널 강도 + 주가 미반응 가중치 → 최종 점수."""
    if not result.signals:
        result.conclusion = "해당없음"
        return

    # 기본 점수: 시그널 강도 합산
    base = sum(s.strength for s in result.signals) * 40

    # 주가 미반응 보너스
    price_bonus = 0.0
    if result.price_position_pct is not None and result.price_position_pct <= 40:
        # 52주 저점권 (하위 40%)
        price_bonus += (40 - result.price_position_pct) / 40 * 30
    if result.price_6m_chg_pct is not None and result.price_6m_chg_pct < 10:
        # 6개월 주가 상승 10% 미만
        price_bonus += max(0, (10 - result.price_6m_chg_pct) / 10) * 30

    result.total_score = min(base + price_bonus, 100)

    # 결론
    if result.total_score >= 70:
        result.conclusion = "강한괴리"
        result.summary = "실적 대비 주가 심한 저평가 가능성 — 시장 미반영 구간"
    elif result.total_score >= 45:
        result.conclusion = "괴리가능"
        result.summary = "실적 개선이 주가에 충분히 반영되지 않은 가능성"
    elif result.total_score >= 20:
        result.conclusion = "보통"
        result.summary = "실적-주가 일부 괴리 감지"
    else:
        result.conclusion = "해당없음"


def format_mispricing(result: MispricingResult) -> str:
    """MispricingResult → Telegram 출력 텍스트."""
    if not result.signals or result.conclusion == "해당없음":
        return ""

    icon = {"강한괴리": "🔥", "괴리가능": "⚡", "보통": "📊"}.get(result.conclusion, "📊")
    lines = [f"{icon} **실적-주가 괴리 분석** — {result.conclusion} ({result.total_score:.0f}점)"]

    for sig in result.signals:
        lines.append(f"  ✅ {sig.label}: {sig.detail}")

    context_parts = []
    if result.price_position_pct is not None:
        context_parts.append(f"52주위치 {result.price_position_pct:.0f}%")
    if result.price_6m_chg_pct is not None:
        sign = "+" if result.price_6m_chg_pct >= 0 else ""
        context_parts.append(f"6개월주가 {sign}{result.price_6m_chg_pct:.1f}%")
    if context_parts:
        lines.append(f"  📍 {' | '.join(context_parts)}")

    if result.summary:
        lines.append(f"  💡 {result.summary}")

    lines.append("  ※ 참고용 분석. 투자 판단 책임은 사용자에게 있음.")
    return "\n".join(lines)
