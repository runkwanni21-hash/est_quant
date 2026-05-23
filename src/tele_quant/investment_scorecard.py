"""투자 스코어카드 — 5차원 공격적 투자 적합도 점수.

5개 차원으로 종목의 단기 공격적 투자 적합도를 계산한다:
  기술모멘텀(25%) / 펀더멘탈(20%) / 성장가속도(25%) / 실적신뢰도(20%) / 밸류에이션(10%)

공개 정보 기반 리서치 보조. 투자 판단 책임은 사용자에게 있음.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

log = logging.getLogger(__name__)

__all__ = [
    "InvestmentScorecard",
    "build_scorecard",
    "format_scorecard",
]

_BAR_FILLED = "█"
_BAR_EMPTY = "░"
_BAR_LEN = 10


def _bar(score: float, max_score: float = 100.0) -> str:
    filled = round(_BAR_LEN * max(0.0, min(score, max_score)) / max_score)
    return _BAR_FILLED * filled + _BAR_EMPTY * (_BAR_LEN - filled)


@dataclass
class InvestmentScorecard:
    symbol: str
    # 차원별 점수 (0-100)
    momentum_score: float = 0.0      # 기술모멘텀 25%
    fundamental_score: float = 0.0   # 펀더멘탈 20%
    growth_score: float = 0.0        # 성장가속도 25%
    reliability_score: float = 0.0   # 실적신뢰도 20%
    valuation_score: float = 0.0     # 밸류에이션 10%
    # 종합
    total_score: float = 0.0
    tier: str = ""                   # STRONG_WATCH / WATCH / NEUTRAL / AVOID
    # 포인트
    bull_points: list[str] = field(default_factory=list)
    bear_points: list[str] = field(default_factory=list)


_WEIGHTS = {
    "momentum": 0.25,
    "fundamental": 0.20,
    "growth": 0.25,
    "reliability": 0.20,
    "valuation": 0.10,
}


def _tier(score: float) -> str:
    if score >= 75:
        return "STRONG_WATCH"
    if score >= 60:
        return "WATCH"
    if score >= 45:
        return "NEUTRAL"
    return "AVOID"


def build_scorecard(
    symbol: str,
    *,
    # 기술모멘텀 inputs
    rs_3m_pct: float | None = None,
    rs_1m_pct: float | None = None,
    vol_surge_ratio: float | None = None,
    week52_pos_pct: float | None = None,
    is_breakout: bool = False,
    dtc: float | None = None,
    # 펀더멘탈 inputs
    piotroski_score: int | None = None,
    roic: float | None = None,
    gross_margin: float | None = None,
    current_ratio: float | None = None,
    net_cash_positive: bool = False,
    # 성장가속도 inputs
    revenue_cagr_3y: float | None = None,
    earnings_growth: float | None = None,
    beat_rate_pct: float | None = None,
    avg_surprise_pct: float | None = None,
    surprise_trend: str = "",
    # 실적신뢰도 inputs
    piotroski_pass_count: int = 0,
    altman_z: float | None = None,
    institutional_pct: float | None = None,
    short_float_pct: float | None = None,
    # 밸류에이션 inputs
    peg_ratio: float | None = None,
    dcf_upside_pct: float | None = None,
    fcf_yield: float | None = None,
    analyst_target_upside: float | None = None,
) -> InvestmentScorecard:
    """각 차원별 0-100 점수 계산 → 가중합산."""
    sc = InvestmentScorecard(symbol=symbol)
    bull: list[str] = []
    bear: list[str] = []

    # ── 1. 기술모멘텀 (25%) ────────────────────────────────────────────────
    mom = 50.0  # base

    if rs_3m_pct is not None:
        if rs_3m_pct >= 20:
            mom += 20
            bull.append(f"3M RS +{rs_3m_pct:.0f}% (매우강)")
        elif rs_3m_pct >= 10:
            mom += 13
            bull.append(f"3M RS +{rs_3m_pct:.0f}%")
        elif rs_3m_pct >= 3:
            mom += 5
        elif rs_3m_pct <= -10:
            mom -= 15
            bear.append(f"3M RS {rs_3m_pct:.0f}% (SPY 대비 부진)")
        elif rs_3m_pct <= -3:
            mom -= 8

    if rs_1m_pct is not None and rs_3m_pct is None:
        mom += max(-10, min(15, rs_1m_pct * 0.8))

    if vol_surge_ratio is not None:
        if vol_surge_ratio >= 3.0:
            mom += 10
            bull.append(f"거래량 {vol_surge_ratio:.1f}x 급증")
        elif vol_surge_ratio >= 1.5:
            mom += 5
        elif vol_surge_ratio < 0.7:
            mom -= 5
            bear.append("거래량 감소")

    if week52_pos_pct is not None:
        if week52_pos_pct >= 90:
            mom += 8
        elif week52_pos_pct <= 10:
            mom -= 8
            bear.append("52주 저점 근처")

    if is_breakout:
        mom += 7
        bull.append("52주 신고가 돌파 시도")

    if dtc is not None and dtc >= 10:
        mom += 5
        bull.append(f"Short DTC {dtc:.1f}일 (스퀴즈 잠재)")

    sc.momentum_score = max(0.0, min(100.0, mom))

    # ── 2. 펀더멘탈 (20%) ────────────────────────────────────────────────
    fund = 50.0

    if piotroski_score is not None:
        if piotroski_score >= 7:
            fund += 20
            bull.append(f"Piotroski {piotroski_score}/9 (건전)")
        elif piotroski_score >= 5:
            fund += 8
        elif piotroski_score <= 2:
            fund -= 20
            bear.append(f"Piotroski {piotroski_score}/9 (취약)")
        elif piotroski_score <= 4:
            fund -= 8

    if roic is not None:
        if roic >= 20:
            fund += 12
            bull.append(f"ROIC {roic:.0f}%")
        elif roic >= 10:
            fund += 5
        elif roic < 0:
            fund -= 10
            bear.append(f"ROIC {roic:.0f}% (마이너스)")

    if gross_margin is not None:
        if gross_margin >= 60:
            fund += 8
            bull.append(f"매출총이익률 {gross_margin:.0f}%")
        elif gross_margin >= 40:
            fund += 3
        elif gross_margin < 15:
            fund -= 5

    if current_ratio is not None:
        if current_ratio >= 2.0:
            fund += 5
        elif current_ratio < 1.0:
            fund -= 8
            bear.append(f"유동비율 {current_ratio:.1f}x (유동성 부족)")

    if net_cash_positive:
        fund += 5
        bull.append("순현금 보유")

    sc.fundamental_score = max(0.0, min(100.0, fund))

    # ── 3. 성장가속도 (25%) ───────────────────────────────────────────────
    grow = 50.0

    if revenue_cagr_3y is not None:
        if revenue_cagr_3y >= 30:
            grow += 20
            bull.append(f"매출 CAGR {revenue_cagr_3y:.0f}%/yr")
        elif revenue_cagr_3y >= 15:
            grow += 10
            bull.append(f"매출 CAGR {revenue_cagr_3y:.0f}%/yr")
        elif revenue_cagr_3y >= 5:
            grow += 3
        elif revenue_cagr_3y < 0:
            grow -= 15
            bear.append(f"매출 3Y CAGR {revenue_cagr_3y:.0f}% (역성장)")

    if earnings_growth is not None:
        eg_pct = earnings_growth * 100 if abs(earnings_growth) <= 5 else earnings_growth
        if eg_pct >= 30:
            grow += 12
        elif eg_pct >= 15:
            grow += 6
        elif eg_pct < 0:
            grow -= 10
            bear.append("EPS 성장률 마이너스")

    if beat_rate_pct is not None:
        if beat_rate_pct >= 75:
            grow += 8
            bull.append(f"EPS 비트율 {beat_rate_pct:.0f}%")
        elif beat_rate_pct < 50:
            grow -= 5
            bear.append(f"EPS 비트율 {beat_rate_pct:.0f}%")

    if avg_surprise_pct is not None and avg_surprise_pct >= 5:
        grow += 5
        bull.append(f"평균 EPS 서프라이즈 +{avg_surprise_pct:.0f}%")

    if surprise_trend == "가속(↑)":
        grow += 5
        bull.append("EPS 서프라이즈 가속")
    elif surprise_trend == "둔화(↓)":
        grow -= 5
        bear.append("EPS 서프라이즈 둔화")

    sc.growth_score = max(0.0, min(100.0, grow))

    # ── 4. 실적신뢰도 (20%) ──────────────────────────────────────────────
    rel = 50.0

    if altman_z is not None:
        if altman_z >= 2.99:
            rel += 15
            bull.append(f"Altman Z {altman_z:.1f} (안전)")
        elif altman_z >= 1.81:
            rel += 5
        else:
            rel -= 20
            bear.append(f"Altman Z {altman_z:.1f} (위험)")

    if institutional_pct is not None:
        if institutional_pct >= 70:
            rel += 10
            bull.append(f"기관보유 {institutional_pct:.0f}%")
        elif institutional_pct >= 40:
            rel += 4
        elif institutional_pct < 10:
            rel -= 10
            bear.append(f"기관보유 {institutional_pct:.0f}% (낮음)")

    if short_float_pct is not None:
        if short_float_pct >= 20:
            rel -= 10
            bear.append(f"공매도 {short_float_pct:.0f}% (높음)")
        elif short_float_pct <= 5:
            rel += 5

    if piotroski_pass_count >= 8:
        rel += 5

    sc.reliability_score = max(0.0, min(100.0, rel))

    # ── 5. 밸류에이션 (10%) ──────────────────────────────────────────────
    val = 50.0

    if peg_ratio is not None and 0 < peg_ratio <= 100:
        if peg_ratio <= 1.0:
            val += 20
            bull.append(f"PEG {peg_ratio:.2f} (저평가)")
        elif peg_ratio <= 1.5:
            val += 10
        elif peg_ratio >= 3.0:
            val -= 15
            bear.append(f"PEG {peg_ratio:.1f} (고평가)")
        elif peg_ratio >= 2.0:
            val -= 5

    if dcf_upside_pct is not None:
        if dcf_upside_pct >= 20:
            val += 15
            bull.append(f"DCF 상승여력 +{dcf_upside_pct:.0f}%")
        elif dcf_upside_pct >= 5:
            val += 5
        elif dcf_upside_pct <= -20:
            val -= 15
            bear.append(f"DCF 대비 {dcf_upside_pct:.0f}% 고평가")

    if fcf_yield is not None:
        if fcf_yield >= 5:
            val += 10
            bull.append(f"FCF 수익률 {fcf_yield:.1f}%")
        elif fcf_yield >= 2:
            val += 4
        elif fcf_yield < 0:
            val -= 8
            bear.append("FCF 마이너스")

    if analyst_target_upside is not None:
        if analyst_target_upside >= 20:
            val += 5
        elif analyst_target_upside <= -10:
            val -= 5

    sc.valuation_score = max(0.0, min(100.0, val))

    # ── 종합 ─────────────────────────────────────────────────────────────
    sc.total_score = (
        sc.momentum_score * _WEIGHTS["momentum"]
        + sc.fundamental_score * _WEIGHTS["fundamental"]
        + sc.growth_score * _WEIGHTS["growth"]
        + sc.reliability_score * _WEIGHTS["reliability"]
        + sc.valuation_score * _WEIGHTS["valuation"]
    )
    sc.tier = _tier(sc.total_score)
    sc.bull_points = bull[:4]
    sc.bear_points = bear[:3]
    return sc


def format_scorecard(sc: InvestmentScorecard) -> str:
    """InvestmentScorecard → Telegram 출력 문자열."""
    if sc.total_score == 0 and not sc.bull_points and not sc.bear_points:
        return ""

    tier_emoji = {
        "STRONG_WATCH": "🔥",
        "WATCH": "👀",
        "NEUTRAL": "⚖️",
        "AVOID": "⛔",
    }.get(sc.tier, "")

    lines = [
        f"🏆 투자 스코어카드 [{tier_emoji} {sc.tier} | 종합 {sc.total_score:.0f}점]",
        f"  기술모멘텀  {_bar(sc.momentum_score)} {sc.momentum_score:.0f}점",
        f"  펀더멘탈    {_bar(sc.fundamental_score)} {sc.fundamental_score:.0f}점",
        f"  성장가속도  {_bar(sc.growth_score)} {sc.growth_score:.0f}점",
        f"  실적신뢰도  {_bar(sc.reliability_score)} {sc.reliability_score:.0f}점",
        f"  밸류에이션  {_bar(sc.valuation_score)} {sc.valuation_score:.0f}점",
    ]

    if sc.bull_points:
        lines.append("  📗 강점: " + " / ".join(sc.bull_points))
    if sc.bear_points:
        lines.append("  📕 위험: " + " / ".join(sc.bear_points))

    return "\n".join(lines)
