"""간이 2-Stage DCF 추정 — Forward EPS + 성장률 + CAPM 할인율.

주의: 가정(성장률·할인율·터미널 배수)에 극도로 민감한 추정치.
확정 내재 가치가 아님. 공개 정보 기반 리서치 보조.
투자 판단 책임은 사용자에게 있음.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

log = logging.getLogger(__name__)

__all__ = [
    "DCFResult",
    "estimate_dcf",
    "format_dcf",
]

_RISK_FREE: float = 0.045   # 10Y 미 국채 근사치 (4.5%)
_EQ_PREMIUM: float = 0.050  # 주식 위험 프리미엄 (5%)
_TERMINAL_PE: float = 20.0  # 터미널 P/E (성숙 기업 평균)


@dataclass
class DCFResult:
    intrinsic_value: float | None = None
    current_price: float | None = None
    upside_pct: float | None = None       # %: 양수=상승 여력, 음수=고평가
    base_eps: float | None = None
    growth_rate_1: float = 0.0            # Stage 1 성장률 (5년)
    growth_rate_2: float = 0.0            # Stage 2 성장률 (5~10년)
    discount_rate: float = 0.0
    beta: float = 1.0
    assumptions: str = ""


def estimate_dcf(symbol: str, market: str = "") -> DCFResult:
    """2-Stage DCF 추정.

    Stage 1 (년 1~5):  base_eps x (1+g1)^t 의 현재가치 합산
    Stage 2 (년 6~10): stage1 말기 EPS x (1+g2)^t 의 현재가치 합산
    Terminal Value:    EPS_10 x (1+g2) x terminal_PE / (1+r)^10
    할인율(r):          CAPM = risk_free + beta x equity_premium
    """
    res = DCFResult()

    try:
        from tele_quant.stock_data_provider import get_ticker_info

        info = get_ticker_info(symbol)

        # Base EPS: Forward 우선, 없으면 TTM
        eps_raw = info.get("forwardEps") or info.get("trailingEps")
        if not eps_raw or float(eps_raw) <= 0:
            return res  # EPS 없으면 DCF 불가
        base_eps = float(eps_raw)
        res.base_eps = base_eps

        # Stage 1 성장률: earningsGrowth → revenueGrowth → 10% fallback
        eg = info.get("earningsGrowth")
        rg = info.get("revenueGrowth")
        if eg and float(eg) > 0:
            g1 = min(max(float(eg), 0.02), 0.45)
        elif rg and float(rg) > 0:
            g1 = min(max(float(rg), 0.02), 0.30)
        else:
            g1 = 0.10

        # Stage 2: g1의 절반 (최소 2%)
        g2 = max(g1 / 2.0, 0.02)

        res.growth_rate_1 = g1
        res.growth_rate_2 = g2

        # 할인율 (CAPM)
        beta = float(info.get("beta") or 1.0)
        beta = min(max(beta, 0.3), 3.0)
        res.beta = beta
        r = _RISK_FREE + beta * _EQ_PREMIUM
        res.discount_rate = r

        # DCF 계산
        pv = 0.0
        eps_t = base_eps

        for t in range(1, 6):
            eps_t *= (1.0 + g1)
            pv += eps_t / (1.0 + r) ** t

        for t in range(6, 11):
            eps_t *= (1.0 + g2)
            pv += eps_t / (1.0 + r) ** t

        tv = eps_t * (1.0 + g2) * _TERMINAL_PE / (1.0 + r) ** 10
        pv += tv

        res.intrinsic_value = round(pv, 2)

        cp = (
            info.get("currentPrice")
            or info.get("regularMarketPrice")
            or info.get("previousClose")
        )
        if cp and float(cp) > 0:
            res.current_price = float(cp)
            res.upside_pct = round((pv - float(cp)) / float(cp) * 100, 1)

        res.assumptions = (
            f"EPS {base_eps:+.2f} / 성장 {g1 * 100:.0f}%→{g2 * 100:.0f}% / "
            f"할인율 {r * 100:.1f}% (β={beta:.1f}) / 터미널P/E {_TERMINAL_PE:.0f}x"
        )

    except Exception as exc:
        log.debug("[dcf_estimator] 실패 %s: %s", symbol, exc)

    return res


def format_dcf(result: DCFResult, market: str = "") -> str:
    """DCFResult → Telegram 출력 문자열."""
    if result.intrinsic_value is None:
        return ""

    is_kr = market.upper() == "KR"
    sym = "₩" if is_kr else "$"

    lines = ["💰 간이 DCF 추정 (참고용):"]
    lines.append(f"  내재가치 추정: {sym}{result.intrinsic_value:,.2f}")

    if result.upside_pct is not None:
        if result.upside_pct >= 0:
            lines.append(f"  📈 상승 여력: +{result.upside_pct:.1f}%")
        else:
            lines.append(f"  📉 고평가 여지: {result.upside_pct:.1f}%")

    if result.assumptions:
        lines.append(f"  가정: {result.assumptions}")

    lines.append("  ⚠ 가정에 극도로 민감 — 확정 가치 아님, 참고만 사용")

    return "\n".join(lines)
