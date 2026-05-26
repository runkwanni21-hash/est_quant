"""모멘텀 신호 — RS, 거래량 서지, 52주 돌파, Short Squeeze DTC, 순현금.

공개 정보 기반 리서치 보조. 투자 판단 책임은 사용자에게 있음.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

log = logging.getLogger(__name__)

__all__ = [
    "MomentumSignals",
    "fetch_momentum_signals",
    "format_momentum_signals",
]


@dataclass
class MomentumSignals:
    symbol: str
    # Relative Strength vs SPY
    rs_1m_pct: float | None = None   # 1개월 초과수익률 (종목 - SPY)
    rs_3m_pct: float | None = None   # 3개월 초과수익률
    rs_label: str = ""               # "강함" / "중립" / "약함"
    # Volume
    vol_surge_ratio: float | None = None   # 최근 5D 평균 / 20D 평균
    vol_label: str = ""              # "급증" / "보통" / "감소"
    # 52-week breakout
    week52_high: float | None = None
    week52_low: float | None = None
    week52_pos_pct: float | None = None  # (현재가-52wLow)/(52wHigh-52wLow)*100
    is_breakout: bool = False        # 위치 >90% + 거래량 서지
    # Short squeeze
    dtc: float | None = None        # Days-to-Cover = sharesShort / adv10d
    dtc_label: str = ""             # "폭발위험" / "높음" / "보통" / "낮음"
    # Net cash
    net_cash_per_share: float | None = None   # (현금 - 총부채) / 발행주식
    net_cash_label: str = ""
    # Errors
    warnings: list[str] = field(default_factory=list)


def _rs_label(pct: float | None) -> str:
    if pct is None:
        return ""
    if pct >= 10:
        return "매우 강함"
    if pct >= 3:
        return "강함"
    if pct >= -3:
        return "중립"
    if pct >= -10:
        return "약함"
    return "매우 약함"


def _vol_label(ratio: float | None) -> str:
    if ratio is None:
        return ""
    if ratio >= 3.0:
        return "급증(3x↑)"
    if ratio >= 1.5:
        return "증가"
    if ratio >= 0.7:
        return "보통"
    return "감소"


def _dtc_label(dtc: float | None) -> str:
    if dtc is None:
        return ""
    if dtc >= 10:
        return "폭발위험(10일↑)"
    if dtc >= 5:
        return "높음(5-10일)"
    if dtc >= 2:
        return "보통(2-5일)"
    return "낮음(<2일)"


def fetch_momentum_signals(symbol: str, market: str = "") -> MomentumSignals:
    """yfinance + stock_data_provider 캐시로 모멘텀 신호 계산."""
    sig = MomentumSignals(symbol=symbol)

    try:
        import pandas as pd

        from tele_quant.stock_data_provider import get_ohlcv, get_ticker_info

        info = get_ticker_info(symbol)
        df = get_ohlcv(symbol, period="1y", interval="1d")

        if df is None or df.empty:
            sig.warnings.append("가격 데이터 없음")
            return sig

        close = df["Close"].dropna()
        if len(close) < 5:
            sig.warnings.append("데이터 부족(<5일)")
            return sig

        current = float(close.iloc[-1])

        # ── 52주 ─────────────────────────────────────────────────────────────
        sig.week52_high = float(close.max())
        sig.week52_low = float(close.min())
        rng = sig.week52_high - sig.week52_low
        if rng > 0:
            sig.week52_pos_pct = (current - sig.week52_low) / rng * 100

        # ── 거래량 서지 ───────────────────────────────────────────────────────
        if "Volume" in df.columns:
            vol = df["Volume"].dropna()
            if len(vol) >= 20:
                v5 = float(vol.iloc[-5:].mean()) if len(vol) >= 5 else None
                v20 = float(vol.iloc[-20:].mean())
                if v5 is not None and v20 > 0:
                    sig.vol_surge_ratio = v5 / v20
                    sig.vol_label = _vol_label(sig.vol_surge_ratio)

        # ── 52주 돌파 판정 ────────────────────────────────────────────────────
        if (
            sig.week52_pos_pct is not None
            and sig.week52_pos_pct >= 90
            and sig.vol_surge_ratio is not None
            and sig.vol_surge_ratio >= 1.5
        ):
            sig.is_breakout = True

        # ── 상대강도 vs SPY ───────────────────────────────────────────────────
        try:
            spy = get_ohlcv("SPY", period="3mo", interval="1d")
            if spy is not None and not spy.empty:
                spy_close = spy["Close"].dropna()

                def _ret(series: pd.Series, days: int) -> float | None:
                    if len(series) < days + 1:
                        return None
                    return (float(series.iloc[-1]) / float(series.iloc[-days]) - 1) * 100

                stock_1m = _ret(close, 21)
                spy_1m = _ret(spy_close, 21)
                stock_3m = _ret(close, 63)
                spy_3m = _ret(spy_close, 63)

                if stock_1m is not None and spy_1m is not None:
                    sig.rs_1m_pct = stock_1m - spy_1m
                if stock_3m is not None and spy_3m is not None:
                    sig.rs_3m_pct = stock_3m - spy_3m

                best_rs = sig.rs_3m_pct if sig.rs_3m_pct is not None else sig.rs_1m_pct
                sig.rs_label = _rs_label(best_rs)
        except Exception as exc:
            log.debug("[momentum] SPY RS 실패 %s: %s", symbol, exc)

        # ── Short Squeeze DTC ─────────────────────────────────────────────────
        shares_short = info.get("sharesShort")
        adv = info.get("averageVolume10days") or info.get("averageDailyVolume10Day")
        if shares_short and adv and adv > 0:
            sig.dtc = shares_short / adv
            sig.dtc_label = _dtc_label(sig.dtc)

        # ── 순현금 per share ──────────────────────────────────────────────────
        cash = info.get("totalCash")
        debt = info.get("totalDebt")
        shares = info.get("sharesOutstanding")
        if cash is not None and debt is not None and shares and shares > 0:
            sig.net_cash_per_share = (cash - debt) / shares
            if sig.net_cash_per_share > 0:
                sig.net_cash_label = "순현금 +"
            else:
                sig.net_cash_label = "순부채"

    except Exception as exc:
        log.debug("[momentum] fetch 실패 %s: %s", symbol, exc)
        sig.warnings.append(str(exc)[:60])

    return sig


def format_momentum_signals(sig: MomentumSignals) -> str:
    """MomentumSignals → Telegram 출력 문자열."""
    lines: list[str] = []

    # RS
    rs_parts: list[str] = []
    if sig.rs_1m_pct is not None:
        sign = "+" if sig.rs_1m_pct >= 0 else ""
        rs_parts.append(f"1M {sign}{sig.rs_1m_pct:.1f}%")
    if sig.rs_3m_pct is not None:
        sign = "+" if sig.rs_3m_pct >= 0 else ""
        rs_parts.append(f"3M {sign}{sig.rs_3m_pct:.1f}%")
    if rs_parts:
        label = f" ({sig.rs_label})" if sig.rs_label else ""
        lines.append(f"  상대강도(vs SPY): {' / '.join(rs_parts)}{label}")

    # 거래량
    if sig.vol_surge_ratio is not None:
        lines.append(f"  거래량 서지: {sig.vol_surge_ratio:.1f}x ({sig.vol_label})")

    # 52주
    if sig.week52_pos_pct is not None:
        w52 = f"  52주 위치: {sig.week52_pos_pct:.0f}%"
        if sig.is_breakout:
            w52 += " ⚡ 52주 신고가 돌파 시도"
        lines.append(w52)

    # Short Squeeze
    if sig.dtc is not None:
        lines.append(f"  Short DTC: {sig.dtc:.1f}일 ({sig.dtc_label})")

    # 순현금
    if sig.net_cash_per_share is not None:
        ncp = sig.net_cash_per_share
        lines.append(f"  순현금/주: ${ncp:.2f} ({sig.net_cash_label})")

    if not lines:
        return ""

    header = "⚡ 모멘텀 신호:"
    return header + "\n" + "\n".join(lines)
