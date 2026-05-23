"""Institutional Flow Analysis — 기관/외국인 수급 분석.

오픈소스/무료 데이터 우선:
- pykrx → KRX 기관/외국인 순매수 (KR 종목)
- yfinance/FDR fallback
- 거래대금/거래량/OBV proxy

'기관 매집 확정' 금지. '수급집중 가능성 HIGH/MEDIUM/LOW'로 표현.
공개 정보 기반 리서치 보조. 투자 판단 책임은 사용자에게 있음.
"""

from __future__ import annotations

import contextlib
import io
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tele_quant.analysis.report_models import InstitutionalFlowSignal

log = logging.getLogger(__name__)


# ── pykrx 기관/외국인 순매수 ────────────────────────────────────────────────


def _fetch_krx_flow(symbol: str, days: int = 20) -> dict:
    """pykrx로 기관/외국인 순매수 수집. 실패 시 빈 dict 반환."""
    result: dict = {
        "inst_net_5d": None, "inst_net_20d": None,
        "foreign_net_5d": None, "foreign_net_20d": None,
        "inst_consecutive_buy": 0, "inst_consecutive_sell": 0,
        "foreign_consecutive_buy": 0,
    }
    # KR 종목만 (6자리.KS/.KQ)
    bare = symbol.split(".")[0]
    if not bare.isdigit():
        return result
    try:
        from datetime import date, timedelta

        _sink = io.StringIO()
        with contextlib.redirect_stdout(_sink):
            from pykrx import stock  # type: ignore[import-untyped]

        end_dt = date.today()
        start_dt = end_dt - timedelta(days=days + 10)
        end_str = end_dt.strftime("%Y%m%d")
        start_str = start_dt.strftime("%Y%m%d")

        with contextlib.redirect_stdout(_sink):
            df = stock.get_market_trading_value_by_date(start_str, end_str, bare)
        if df is None or df.empty:
            return result

        # 기관순매수: 기관합계 컬럼 추출 (컬럼명이 버전마다 다를 수 있음)
        inst_col = None
        foreign_col = None
        for col in df.columns:
            c = str(col)
            if "기관" in c and "합계" in c:
                inst_col = col
            if "외국인" in c:
                foreign_col = col

        if inst_col is not None:
            recent = df[inst_col].dropna()
            if len(recent) >= 5:
                result["inst_net_5d"] = float(recent.iloc[-5:].sum()) / 1e8  # 억원
            if len(recent) >= 20:
                result["inst_net_20d"] = float(recent.iloc[-20:].sum()) / 1e8

            # 연속 순매수/매도
            consec_buy = 0
            consec_sell = 0
            for v in reversed(recent.tolist()):
                if v > 0:
                    if consec_sell > 0:
                        break
                    consec_buy += 1
                elif v < 0:
                    if consec_buy > 0:
                        break
                    consec_sell += 1
                else:
                    break
            result["inst_consecutive_buy"] = consec_buy
            result["inst_consecutive_sell"] = consec_sell

        if foreign_col is not None:
            recent_f = df[foreign_col].dropna()
            if len(recent_f) >= 5:
                result["foreign_net_5d"] = float(recent_f.iloc[-5:].sum()) / 1e8
            if len(recent_f) >= 20:
                result["foreign_net_20d"] = float(recent_f.iloc[-20:].sum()) / 1e8
            consec_f = 0
            for v in reversed(recent_f.tolist()):
                if v > 0:
                    consec_f += 1
                else:
                    break
            result["foreign_consecutive_buy"] = consec_f

    except ImportError:
        log.debug("[inst_flow] pykrx not available")
    except Exception as exc:
        log.debug("[inst_flow] krx flow failed %s: %s", symbol, exc)
    return result


# ── OBV 기반 proxy ────────────────────────────────────────────────────────────


def _obv_proxy(symbol: str) -> dict:
    """OBV 기반 수급 proxy 지표."""
    result: dict = {"obv_slope": "FLAT", "price_obv_divergence": False, "bb_squeeze_recovery": False}
    try:
        import numpy as np

        from tele_quant.stock_data_provider import get_ohlcv

        df = get_ohlcv(symbol, period="3mo", interval="1d")
        if df is None or df.empty:
            return result

        close = df["Close"].dropna()
        vol = df["Volume"].dropna()
        if len(close) < 20:
            return result

        # OBV
        direction = close.diff().apply(lambda x: 1 if x > 0 else (-1 if x < 0 else 0))
        obv = (vol * direction).cumsum()
        window = min(20, len(obv))
        obv_slope_val = np.polyfit(range(window), obv.iloc[-window:].values, 1)[0]
        result["obv_slope"] = "UP" if obv_slope_val > 0 else ("DOWN" if obv_slope_val < 0 else "FLAT")

        # OBV divergence (가격 횡보 + OBV 상승)
        close_slope = np.polyfit(range(10), close.iloc[-10:].values, 1)[0]
        obv_slope_10 = np.polyfit(range(10), obv.iloc[-10:].values, 1)[0]
        price_flat = abs(close_slope / (close.iloc[-10:].mean() + 1e-9)) < 0.003
        result["price_obv_divergence"] = bool(price_flat and obv_slope_10 > 0)

        # BB 수축 후 MA20 회복
        ma20 = close.rolling(20).mean()
        std20 = close.rolling(20).std()
        width = (4 * std20) / (ma20 + 1e-9)
        if len(width) >= 5:
            prev_squeeze = width.iloc[-5] < 0.05
            now_above_ma = float(close.iloc[-1]) > float(ma20.iloc[-1])
            result["bb_squeeze_recovery"] = bool(prev_squeeze and now_above_ma)

    except Exception as exc:
        log.debug("[inst_flow] obv proxy failed %s: %s", symbol, exc)
    return result


