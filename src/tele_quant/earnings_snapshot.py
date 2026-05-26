"""Earnings snapshot — 최근 실적/EPS/가이던스/다음 발표일 조회.

공개 정보 기반 리서치 보조. 투자 판단 책임은 사용자에게 있음.
데이터 미확인 시 숫자를 지어내지 않고 '확인 제한'으로 표시.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

log = logging.getLogger(__name__)

__all__ = [
    "EarningsSnapshot",
    "fetch_earnings_snapshot",
    "format_earnings_snapshot",
]


def _is_rate_limit_error(exc: BaseException) -> bool:
    text = f"{exc.__class__.__name__}: {exc}"
    return any(
        marker in text
        for marker in (
            "YFRateLimitError",
            "Too Many Requests",
            "Rate limited",
            "rate limit",
            "rate-limited",
        )
    )


@dataclass
class EarningsSnapshot:
    """최근 실적 + 다음 발표 정보."""

    symbol: str
    market: str = ""

    # 최근 실적
    last_report_date: str = ""           # YYYY-MM-DD
    eps_actual: float | None = None
    eps_estimate: float | None = None
    eps_surprise_pct: float | None = None
    revenue_actual_bn: float | None = None   # USD/KRW 10억 단위
    revenue_estimate_bn: float | None = None
    revenue_growth_yoy_pct: float | None = None
    guidance_direction: str = ""         # "raised" | "lowered" | "maintained" | ""

    # 다음 실적
    next_report_date: str = ""

    # 제한 사항
    data_limited: bool = False
    note: str = ""


def fetch_earnings_snapshot(symbol: str, market: str = "") -> EarningsSnapshot:
    """yfinance에서 실적/EPS 데이터를 조회한다."""
    snap = EarningsSnapshot(symbol=symbol, market=market)
    mkt = (market or "").upper()

    try:
        from tele_quant.stock_data_provider import (
            is_yfinance_rate_limited,
            yfinance_rate_limit_message,
        )

        if is_yfinance_rate_limited():
            snap.data_limited = True
            snap.note = yfinance_rate_limit_message()
            return snap

        import yfinance as yf
        ticker = yf.Ticker(symbol)
        info = ticker.info or {}

        # ── EPS (trailing/forward) ────────────────────────────────────────────
        eps_ttm = info.get("trailingEps")
        eps_fwd = info.get("forwardEps")
        if eps_ttm is not None:
            snap.eps_actual = float(eps_ttm)
        if eps_fwd is not None:
            snap.eps_estimate = float(eps_fwd)
            if eps_ttm and eps_ttm != 0:
                snap.eps_surprise_pct = (eps_fwd - eps_ttm) / abs(eps_ttm) * 100

        # ── Revenue ───────────────────────────────────────────────────────────
        rev = info.get("totalRevenue")
        rev_growth = info.get("revenueGrowth")
        if rev is not None:
            snap.revenue_actual_bn = rev / 1e9
        if rev_growth is not None:
            snap.revenue_growth_yoy_pct = rev_growth * 100

        # ── Next earnings date ────────────────────────────────────────────────
        try:
            cal = ticker.calendar
            if cal is not None and hasattr(cal, "get"):
                ed = cal.get("Earnings Date")
                if ed is not None:
                    if hasattr(ed, "__iter__") and not isinstance(ed, str):
                        dates = list(ed)
                        if dates:
                            snap.next_report_date = str(dates[0])[:10]
                    else:
                        snap.next_report_date = str(ed)[:10]
        except Exception as exc:
            log.debug("[earnings] calendar 조회 실패 %s: %s", symbol, exc)

        # ── KR 제한 안내 ─────────────────────────────────────────────────────
        if mkt == "KR":
            snap.data_limited = True
            snap.note = "KR 실적 데이터는 yfinance 기준 제한적. DART 공시 확인 권장."

    except Exception as exc:
        log.debug("[earnings] fetch 실패 %s: %s", symbol, exc)
        snap.data_limited = True
        snap.note = f"실적 데이터 조회 실패: {exc}"

        if _is_rate_limit_error(exc):
            from tele_quant.stock_data_provider import yfinance_rate_limit_message

            snap.note = yfinance_rate_limit_message()

    return snap


def format_earnings_snapshot(snap: EarningsSnapshot) -> str:
    """EarningsSnapshot → Telegram 출력 문자열."""
    lines = ["📊 실적 스냅샷:"]

    if snap.eps_actual is not None:
        lines.append(f"  • EPS(TTM): {snap.eps_actual:+.2f}")
    else:
        lines.append("  • EPS(TTM): 확인 제한")

    if snap.eps_estimate is not None:
        lines.append(f"  • EPS(Forward): {snap.eps_estimate:+.2f}")
        if snap.eps_surprise_pct is not None:
            lines.append(f"  • EPS 성장 추정: {snap.eps_surprise_pct:+.1f}%")

    if snap.revenue_actual_bn is not None:
        rev_str = f"${snap.revenue_actual_bn:.1f}B" if snap.market != "KR" else f"{snap.revenue_actual_bn:.1f}조"
        lines.append(f"  • 매출(TTM): {rev_str}")
    else:
        lines.append("  • 매출: 확인 제한")

    if snap.revenue_growth_yoy_pct is not None:
        lines.append(f"  • 매출성장(YoY): {snap.revenue_growth_yoy_pct:+.1f}%")

    if snap.guidance_direction:
        g_map = {"raised": "✅ 가이던스 상향", "lowered": "⚠ 가이던스 하향", "maintained": "— 가이던스 유지"}
        lines.append(f"  • 가이던스: {g_map.get(snap.guidance_direction, snap.guidance_direction)}")

    if snap.next_report_date:
        lines.append(f"  • 다음 실적 예정: {snap.next_report_date}")
    else:
        lines.append("  • 다음 실적일: 확인 제한")

    if snap.note:
        lines.append(f"  ※ {snap.note}")

    return "\n".join(lines)
