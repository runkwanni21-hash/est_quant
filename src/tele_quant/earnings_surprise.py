"""분기 EPS 실적 서프라이즈 분석 — yfinance earnings_history 기반.

4개 분기 비트율·평균 서프라이즈·트렌드를 계산한다.
공개 정보 기반 리서치 보조. 투자 판단 책임은 사용자에게 있음.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

log = logging.getLogger(__name__)

__all__ = [
    "EarningsSurprise",
    "QuarterlyBeat",
    "fetch_earnings_surprise",
    "format_earnings_surprise",
]


@dataclass
class QuarterlyBeat:
    quarter: str          # e.g. "2024Q4"
    eps_actual: float | None = None
    eps_estimate: float | None = None
    surprise_pct: float | None = None  # (actual - estimate) / |estimate| * 100
    beat: bool | None = None           # True=beat, False=miss, None=무데이터


@dataclass
class EarningsSurprise:
    symbol: str
    quarters: list[QuarterlyBeat] = field(default_factory=list)
    beat_rate_pct: float | None = None      # 비트한 분기 / 전체
    avg_surprise_pct: float | None = None   # 평균 서프라이즈 %
    trend: str = ""                          # "가속" / "안정" / "둔화" / "미확인"
    data_limited: bool = False
    note: str = ""


def _calc_trend(quarters: list[QuarterlyBeat]) -> str:
    """최근 4분기 서프라이즈 추세. 최신이 앞에 있다고 가정."""
    surprises = [q.surprise_pct for q in quarters if q.surprise_pct is not None]
    if len(surprises) < 3:
        return "미확인"
    # 최신 2개 평균 vs 이전 2개 평균
    recent = sum(surprises[:2]) / 2
    prior = sum(surprises[2:4]) / len(surprises[2:4])
    diff = recent - prior
    if diff >= 5:
        return "가속(↑)"
    if diff <= -5:
        return "둔화(↓)"
    return "안정(→)"


def fetch_earnings_surprise(symbol: str) -> EarningsSurprise:
    """yfinance earnings_history에서 최근 4분기 EPS 서프라이즈 계산."""
    es = EarningsSurprise(symbol=symbol)

    try:
        import pandas as pd

        from tele_quant.stock_data_provider import get_earnings_history

        df = get_earnings_history(symbol)

        if df is None or (isinstance(df, pd.DataFrame) and df.empty):
            es.data_limited = True
            es.note = "분기 EPS 데이터 없음"
            return es

        # yfinance earnings_history columns: Date, EPS Estimate, Reported EPS, Surprise(%)
        rows: list[QuarterlyBeat] = []
        for _, row in df.iterrows():
            try:
                date_val = row.get("Date") or row.name
                quarter = str(date_val)[:7] if date_val is not None else "?"

                actual_raw = row.get("Reported EPS") or row.get("epsActual")
                est_raw = row.get("EPS Estimate") or row.get("epsEstimate")
                surp_raw = row.get("Surprise(%)") or row.get("surprisePercent")

                actual = float(actual_raw) if actual_raw is not None and pd.notna(actual_raw) else None
                est = float(est_raw) if est_raw is not None and pd.notna(est_raw) else None

                surp: float | None = None
                if surp_raw is not None and pd.notna(surp_raw):
                    surp = float(surp_raw) * 100 if abs(float(surp_raw)) <= 1.0 else float(surp_raw)
                elif actual is not None and est is not None and est != 0:
                    surp = (actual - est) / abs(est) * 100

                beat: bool | None = None
                if surp is not None:
                    beat = surp >= 0

                rows.append(QuarterlyBeat(
                    quarter=quarter,
                    eps_actual=actual,
                    eps_estimate=est,
                    surprise_pct=surp,
                    beat=beat,
                ))
            except Exception:
                continue

        # 최신 4개 (earnings_history는 최신이 마지막 행)
        rows = list(reversed(rows))[:4]
        es.quarters = rows

        beats = [q for q in rows if q.beat is True]
        total_scored = [q for q in rows if q.beat is not None]
        if total_scored:
            es.beat_rate_pct = len(beats) / len(total_scored) * 100

        surprises = [q.surprise_pct for q in rows if q.surprise_pct is not None]
        if surprises:
            es.avg_surprise_pct = sum(surprises) / len(surprises)

        es.trend = _calc_trend(rows)

    except Exception as exc:
        log.debug("[earnings_surprise] fetch 실패 %s: %s", symbol, exc)
        es.data_limited = True
        es.note = f"EPS 서프라이즈 조회 실패: {exc}"

    return es


def format_earnings_surprise(es: EarningsSurprise, market: str = "US") -> str:
    """EarningsSurprise → Telegram 출력 문자열."""
    if not es.quarters and not es.note:
        return ""

    is_kr = market.upper() == "KR"
    lines: list[str] = ["📊 분기 EPS 서프라이즈 (최근 4분기):"]

    for q in es.quarters[:4]:
        beat_str = "✅" if q.beat is True else ("❌" if q.beat is False else "•")
        parts = [f"  {beat_str} {q.quarter}"]
        if q.eps_actual is not None:
            parts.append(f"실적 {q.eps_actual:,.0f}원" if is_kr else f"실적 ${q.eps_actual:.2f}")
        if q.eps_estimate is not None:
            parts.append(f"예상 {q.eps_estimate:,.0f}원" if is_kr else f"예상 ${q.eps_estimate:.2f}")
        if q.surprise_pct is not None:
            sign = "+" if q.surprise_pct >= 0 else ""
            parts.append(f"{sign}{q.surprise_pct:.1f}%")
        lines.append(" | ".join(parts))

    summary_parts: list[str] = []
    if es.beat_rate_pct is not None:
        summary_parts.append(f"비트율 {es.beat_rate_pct:.0f}%")
    if es.avg_surprise_pct is not None:
        sign = "+" if es.avg_surprise_pct >= 0 else ""
        summary_parts.append(f"평균서프라이즈 {sign}{es.avg_surprise_pct:.1f}%")
    if es.trend:
        summary_parts.append(f"트렌드 {es.trend}")
    if summary_parts:
        lines.append("  → " + " | ".join(summary_parts))

    if es.note:
        lines.append(f"  ※ {es.note}")

    return "\n".join(lines)
