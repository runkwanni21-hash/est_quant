"""연간 실적 히스토리 — yfinance income_stmt 기반 최근 5년.

공개 정보 기반 리서치 보조. 투자 판단 책임은 사용자에게 있음.
데이터 미확인 시 숫자를 지어내지 않고 '확인 제한'으로 표시.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger(__name__)

__all__ = [
    "AnnualResult",
    "EarningsHistory",
    "fetch_earnings_history",
    "format_earnings_history",
]


@dataclass
class AnnualResult:
    """단일 연도 실적 요약."""

    year: int
    revenue_bn: float | None = None        # 매출 10억 단위 (USD B / KRW 조)
    revenue_yoy_pct: float | None = None   # 전년 대비 매출 성장률 %
    operating_income_bn: float | None = None
    net_income_bn: float | None = None
    op_margin_pct: float | None = None     # 영업이익률 %


@dataclass
class EarningsHistory:
    """최근 5년 연간 실적 묶음."""

    symbol: str
    market: str = ""
    currency: str = "USD"
    results: list[AnnualResult] = field(default_factory=list)
    data_limited: bool = False
    note: str = ""


def fetch_earnings_history(symbol: str, market: str = "", years: int = 5) -> EarningsHistory:
    """yfinance income_stmt에서 최대 `years`년 연간 실적 조회.

    결과는 최신 연도가 앞(results[0])에 온다.
    """
    h = EarningsHistory(symbol=symbol, market=market)
    mkt = (market or "").upper()
    if mkt == "KR":
        h.currency = "KRW"

    try:
        import pandas as pd

        from tele_quant.stock_data_provider import get_income_stmt

        stmt = get_income_stmt(symbol)

        if stmt is None or (isinstance(stmt, pd.DataFrame) and stmt.empty):
            h.data_limited = True
            h.note = "연간 실적 데이터 없음"
            return h

        cols: list[Any] = list(stmt.columns)[:years]  # 최신→과거 순

        _REV = "Total Revenue"
        _OP = "Operating Income"
        _NET = "Net Income"

        def _val(row: str, col: Any) -> float | None:
            try:
                if row in stmt.index:
                    v = stmt.loc[row, col]
                    if pd.notna(v):
                        return float(v)
            except Exception:
                pass
            return None

        prev_rev_bn: float | None = None
        ordered: list[AnnualResult] = []

        for col in reversed(cols):  # 과거→현재 순으로 YoY 계산
            year = int(str(col)[:4])
            rev = _val(_REV, col)
            op_inc = _val(_OP, col)
            net = _val(_NET, col)

            rev_bn = rev / 1e9 if rev is not None else None
            op_bn = op_inc / 1e9 if op_inc is not None else None
            net_bn = net / 1e9 if net is not None else None

            yoy: float | None = None
            if rev_bn is not None and prev_rev_bn and prev_rev_bn != 0:
                yoy = (rev_bn - prev_rev_bn) / abs(prev_rev_bn) * 100

            op_margin: float | None = None
            if rev and rev != 0 and op_inc is not None:
                op_margin = op_inc / rev * 100

            ordered.append(AnnualResult(
                year=year,
                revenue_bn=rev_bn,
                revenue_yoy_pct=yoy,
                operating_income_bn=op_bn,
                net_income_bn=net_bn,
                op_margin_pct=op_margin,
            ))
            prev_rev_bn = rev_bn

        h.results = list(reversed(ordered))  # 최신 연도 먼저

        if mkt == "KR":
            h.note = "KR 연간 실적은 yfinance 기준 제한적. DART 공시 확인 권장."

    except Exception as exc:
        log.debug("[earnings_history] fetch 실패 %s: %s", symbol, exc)
        h.data_limited = True
        h.note = f"연간 실적 데이터 조회 실패: {exc}"

    return h


def format_earnings_history(h: EarningsHistory) -> str:
    """EarningsHistory → Telegram 출력 문자열."""
    if not h.results:
        return ""

    is_kr = h.currency == "KRW"
    lines = ["📈 연간 실적 (최근 5년):"]

    for r in h.results[:5]:
        parts: list[str] = [f"  {r.year}년"]

        if r.revenue_bn is not None:
            rev_str = f"{r.revenue_bn:.1f}조" if is_kr else f"${r.revenue_bn:.1f}B"
            if r.revenue_yoy_pct is not None:
                sign = "+" if r.revenue_yoy_pct >= 0 else ""
                parts.append(f"매출 {rev_str}({sign}{r.revenue_yoy_pct:.1f}%)")
            else:
                parts.append(f"매출 {rev_str}")

        if r.op_margin_pct is not None:
            parts.append(f"OPM {r.op_margin_pct:.1f}%")

        if r.net_income_bn is not None:
            net_str = f"{r.net_income_bn:.1f}조" if is_kr else f"${r.net_income_bn:.1f}B"
            parts.append(f"순익 {net_str}")

        if len(parts) > 1:  # 연도 외 데이터 있을 때만 출력
            lines.append(" | ".join(parts))

    if h.note:
        lines.append(f"  ※ {h.note}")

    return "\n".join(lines)
