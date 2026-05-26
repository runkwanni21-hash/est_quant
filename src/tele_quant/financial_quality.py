"""재무 품질 지표 — Piotroski F-Score, Altman Z-Score, ROIC, 유동성.

공개 정보 기반 리서치 보조. 투자 판단 책임은 사용자에게 있음.
데이터 부족 시 해당 지표를 None으로 반환하며 추측하지 않는다.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger(__name__)

__all__ = [
    "FinancialQuality",
    "fetch_financial_quality",
    "format_financial_quality",
]


# ── Data model ────────────────────────────────────────────────────────────────


@dataclass
class FinancialQuality:
    symbol: str

    # Piotroski F-Score (0~9)
    piotroski_score: int | None = None
    piotroski_signals: list[str] = field(default_factory=list)
    piotroski_failed: list[str] = field(default_factory=list)

    # Altman Z-Score
    altman_z: float | None = None
    altman_zone: str = ""  # 안전(Safe) / 회색(Grey) / 위험(Distress)

    # ROIC
    roic: float | None = None  # %

    # Revenue CAGR
    revenue_cagr_3y: float | None = None  # %

    # 시장 포지션
    short_float_pct: float | None = None    # %
    insider_pct: float | None = None        # %
    institutional_pct: float | None = None  # %

    # 유동성
    avg_volume_10d: float | None = None
    liquidity_grade: str = ""

    data_limited: bool = False
    note: str = ""


# ── 내부 헬퍼 ─────────────────────────────────────────────────────────────────


def _sf(val: Any) -> float | None:
    """안전한 float 변환. NaN/None 시 None."""
    try:
        if val is None:
            return None
        f = float(val)
        return None if f != f else f  # NaN guard
    except Exception:
        return None


def _row(df: Any, *names: str, col: int = 0) -> float | None:
    """DataFrame에서 여러 행 이름 시도 → 지정 컬럼(최신=0, 전년=1)의 값."""
    try:
        import pandas as pd

        if df is None or (isinstance(df, pd.DataFrame) and df.empty):
            return None
        if len(df.columns) <= col:
            return None
        c = df.columns[col]
        for name in names:
            if name in df.index:
                v = df.loc[name, c]
                if pd.notna(v):
                    return float(v)
    except Exception:
        pass
    return None


def _cur(df: Any, *names: str) -> float | None:
    return _row(df, *names, col=0)


def _prv(df: Any, *names: str) -> float | None:
    return _row(df, *names, col=1)


# ── Piotroski F-Score ─────────────────────────────────────────────────────────


def _piotroski(
    income: Any,
    balance: Any,
    cashflow: Any,
    info: dict[str, Any],
) -> tuple[int, list[str], list[str]]:
    """9점 Piotroski F-Score. 데이터 없는 항목은 0점 처리."""
    score = 0
    ok: list[str] = []
    fail: list[str] = []

    def _chk(name: str, cond: bool | None) -> None:
        nonlocal score
        if cond is True:
            score += 1
            ok.append(name)
        elif cond is False:
            fail.append(name)

    # ── 수익성 (4) ────────────────────────────────────────────────────────────
    ta = _cur(balance, "Total Assets")
    net = _cur(income, "Net Income", "Net Income Common Stockholders")
    roa = (net / ta) if (net is not None and ta and ta > 0) else None
    _chk("ROA>0", roa > 0 if roa is not None else None)

    ocf = _cur(cashflow, "Operating Cash Flow", "Cash Flows From Operations",
               "Operating Activities")
    _chk("영업현금흐름>0", ocf > 0 if ocf is not None else None)

    ta_p = _prv(balance, "Total Assets")
    net_p = _prv(income, "Net Income", "Net Income Common Stockholders")
    roa_p = (net_p / ta_p) if (net_p is not None and ta_p and ta_p > 0) else None
    _chk("ROA 개선", (roa > roa_p) if (roa is not None and roa_p is not None) else None)

    if net is not None and ocf is not None and ta and ta > 0:
        accruals = (net - ocf) / ta
        _chk("발생액<0(현금질)", accruals < 0)
    else:
        _chk("발생액<0(현금질)", None)

    # ── 레버리지/유동성 (3) ────────────────────────────────────────────────────
    ltd = _cur(balance, "Long Term Debt", "Long-Term Debt", "LongTermDebt")
    ltd_p = _prv(balance, "Long Term Debt", "Long-Term Debt", "LongTermDebt")
    lev = (ltd / ta) if (ltd is not None and ta and ta > 0) else None
    lev_p = (ltd_p / ta_p) if (ltd_p is not None and ta_p and ta_p > 0) else None
    _chk("레버리지 감소", (lev < lev_p) if (lev is not None and lev_p is not None) else None)

    ca = _cur(balance, "Current Assets")
    cl = _cur(balance, "Current Liabilities")
    ca_p = _prv(balance, "Current Assets")
    cl_p = _prv(balance, "Current Liabilities")
    cr = (ca / cl) if (ca and cl and cl > 0) else None
    cr_p = (ca_p / cl_p) if (ca_p and cl_p and cl_p > 0) else None
    _chk("유동비율 개선", (cr > cr_p) if (cr is not None and cr_p is not None) else None)

    # 주식 희석 여부: Diluted Average Shares 비교
    sh = _cur(income, "Diluted Average Shares", "Basic Average Shares", "Ordinary Shares Number")
    sh_p = _prv(income, "Diluted Average Shares", "Basic Average Shares", "Ordinary Shares Number")
    _chk("주식 미희석", (sh <= sh_p) if (sh is not None and sh_p is not None) else None)

    # ── 효율성 (2) ────────────────────────────────────────────────────────────
    rev = _cur(income, "Total Revenue")
    rev_p = _prv(income, "Total Revenue")
    gp = _cur(income, "Gross Profit")
    gp_p = _prv(income, "Gross Profit")
    gm = (gp / rev) if (gp is not None and rev and rev > 0) else None
    gm_p = (gp_p / rev_p) if (gp_p is not None and rev_p and rev_p > 0) else None
    _chk("매출총이익률 개선", (gm > gm_p) if (gm is not None and gm_p is not None) else None)

    at = (rev / ta) if (rev and ta and ta > 0) else None
    at_p = (rev_p / ta_p) if (rev_p and ta_p and ta_p > 0) else None
    _chk("자산회전율 개선", (at > at_p) if (at is not None and at_p is not None) else None)

    return score, ok, fail


# ── Altman Z-Score ────────────────────────────────────────────────────────────


def _altman_z(
    income: Any, balance: Any, info: dict[str, Any]
) -> tuple[float | None, str]:
    """Altman Z-Score (상장사 버전).

    Z = 1.2*(WC/TA) + 1.4*(RE/TA) + 3.3*(EBIT/TA) + 0.6*(ME/TL) + 1.0*(S/TA)
    """
    ta = _cur(balance, "Total Assets")
    if not ta or ta <= 0:
        return None, ""

    ca = _cur(balance, "Current Assets") or 0.0
    cl = _cur(balance, "Current Liabilities") or 0.0
    wc = ca - cl

    re = _cur(balance, "Retained Earnings", "RetainedEarnings") or 0.0

    ebit = (
        _cur(income, "Operating Income", "EBIT", "Ebit")
        or 0.0
    )

    me = _sf(info.get("marketCap")) or 0.0

    te = (
        _cur(balance,
             "Stockholders Equity",
             "Total Stockholder Equity",
             "Total Equity Gross Minority Interest",
             "Stockholders' Equity")
        or 0.0
    )
    tl = ta - te if te else ta

    rev = _cur(income, "Total Revenue") or 0.0

    try:
        z = (
            1.2 * (wc / ta)
            + 1.4 * (re / ta)
            + 3.3 * (ebit / ta)
            + 0.6 * (me / tl if tl > 0 else 0.0)
            + 1.0 * (rev / ta)
        )
    except ZeroDivisionError:
        return None, ""

    if z > 2.99:
        zone = "안전 (Z>2.99)"
    elif z > 1.81:
        zone = "회색 (1.81~2.99)"
    else:
        zone = "위험 (<1.81)"

    return round(z, 2), zone


# ── ROIC ─────────────────────────────────────────────────────────────────────


def _roic(income: Any, balance: Any, info: dict[str, Any]) -> float | None:
    """ROIC = NOPAT / Invested Capital (%)."""
    op_inc = _cur(income, "Operating Income", "EBIT", "Ebit")
    if op_inc is None:
        return None

    tax = _sf(info.get("effectiveTaxRate")) or 0.21
    nopat = op_inc * (1.0 - max(min(tax, 0.50), 0.0))

    te = _cur(
        balance,
        "Stockholders Equity",
        "Total Stockholder Equity",
        "Total Equity Gross Minority Interest",
    )
    if te is None:
        return None

    ltd = _cur(balance, "Long Term Debt", "Long-Term Debt", "LongTermDebt") or 0.0
    cash = (
        _cur(balance, "Cash And Cash Equivalents", "Cash", "CashAndCashEquivalents")
        or 0.0
    )

    invested = te + ltd - cash
    if invested <= 0:
        return None

    return round(nopat / invested * 100, 1)


# ── Revenue CAGR ──────────────────────────────────────────────────────────────


def _revenue_cagr(income: Any, years: int = 3) -> float | None:
    try:
        import pandas as pd

        if income is None or (isinstance(income, pd.DataFrame) and income.empty):
            return None
        if "Total Revenue" not in income.index:
            return None
        revs = income.loc["Total Revenue"].dropna()
        if len(revs) < years + 1:
            return None
        rev_new = float(revs.iloc[0])
        rev_old = float(revs.iloc[years])
        if rev_old <= 0 or rev_new <= 0:
            return None
        return round(((rev_new / rev_old) ** (1.0 / years) - 1) * 100, 1)
    except Exception:
        return None


# ── Liquidity ─────────────────────────────────────────────────────────────────


def _liquidity_grade(avg_vol: float | None) -> str:
    if avg_vol is None:
        return "미확인"
    if avg_vol >= 5_000_000:
        return "높음"
    if avg_vol >= 500_000:
        return "중간"
    if avg_vol >= 50_000:
        return "낮음"
    return "매우 낮음"


# ── Public API ────────────────────────────────────────────────────────────────


def fetch_financial_quality(symbol: str, market: str = "") -> FinancialQuality:
    """Piotroski, Altman Z, ROIC, 매출 CAGR, 지분율, 유동성 종합 조회."""
    fq = FinancialQuality(symbol=symbol)

    try:
        from tele_quant.stock_data_provider import (
            get_balance_sheet,
            get_cashflow,
            get_income_stmt,
            get_ticker_info,
        )

        info = get_ticker_info(symbol)
        income = get_income_stmt(symbol)
        balance = get_balance_sheet(symbol)
        cashflow = get_cashflow(symbol)

        # ── Piotroski ───────────────────────────────────────────────────────
        try:
            fq.piotroski_score, fq.piotroski_signals, fq.piotroski_failed = _piotroski(
                income, balance, cashflow, info
            )
        except Exception as exc:
            log.debug("[financial_quality] Piotroski 실패 %s: %s", symbol, exc)

        # ── Altman Z ────────────────────────────────────────────────────────
        try:
            fq.altman_z, fq.altman_zone = _altman_z(income, balance, info)
        except Exception as exc:
            log.debug("[financial_quality] Altman Z 실패 %s: %s", symbol, exc)

        # ── ROIC ────────────────────────────────────────────────────────────
        try:
            fq.roic = _roic(income, balance, info)
        except Exception as exc:
            log.debug("[financial_quality] ROIC 실패 %s: %s", symbol, exc)

        # ── Revenue CAGR ─────────────────────────────────────────────────────
        try:
            fq.revenue_cagr_3y = _revenue_cagr(income, years=3)
        except Exception as exc:
            log.debug("[financial_quality] CAGR 실패 %s: %s", symbol, exc)

        # ── 지분율 ───────────────────────────────────────────────────────────
        sf = info.get("shortPercentOfFloat")
        fq.short_float_pct = float(sf) * 100 if sf else None

        ins = info.get("heldPercentInsiders")
        fq.insider_pct = float(ins) * 100 if ins else None

        inst = info.get("heldPercentInstitutions")
        fq.institutional_pct = float(inst) * 100 if inst else None

        # ── 유동성 ──────────────────────────────────────────────────────────
        avg_vol = info.get("averageVolume10days") or info.get("averageDailyVolume10Day")
        fq.avg_volume_10d = float(avg_vol) if avg_vol else None
        fq.liquidity_grade = _liquidity_grade(fq.avg_volume_10d)

        if market.upper() == "KR":
            fq.note = "KR 재무제표는 yfinance 기준 제한적. 참고용 수치."

    except Exception as exc:
        log.debug("[financial_quality] fetch 실패 %s: %s", symbol, exc)
        fq.data_limited = True

    return fq


def format_financial_quality(fq: FinancialQuality) -> str:
    """FinancialQuality → Telegram 출력."""
    has_any = (
        fq.piotroski_score is not None
        or fq.altman_z is not None
        or fq.roic is not None
        or fq.revenue_cagr_3y is not None
        or fq.short_float_pct is not None
    )
    if not has_any:
        return ""

    lines: list[str] = ["🏦 재무 품질 분석:"]

    # Piotroski
    if fq.piotroski_score is not None:
        p = fq.piotroski_score
        icon = "✅" if p >= 7 else ("⚡" if p >= 4 else "⚠")
        label = "강함" if p >= 7 else ("보통" if p >= 4 else "약함")
        lines.append(f"  {icon} Piotroski F-Score: {p}/9 ({label})")
        if fq.piotroski_failed:
            lines.append(f"    미충족: {' · '.join(fq.piotroski_failed[:4])}")

    # Altman Z
    if fq.altman_z is not None:
        icon = "✅" if fq.altman_z > 2.99 else ("⚡" if fq.altman_z > 1.81 else "🚨")
        lines.append(f"  {icon} Altman Z: {fq.altman_z:.2f} ({fq.altman_zone})")

    # ROIC
    if fq.roic is not None:
        icon = "✅" if fq.roic > 15 else ("⚡" if fq.roic > 8 else "⚠")
        lines.append(f"  {icon} ROIC: {fq.roic:.1f}%")

    # Revenue CAGR
    if fq.revenue_cagr_3y is not None:
        sign = "+" if fq.revenue_cagr_3y >= 0 else ""
        icon = "📈" if fq.revenue_cagr_3y > 5 else "📉"
        lines.append(f"  {icon} 매출 CAGR (3Y): {sign}{fq.revenue_cagr_3y:.1f}%")

    # 지분
    pos: list[str] = []
    if fq.short_float_pct is not None:
        pos.append(f"공매도 {fq.short_float_pct:.1f}%")
    if fq.insider_pct is not None:
        pos.append(f"내부자 {fq.insider_pct:.1f}%")
    if fq.institutional_pct is not None:
        pos.append(f"기관 {fq.institutional_pct:.1f}%")
    if pos:
        lines.append(f"  📊 지분: {' | '.join(pos)}")

    # 유동성
    if fq.liquidity_grade:
        vol_str = ""
        if fq.avg_volume_10d:
            if fq.avg_volume_10d >= 1_000_000:
                vol_str = f" (ADV {fq.avg_volume_10d / 1_000_000:.1f}M주)"
            else:
                vol_str = f" (ADV {fq.avg_volume_10d / 1_000:.0f}K주)"
        lines.append(f"  💧 유동성: {fq.liquidity_grade}{vol_str}")

    if fq.note:
        lines.append(f"  ※ {fq.note}")

    return "\n".join(lines)
