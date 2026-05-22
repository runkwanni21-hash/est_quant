"""Technical Signal Engine — technical_playbooks.yml 기반 실제 지표 계산.

공개 정보 기반 리서치 보조. 투자 판단 책임은 사용자에게 있음.
stock_data_provider 캐시 경유 필수 (yfinance 직접 호출 금지).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pandas as pd

    from tele_quant.analysis.report_models import TechnicalAccumulationSignal

log = logging.getLogger(__name__)

_PLAYBOOK_PATH = Path(__file__).parent.parent.parent.parent / "config" / "technical_playbooks.yml"

# ── 플레이북 로딩 ─────────────────────────────────────────────────────────────


def _load_playbook() -> dict:
    try:
        import yaml  # type: ignore[import-untyped]
        with _PLAYBOOK_PATH.open(encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception as exc:
        log.warning("[tech_engine] playbook load failed: %s", exc)
        return {}


_PLAYBOOK: dict | None = None


def _playbook() -> dict:
    global _PLAYBOOK
    if _PLAYBOOK is None:
        _PLAYBOOK = _load_playbook()
    return _PLAYBOOK


# ── OBV 계산 ─────────────────────────────────────────────────────────────────


def _obv_trend(df: pd.DataFrame) -> str:  # type: ignore[name-defined]
    """OBV 20일 추세: UP / DOWN / FLAT."""
    try:
        import numpy as np

        close = df["Close"].dropna()
        volume = df["Volume"].dropna()
        if len(close) < 5:
            return "FLAT"
        direction = close.diff().apply(lambda x: 1 if x > 0 else (-1 if x < 0 else 0))
        obv = (volume * direction).cumsum()
        window = min(20, len(obv))
        recent = obv.iloc[-window:]
        if len(recent) < 2:
            return "FLAT"
        slope = np.polyfit(range(len(recent)), recent.values, 1)[0]
        if slope > 0:
            return "UP"
        if slope < 0:
            return "DOWN"
        return "FLAT"
    except Exception:
        return "FLAT"


def _obv_divergence(df: pd.DataFrame) -> bool:  # type: ignore[name-defined]
    """OBV 상승 + 가격 횡보 = 잠재적 매집 신호."""
    try:
        import numpy as np

        close = df["Close"].dropna()
        volume = df["Volume"].dropna()
        if len(close) < 10:
            return False
        direction = close.diff().apply(lambda x: 1 if x > 0 else (-1 if x < 0 else 0))
        obv = (volume * direction).cumsum()
        recent_close = close.iloc[-10:]
        recent_obv = obv.iloc[-10:]
        close_slope = np.polyfit(range(10), recent_close.values, 1)[0]
        obv_slope = np.polyfit(range(10), recent_obv.values, 1)[0]
        price_flat = abs(close_slope / (recent_close.mean() + 1e-9)) < 0.003
        return price_flat and obv_slope > 0
    except Exception:
        return False


# ── 볼린저밴드 ────────────────────────────────────────────────────────────────


def _bollinger(df: pd.DataFrame, period: int = 20) -> dict:  # type: ignore[name-defined]
    """볼린저밴드 지표 계산."""
    result: dict = {"pct": None, "width": None, "squeeze": False, "pattern": ""}
    try:

        close = df["Close"].dropna()
        if len(close) < period:
            return result
        ma = close.rolling(period).mean()
        std = close.rolling(period).std()
        upper = ma + 2 * std
        lower = ma - 2 * std
        width = (upper - lower) / (ma + 1e-9)
        last_close = float(close.iloc[-1])
        last_upper = float(upper.iloc[-1])
        last_lower = float(lower.iloc[-1])
        last_ma = float(ma.iloc[-1])
        last_width = float(width.iloc[-1])
        squeeze_threshold = _playbook().get("bollinger_band", {}).get("squeeze_threshold", 0.05)
        result["pct"] = (last_close - last_lower) / (last_upper - last_lower + 1e-9)
        result["width"] = last_width
        result["squeeze"] = last_width < squeeze_threshold

        # 패턴 감지
        if len(close) >= 3:
            prev2 = float(close.iloc[-3])
            prev1 = float(close.iloc[-2])
            prev_lower = float(lower.iloc[-2])
            prev_ma = float(ma.iloc[-2])
            if prev2 < prev_lower and last_close > prev_ma:
                result["pattern"] = "하단 이탈 후 회복"
            elif prev1 < prev_ma and last_close > prev_ma:
                result["pattern"] = "중단 회복"
            elif result["squeeze"] and last_close > last_ma:
                result["pattern"] = "수축 후 상단 접근"
    except Exception as exc:
        log.debug("[tech_engine] bollinger failed: %s", exc)
    return result


# ── 이동평균 ──────────────────────────────────────────────────────────────────


def _ma_position(df: pd.DataFrame) -> dict:  # type: ignore[name-defined]
    """MA20/60/120 위치 계산."""
    result: dict = {"ma20": None, "ma60": None, "ma120": None, "close": None,
                    "above_ma20": None, "above_ma60": None}
    try:
        close = df["Close"].dropna()
        n = len(close)
        last = float(close.iloc[-1])
        result["close"] = last
        for period, key in [(20, "ma20"), (60, "ma60"), (120, "ma120")]:
            if n >= period:
                val = float(close.rolling(period).mean().iloc[-1])
                result[key] = val
        if result["ma20"] is not None:
            result["above_ma20"] = last > result["ma20"]
        if result["ma60"] is not None:
            result["above_ma60"] = last > result["ma60"]
    except Exception as exc:
        log.debug("[tech_engine] ma_position failed: %s", exc)
    return result


# ── 거래량/거래대금 ──────────────────────────────────────────────────────────


def _volume_metrics(df: pd.DataFrame) -> dict:  # type: ignore[name-defined]
    """거래량 20일 평균 대비 배율, 거래대금 증가율."""
    result: dict = {"vol_ratio_20d": None, "turnover_change_pct": None}
    try:

        vol = df["Volume"].dropna()
        close = df["Close"].dropna()
        if len(vol) < 20:
            return result
        avg20 = float(vol.iloc[-20:-1].mean())
        last_vol = float(vol.iloc[-1])
        result["vol_ratio_20d"] = last_vol / (avg20 + 1e-9)

        # 거래대금 (Volume * Close)
        if len(close) >= 20 and len(vol) >= 20:
            turnover = vol * close
            recent5 = float(turnover.iloc[-5:].mean())
            prev5 = float(turnover.iloc[-10:-5].mean())
            result["turnover_change_pct"] = (recent5 - prev5) / (abs(prev5) + 1e-9) * 100
    except Exception as exc:
        log.debug("[tech_engine] volume failed: %s", exc)
    return result


# ── 수익률 ───────────────────────────────────────────────────────────────────


def _returns(df: pd.DataFrame) -> dict:  # type: ignore[name-defined]
    """1D/3D/5D/10D/20D 수익률(%) 및 52주 위치."""
    result: dict = {
        "ret_1d": None, "ret_3d": None, "ret_5d": None,
        "ret_10d": None, "ret_20d": None,
        "w52_high": None, "w52_low": None, "w52_position_pct": None,
    }
    try:
        close = df["Close"].dropna()
        n = len(close)
        last = float(close.iloc[-1])
        for days, key in [(1, "ret_1d"), (3, "ret_3d"), (5, "ret_5d"), (10, "ret_10d"), (20, "ret_20d")]:
            if n > days:
                prev = float(close.iloc[-(days + 1)])
                result[key] = (last - prev) / (prev + 1e-9) * 100
        w52 = close.iloc[-252:]
        if len(w52) > 0:
            hi = float(w52.max())
            lo = float(w52.min())
            result["w52_high"] = hi
            result["w52_low"] = lo
            result["w52_position_pct"] = (last - lo) / (hi - lo + 1e-9) * 100
    except Exception as exc:
        log.debug("[tech_engine] returns failed: %s", exc)
    return result


# ── RSI ──────────────────────────────────────────────────────────────────────


def _rsi(close: pd.Series, period: int = 14) -> float | None:  # type: ignore[name-defined]
    try:

        if len(close) < period + 1:
            return None
        delta = close.diff()
        gain = delta.where(delta > 0, 0.0)
        loss = -delta.where(delta < 0, 0.0)
        avg_gain = gain.rolling(period).mean()
        avg_loss = loss.rolling(period).mean()
        rs = avg_gain / avg_loss.replace(0, 1e-10)
        rsi = 100 - (100 / (1 + rs))
        val = rsi.iloc[-1]
        import pandas as pd
        return float(val) if not pd.isna(val) else None
    except Exception:
        return None


# ── 과열 감지 ────────────────────────────────────────────────────────────────


def _detect_overheat(
    rsi: float | None,
    ret_20d: float | None,
    vol_ratio: float | None,
    bb_pct: float | None,
) -> bool:
    """과열 추격주의 여부 판단."""
    flags = 0
    if rsi is not None and rsi > 70:
        flags += 1
    if ret_20d is not None and ret_20d > 30:
        flags += 1
    if vol_ratio is not None and vol_ratio > 3.0:
        flags += 1
    if bb_pct is not None and bb_pct > 0.95:
        flags += 1
    return flags >= 2


# ── RSI 점수 ─────────────────────────────────────────────────────────────────


def _rsi_score(rsi: float | None) -> tuple[float, str]:
    """playbook RSI score_rules long 기준 점수 반환."""
    if rsi is None:
        return 0.0, ""
    pb = _playbook().get("rsi", {}).get("score_rules", {}).get("long", [])
    for rule in pb:
        if "range" in rule:
            lo, hi = rule["range"]
            if lo <= rsi <= hi:
                return float(rule.get("score", 0)), rule.get("label", "")
        elif "threshold_above" in rule:
            if rsi >= rule["threshold_above"]:
                return float(rule.get("score", 0)), rule.get("label", "")
        elif "threshold_below" in rule:
            if rsi < rule["threshold_below"]:
                return float(rule.get("score", 0)), rule.get("label", "")
    return 0.0, ""


# ── MA 점수 ──────────────────────────────────────────────────────────────────


def _ma_score(above_ma20: bool | None, above_ma60: bool | None) -> float:
    score = 0.0
    if above_ma20 is True:
        score += 4.0
    if above_ma60 is True:
        score += 3.0
    if above_ma20 is False:
        score -= 2.0
    return score


# ── 메인 엔진 ────────────────────────────────────────────────────────────────


def compute_technical_accumulation_signal(
    symbol: str,
    period: str = "6mo",
) -> TechnicalAccumulationSignal:  # type: ignore[name-defined]
    """종목 기술적 매집 신호 계산.

    stock_data_provider 캐시 경유 필수.
    실패해도 부분 결과 반환 (graceful fallback).
    """
    from tele_quant.analysis.report_models import TechnicalAccumulationSignal
    from tele_quant.stock_data_provider import get_ohlcv

    sig = TechnicalAccumulationSignal()

    try:
        df = get_ohlcv(symbol, period=period, interval="1d")
        if df is None or df.empty:
            log.debug("[tech_engine] no ohlcv for %s", symbol)
            return sig

        close = df["Close"].dropna()

        # RSI 1D
        sig.rsi_1d = _rsi(close, 14)

        # RSI 4H (4시간 봉은 별도 조회, 없으면 생략)
        try:
            df_4h = get_ohlcv(symbol, period="60d", interval="1h")
            if df_4h is not None and not df_4h.empty:
                # 4시간 단위 resample
                df_4h_res = df_4h["Close"].resample("4h").last().dropna()
                sig.rsi_4h = _rsi(df_4h_res, 14)
        except Exception:
            pass

        # 볼린저밴드
        bb = _bollinger(df)
        sig.bb_pct = bb["pct"]
        sig.bb_width = bb["width"]
        sig.bb_squeeze = bb["squeeze"]
        if bb["pattern"]:
            sig.patterns.append(f"BB: {bb['pattern']}")

        # OBV
        sig.obv_trend = _obv_trend(df)
        sig.obv_divergence = _obv_divergence(df)

        # MA 위치
        ma = _ma_position(df)
        sig.ma20 = ma["ma20"]
        sig.ma60 = ma["ma60"]
        sig.ma120 = ma["ma120"]
        sig.close = ma["close"]
        sig.above_ma20 = ma["above_ma20"]
        sig.above_ma60 = ma["above_ma60"]

        # 거래량/거래대금
        vol = _volume_metrics(df)
        sig.vol_ratio_20d = vol["vol_ratio_20d"]
        sig.turnover_change_pct = vol["turnover_change_pct"]

        # 수익률 / 52주
        rets = _returns(df)
        sig.ret_1d = rets["ret_1d"]
        sig.ret_3d = rets["ret_3d"]
        sig.ret_5d = rets["ret_5d"]
        sig.ret_10d = rets["ret_10d"]
        sig.ret_20d = rets["ret_20d"]
        sig.w52_high = rets["w52_high"]
        sig.w52_low = rets["w52_low"]
        sig.w52_position_pct = rets["w52_position_pct"]

        # 과열 감지
        sig.overheat = _detect_overheat(sig.rsi_1d, sig.ret_20d, sig.vol_ratio_20d, sig.bb_pct)

        # 점수 계산 (0~100)
        score = 0.0

        rsi_pts, rsi_label = _rsi_score(sig.rsi_1d)
        score += min(max(rsi_pts, -5), 15)
        if rsi_label:
            sig.patterns.append(rsi_label)

        bb_pts = 0.0
        if bb["pattern"] == "하단 이탈 후 회복":
            bb_pts = 8.0
        elif bb["pattern"] == "중단 회복" or bb["pattern"] == "수축 후 상단 접근":
            bb_pts = 7.0
        score += bb_pts

        if sig.obv_trend == "UP":
            score += 6.0
            sig.patterns.append("OBV 상승 추세")
        if sig.obv_divergence:
            score += 8.0
            sig.patterns.append("OBV 상승 + 가격 횡보 (매집 신호)")

        score += _ma_score(sig.above_ma20, sig.above_ma60)

        if sig.vol_ratio_20d is not None:
            if 1.3 <= sig.vol_ratio_20d <= 3.0:
                score += 5.0
                sig.patterns.append(f"거래량 {sig.vol_ratio_20d:.1f}배 (적정 증가)")
            elif sig.vol_ratio_20d > 3.0:
                score -= 3.0
                sig.patterns.append(f"거래량 {sig.vol_ratio_20d:.1f}배 (과열 주의)")

        if sig.turnover_change_pct is not None and sig.turnover_change_pct > 20:
            score += 4.0
            sig.patterns.append(f"거래대금 +{sig.turnover_change_pct:.0f}% 증가")

        # 52주 위치 보너스
        if sig.w52_position_pct is not None:
            if 30 <= sig.w52_position_pct <= 70:
                score += 4.0
            elif sig.w52_position_pct > 90:
                score -= 3.0
                sig.patterns.append("52주 고점 근접")

        # 과열 패널티
        if sig.overheat:
            score -= 10.0

        sig.score = min(max(score, 0.0), 100.0)

        # 레이블
        if sig.overheat:
            sig.label = "과열 추격주의"
        elif sig.obv_divergence and sig.score >= 50:
            sig.label = "수급집중 가능성"
        elif "중단 회복" in bb["pattern"] or (sig.above_ma20 and sig.ret_5d is not None and sig.ret_5d < 5):
            sig.label = "눌림 후 재상승"
        elif sig.score < 35:
            sig.label = "기준 미달"
        else:
            sig.label = "기술적 중립"

    except Exception as exc:
        log.warning("[tech_engine] %s compute failed: %s", symbol, exc)

    return sig