# ── 점수 계산 ─────────────────────────────────────────────────────────────────


def _compute_flow_score(
    krx: dict,
    proxy: dict,
    rsi: float | None,
    ret_20d: float | None,
    vol_ratio: float | None,
    bb_pct: float | None,
) -> tuple[float, str, list[str]]:
    """수급집중 점수(0~100) 및 레벨(HIGH/MEDIUM/LOW) 반환."""
    score = 40.0
    notes: list[str] = []

    # KRX 기관/외국인 순매수 신호
    inst_5d = krx.get("inst_net_5d")
    foreign_5d = krx.get("foreign_net_5d")
    inst_consec = krx.get("inst_consecutive_buy", 0)
    foreign_consec = krx.get("foreign_consecutive_buy", 0)

    if inst_5d is not None:
        if inst_5d > 50:
            score += 15
            notes.append(f"기관 5일 순매수 +{inst_5d:.0f}억")
        elif inst_5d > 0:
            score += 7
            notes.append(f"기관 5일 순매수 +{inst_5d:.0f}억 (소폭)")
        elif inst_5d < -50:
            score -= 10
            notes.append(f"기관 5일 순매도 {inst_5d:.0f}억")

    if inst_consec >= 5:
        score += 10
        notes.append(f"기관 {inst_consec}일 연속 순매수")
    elif inst_consec >= 3:
        score += 5
        notes.append(f"기관 {inst_consec}일 연속 순매수")

    if foreign_5d is not None and foreign_5d > 0:
        score += 5
        notes.append(f"외국인 5일 순매수 +{foreign_5d:.0f}억")

    if foreign_consec >= 3:
        score += 5
        notes.append(f"외국인 {foreign_consec}일 연속 순매수")

    # proxy 지표
    if proxy.get("price_obv_divergence"):
        score += 10
        notes.append("가격 횡보 + OBV 상승 (매집 proxy 신호)")
    elif proxy.get("obv_slope") == "UP":
        score += 5
        notes.append("OBV 상승 추세")
    elif proxy.get("obv_slope") == "DOWN":
        score -= 5

    if proxy.get("bb_squeeze_recovery"):
        score += 8
        notes.append("볼린저밴드 수축 후 MA20 회복")

    # RSI 45~65 구간 (적정)
    if rsi is not None:
        if 45 <= rsi <= 65:
            score += 5
            notes.append(f"RSI {rsi:.0f} 적정 구간")
        elif rsi > 70:
            score -= 8
            notes.append(f"RSI {rsi:.0f} 과열 — 수급 집중 신뢰도 낮음")
        elif rsi < 35:
            score -= 3

    # 과열 패널티
    if ret_20d is not None and ret_20d > 30:
        score -= 10
        notes.append(f"1개월 +{ret_20d:.0f}% 과열 추격주의")
    if vol_ratio is not None and vol_ratio > 5:
        score -= 5
        notes.append(f"거래량 {vol_ratio:.1f}배 폭발 (단기 소진 주의)")
    if bb_pct is not None and bb_pct > 0.95:
        score -= 5
        notes.append("볼린저밴드 상단 과열")

    score = min(max(score, 0), 100)

    if score >= 65:
        level = "HIGH"
    elif score >= 45:
        level = "MEDIUM"
    else:
        level = "LOW"

    return score, level, notes


# ── 메인 ─────────────────────────────────────────────────────────────────────


def compute_institutional_flow(
    symbol: str,
    rsi: float | None = None,
    ret_20d: float | None = None,
    vol_ratio: float | None = None,
    bb_pct: float | None = None,
) -> InstitutionalFlowSignal:  # type: ignore[name-defined]
    """기관/외국인 수급 신호 계산.

    실패해도 부분 결과 반환 (graceful fallback).
    """
    from tele_quant.analysis.report_models import InstitutionalFlowSignal

    sig = InstitutionalFlowSignal()

    # KRX 데이터 (KR만)
    is_kr = symbol.endswith((".KS", ".KQ"))
    krx = _fetch_krx_flow(symbol) if is_kr else {}
    sig.inst_net_5d = krx.get("inst_net_5d")
    sig.inst_net_20d = krx.get("inst_net_20d")
    sig.foreign_net_5d = krx.get("foreign_net_5d")
    sig.foreign_net_20d = krx.get("foreign_net_20d")
    sig.inst_consecutive_buy = krx.get("inst_consecutive_buy", 0)
    sig.inst_consecutive_sell = krx.get("inst_consecutive_sell", 0)
    sig.foreign_consecutive_buy = krx.get("foreign_consecutive_buy", 0)
    sig.data_source = "krx" if any(v is not None for v in [sig.inst_net_5d, sig.inst_net_20d]) else "proxy"

    # OBV proxy
    proxy = _obv_proxy(symbol)
    sig.obv_slope = proxy.get("obv_slope", "FLAT")
    sig.price_obv_divergence = proxy.get("price_obv_divergence", False)
    sig.bb_squeeze_recovery = proxy.get("bb_squeeze_recovery", False)

    # 점수 계산
    sig.flow_score, sig.flow_level, sig.flow_notes = _compute_flow_score(
        krx, proxy, rsi, ret_20d, vol_ratio, bb_pct
    )

    return sig
