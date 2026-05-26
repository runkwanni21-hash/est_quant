"""Stock Snapshot — 단일 종목 즉시 분석 스냅샷.

공개 정보 기반 리서치 보조. 투자 판단 책임은 사용자에게 있음.
표현 제약: "매수 권장" / "매도 권장" / "확정 수익" / "세력 매집 확정" 금지.
5%는 확정 목표가 아닌 '관찰 기준/기대 보상 구간'으로만 표현.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from tele_quant.db import Store

log = logging.getLogger(__name__)

_DISCLAIMER = "⚠ 공개 정보 기반 리서치 보조 — 투자 판단 책임은 사용자에게 있음"

__all__ = [
    "StockAnalysisSnapshot",
    "_quick_tech_score",
    "analyze_single",
    "build_stock_snapshot",
    "compute_accumulation_pattern",
    "compute_daily_technicals",
    "compute_price_changes",
    "compute_star_rating",
    "compute_swing_setup",
    "compute_swing_trade_score",
    "fetch_price_window",
    "format_stock_snapshot",
]


# ── Data model ────────────────────────────────────────────────────────────────


@dataclass
class StockAnalysisSnapshot:
    """단일 종목 분석 스냅샷 — 가격·기술·펀더멘탈·섹터·스윙·이슈·수혜주."""

    symbol: str
    market: str
    name: str = ""

    # ── 4H 기술 지표 ─────────────────────────────────────────────────────────
    close: float | None = None
    rsi: float | None = None
    bb_pct: float | None = None
    vol_ratio: float | None = None
    obv_trend: str = ""
    tech_score: float = 0.0
    tech_reason: str = ""
    direction: str = "LONG"

    # ── 일봉 가격 변동률 ─────────────────────────────────────────────────────
    price_change_1d: float | None = None   # %
    price_change_1w: float | None = None   # %
    price_change_1m: float | None = None   # %
    price_change_3m: float | None = None   # %

    # ── 일봉 이동평균 / 보조 지표 ─────────────────────────────────────────────
    ma_20: float | None = None
    ma_60: float | None = None
    daily_rsi: float | None = None

    # ── 스윙 셋업 ─────────────────────────────────────────────────────────────
    setup_label: str = ""        # 셋업 유형 (과매도 반등/20MA 지지 등)
    setup_score: float = 0.0    # 셋업 점수 (0~100)
    accum_signal: str = ""       # 수급 패턴 신호
    accum_score: float = 0.0    # 수급 점수 (0~100)
    swing_score: float = 0.0    # 종합 스윙 점수 (0~100)
    swing_grade: str = "—"      # A등급/B등급/C등급/기준 미달/—

    # ── 펀더멘탈 ─────────────────────────────────────────────────────────────
    sector: str = ""
    industry: str = ""   # yfinance industry (sector_id 탐지 정밀도 향상)
    fund_line: str = ""
    val_score: float = 0.0
    val_reason: str = ""
    edge_label: str = ""
    institutional_blind: bool = False

    # ── 재무지표 (개별 필드) ─────────────────────────────────────────────────
    pe_trailing: float | None = None
    pe_forward: float | None = None
    pb: float | None = None
    roe: float | None = None             # %
    eps_growth: float | None = None      # YoY %
    revenue_growth: float | None = None  # %
    op_margin: float | None = None       # %
    debt_to_equity: float | None = None
    dividend_yield: float | None = None  # %

    # ── 심화 밸류에이션 ────────────────────────────────────────────────────────
    ev_to_ebitda: float | None = None
    fcf_yield: float | None = None       # %
    gross_margin: float | None = None    # %
    current_ratio: float | None = None
    peg_ratio: float | None = None

    # ── 애널리스트 컨센서스 ────────────────────────────────────────────────────
    analyst_target: float | None = None
    analyst_target_upside: float | None = None  # %
    analyst_count: int | None = None
    analyst_rec_mean: float | None = None  # 1=강매수 ~ 5=강매도

    # ── 시총 / 52주 ──────────────────────────────────────────────────────────
    market_cap_krw: float | None = None
    market_cap_usd: float | None = None
    w52_high: float | None = None
    w52_low: float | None = None
    w52_position_pct: float | None = None  # 0~100%

    # ── 섹터 분석 ────────────────────────────────────────────────────────────
    sector_title: str = ""
    sector_score: float = 50.0
    sector_lines: list[str] = field(default_factory=list)
    sector_risks: list[str] = field(default_factory=list)
    sector_catalysts: list[str] = field(default_factory=list)
    sector_peers: list[str] = field(default_factory=list)
    sector_checkpoints: list[str] = field(default_factory=list)

    # ── 종합 ─────────────────────────────────────────────────────────────────
    total_score: float = 0.0
    grade: str = "—"

    # ── 이슈·수혜주 ──────────────────────────────────────────────────────────
    recent_issues: list[str] = field(default_factory=list)
    beneficiaries: list[str] = field(default_factory=list)
    error: str = ""

    # ── 티커 해소 정보 ────────────────────────────────────────────────────────
    cap_bucket: str = ""          # 대형주 / 마이크로캡 / …
    exchange_label: str = ""      # NYSE / NASDAQ / OTC / …
    ticker_warnings: list[str] = field(default_factory=list)
    ticker_changed: bool = False

    # ── 재무 품질 (Piotroski / Altman Z / ROIC / CAGR) ───────────────────────
    piotroski_score: int | None = None
    altman_z: float | None = None
    altman_zone: str = ""
    roic: float | None = None          # %
    revenue_cagr_3y: float | None = None  # %
    short_float_pct: float | None = None
    insider_pct: float | None = None
    institutional_pct: float | None = None
    financial_quality_text: str = ""

    # ── DCF 추정 ─────────────────────────────────────────────────────────────
    dcf_text: str = ""

    # ── 섹터 시드 관계 힌트 ────────────────────────────────────────────────────
    relation_hints: dict[str, list[Any]] = field(default_factory=dict)

    # ── 섹터 매크로 지표 (format_sector_macro 결과 캐시) ──────────────────────
    sector_macro_text: str = ""

    # ── 섹터 심층 분석 (sector_intelligence) ─────────────────────────────────
    sector_intelligence_text: str = ""

    # ── 실적 스냅샷 ──────────────────────────────────────────────────────────
    earnings_text: str = ""

    # ── 캘린더 정책 노트 (월요일/금요일 특수 정책) ───────────────────────────
    policy_note: str = ""

    # ── 최근 이슈 포맷된 텍스트 (recent_issue_collector) ───────────────────
    recent_issues_formatted: str = ""

    # ── TradingView 차트 링크 ─────────────────────────────────────────────
    chart_url_4h: str = ""
    chart_url_daily: str = ""

    # ── 연간 실적 히스토리 ────────────────────────────────────────────────
    earnings_history_text: str = ""

    # ── LONG 관찰 적합도 별점 ─────────────────────────────────────────────
    star_rating: str = ""   # ★★★☆☆
    star_sub: str = ""      # 기술:B / 펀더:A / 스윙:C

    # ── 모멘텀 신호 ────────────────────────────────────────────────────────
    momentum_text: str = ""

    # ── EPS 서프라이즈 ────────────────────────────────────────────────────
    earnings_surprise_text: str = ""

    # ── 투자 스코어카드 ──────────────────────────────────────────────────
    scorecard_text: str = ""

    # ── 매집 의심 분석 ────────────────────────────────────────────────────
    accumulation_text: str = ""

    # ── 실적-주가 괴리 분석 ───────────────────────────────────────────────
    mispricing_text: str = ""


# ── Price window ───────────────────────────────────────────────────────────────


def fetch_price_window(symbol: str, period: str = "3mo") -> Any:
    """일봉 OHLCV 데이터 반환 (stock_data_provider 캐시 경유).

    Returns:
        pd.DataFrame 또는 None (실패 시).
    """
    from tele_quant.stock_data_provider import get_ohlcv

    return get_ohlcv(symbol, period=period, interval="1d")


# ── Price changes ──────────────────────────────────────────────────────────────


def compute_price_changes(df: Any) -> dict[str, float | None]:
    """일봉 DataFrame에서 1D/1W/1M/3M 가격 변동률(%) 계산."""
    result: dict[str, float | None] = {"1d": None, "1w": None, "1m": None, "3m": None}
    try:
        import pandas as pd

        if df is None or (isinstance(df, pd.DataFrame) and df.empty):
            return result
        closes = df["Close"].dropna()
        n = len(closes)
        if n < 2:
            return result
        last = float(closes.iloc[-1])

        def _pct(lookback: int) -> float | None:
            if n > lookback:
                prev = float(closes.iloc[-(lookback + 1)])
                return (last - prev) / prev * 100 if prev else None
            return None

        result["1d"] = _pct(1)
        result["1w"] = _pct(5)
        result["1m"] = _pct(21)
        result["3m"] = _pct(min(62, n - 1))
    except Exception as exc:
        log.debug("compute_price_changes error: %s", exc)
    return result


# ── Daily technicals ───────────────────────────────────────────────────────────


def compute_daily_technicals(df: Any) -> dict[str, float | None]:
    """일봉 DataFrame에서 MA20/MA60/RSI(14) 계산."""
    result: dict[str, float | None] = {"ma_20": None, "ma_60": None, "rsi": None}
    try:
        import pandas as pd

        if df is None or (isinstance(df, pd.DataFrame) and df.empty):
            return result
        closes = df["Close"].dropna()
        n = len(closes)

        if n >= 20:
            result["ma_20"] = float(closes.rolling(20).mean().iloc[-1])
        if n >= 60:
            result["ma_60"] = float(closes.rolling(60).mean().iloc[-1])

        # RSI 14
        if n >= 15:
            delta = closes.diff()
            gain = delta.clip(lower=0).rolling(14).mean()
            loss = (-delta.clip(upper=0)).rolling(14).mean()
            g = float(gain.iloc[-1])
            lo = float(loss.iloc[-1])
            if lo and lo != 0:
                result["rsi"] = 100.0 - (100.0 / (1.0 + g / lo))
    except Exception as exc:
        log.debug("compute_daily_technicals error: %s", exc)
    return result


# ── Swing setup ────────────────────────────────────────────────────────────────


def compute_swing_setup(
    tech_4h: dict[str, Any],
    daily_tech: dict[str, float | None],
    price_changes: dict[str, float | None],
    direction: str,
) -> tuple[str, float]:
    """스윙 셋업 유형과 원점수(0~100) 반환.

    셋업 유형 (LONG):
      - 과매도 반등 셋업: 4H RSI < 35
      - 20MA 지지 반등 셋업: 현재가 MA20±3% 이내
      - 눌림목 매집 구간: 1개월 음수 + RSI 40~60
      - 일반 LONG 셋업

    셋업 유형 (SHORT):
      - 과열 매도 셋업: 4H RSI > 75
      - 단기 급등 과열: 1주 +10% 이상
      - 일반 SHORT 셋업
    """
    rsi_4h = tech_4h.get("rsi")
    daily_rsi = daily_tech.get("rsi")
    ma_20 = daily_tech.get("ma_20")
    close_4h = tech_4h.get("close")
    pct_1m = price_changes.get("1m")
    pct_1w = price_changes.get("1w")

    label = "데이터 부족"
    score = 40.0

    if direction == "LONG":
        if rsi_4h is not None and rsi_4h < 35:
            label = "과매도 반등 셋업"
            score = 75.0 + (10.0 if daily_rsi and daily_rsi < 40 else 0.0)
        elif close_4h and ma_20 and close_4h >= ma_20:
            proximity = abs((close_4h - ma_20) / ma_20 * 100)
            if proximity <= 3.0:
                label = "20MA 지지 반등 셋업"
                score = 65.0
            elif rsi_4h is not None and 40 <= rsi_4h <= 60:
                label = "일반 LONG 셋업"
                score = 55.0
            else:
                label = "일반 LONG 셋업"
                score = 50.0
        elif pct_1m is not None and pct_1m < 0 and rsi_4h is not None and 40 <= rsi_4h <= 60:
            label = "눌림목 매집 구간"
            score = 60.0
        elif rsi_4h is not None:
            label = "일반 LONG 셋업"
            score = 50.0
    else:  # SHORT
        if rsi_4h is not None and rsi_4h > 75:
            label = "과열 매도 셋업"
            score = 75.0
        elif pct_1w is not None and pct_1w > 10:
            label = "단기 급등 과열"
            score = 65.0
        elif rsi_4h is not None:
            label = "일반 SHORT 셋업"
            score = 50.0

    return label, min(score, 100.0)


# ── Accumulation pattern ───────────────────────────────────────────────────────


def compute_accumulation_pattern(df: Any) -> tuple[str, float]:
    """거래량·가격 패턴으로 수급 신호를 판단한다 (0~100).

    주의: "세력 매집 확정" 같은 단정 표현 절대 금지.
    "매집 가능성이 있는 수급 패턴" 수준으로만 표현.
    """
    try:
        import pandas as pd

        if df is None or (isinstance(df, pd.DataFrame) and df.empty):
            return "수급 패턴 불명확", 40.0

        closes = df["Close"].dropna()
        volumes = df["Volume"].dropna()
        if len(closes) < 10 or len(volumes) < 10:
            return "데이터 부족", 40.0

        recent_vol = float(volumes.iloc[-5:].mean())
        base_vols = volumes.iloc[-20:-5] if len(volumes) >= 20 else volumes.iloc[:-5]
        prev_vol = float(base_vols.mean()) if len(base_vols) > 0 else recent_vol
        vol_ratio = recent_vol / prev_vol if prev_vol > 0 else 1.0

        price_5d = (
            (float(closes.iloc[-1]) - float(closes.iloc[-6])) / float(closes.iloc[-6]) * 100
            if len(closes) >= 6 else 0.0
        )

        if vol_ratio >= 1.5 and abs(price_5d) < 3.0:
            return "매집 가능성이 있는 수급 패턴", 75.0
        elif vol_ratio >= 1.3 and price_5d > 0:
            return "거래량 증가 + 가격 안정 패턴", 65.0
        elif vol_ratio < 0.7:
            return "거래량 감소 — 방향성 약화 가능성", 35.0
        else:
            return "수급 패턴 불명확", 50.0
    except Exception as exc:
        log.debug("compute_accumulation_pattern error: %s", exc)
        return "수급 패턴 불명확", 40.0


# ── Technical score ────────────────────────────────────────────────────────────


def _quick_tech_score(d: dict[str, Any], side: str) -> tuple[float, str]:
    """4H 데이터로 기술적 점수 계산 (0~40점)."""
    score = 0.0
    parts: list[str] = []

    rsi = d.get("rsi")
    bb_pct = d.get("bb_pct")
    vol_ratio = d.get("vol_ratio") or 1.0
    obv = d.get("obv", "")

    if not d:
        return 0.0, "데이터 부족"

    # playbook RSI 레이블 (점수는 기존 유지, 레이블만 보강)
    _pb_rsi_label: str = ""
    if rsi is not None:
        try:
            from tele_quant.sector_analysis_engine import score_rsi_from_playbook
            _, _pb_rsi_label = score_rsi_from_playbook(rsi, side=side.lower())
        except Exception:
            pass

    if side == "LONG":
        if rsi is not None:
            if rsi < 40:
                score += 15
                parts.append(f"RSI {rsi:.0f}({_pb_rsi_label or '과매도'})")
            elif rsi < 55:
                score += 10
                parts.append(f"RSI {rsi:.0f}({_pb_rsi_label or '중립'})")
            elif rsi < 70:
                score += 5
                parts.append(f"RSI {rsi:.0f}({_pb_rsi_label or '상승'})")
            else:
                score -= 5
                parts.append(f"RSI {rsi:.0f}({_pb_rsi_label or '과열'})")
        if bb_pct is not None:
            if bb_pct < 20:
                score += 10
                parts.append("볼린저 하단 근접")
            elif bb_pct < 50:
                score += 5
                parts.append("볼린저 중하단")
        if vol_ratio >= 1.5:
            score += 8
            parts.append(f"거래량 {vol_ratio:.1f}x↑")
        elif vol_ratio >= 1.2:
            score += 4
            parts.append(f"거래량 {vol_ratio:.1f}x")
        if "상승" in obv:
            score += 7
            parts.append("OBV 상승")
    else:  # SHORT
        if rsi is not None:
            if rsi > 70:
                score += 15
                parts.append(f"RSI {rsi:.0f}({_pb_rsi_label or '과열'})")
            elif rsi > 55:
                score += 8
                parts.append(f"RSI {rsi:.0f}({_pb_rsi_label or '고점권'})")
        if bb_pct is not None:
            if bb_pct > 80:
                score += 10
                parts.append("볼린저 상단 돌파")
            elif bb_pct > 60:
                score += 5
                parts.append("볼린저 중상단")
        if vol_ratio >= 1.5:
            score += 8
            parts.append(f"거래량 {vol_ratio:.1f}x↑")
        if "하락" in obv:
            score += 7
            parts.append("OBV 하락")

    reason = " · ".join(parts) if parts else "데이터 부족"
    return min(score, 40.0), reason


# ── Swing trade score ──────────────────────────────────────────────────────────


def compute_swing_trade_score(snap: StockAnalysisSnapshot) -> tuple[float, str]:
    """스윙 트레이드 종합 점수 및 등급 계산.

    공식:
        swing = tech_setup*0.35 + accum*0.20 + sector_val*0.20
                + issue*0.15 + relation*0.10 - penalties

    등급: A(>=70) / B(>=55) / C(>=40) / 기준 미달(<40)
    """
    # tech_setup: tech_score(0~40) → 0~100 정규화
    tech_norm = (snap.tech_score / 40.0) * 100.0
    tech_comp = tech_norm * 0.35

    # accum: 0~100
    accum_comp = snap.accum_score * 0.20

    # sector value: 0~100 (기본 50)
    sector_comp = snap.sector_score * 0.20

    # recent issue: base 50, +15 per issue up to 100
    issue_score = min(50.0 + len(snap.recent_issues) * 15.0, 100.0)
    issue_comp = issue_score * 0.15

    # relation trigger: 기본 50 (향후 relation score 연동 예정)
    relation_comp = 50.0 * 0.10

    raw = tech_comp + accum_comp + sector_comp + issue_comp + relation_comp

    # Penalties
    penalties = 0.0
    if snap.rsi and snap.rsi > 75 and snap.direction == "LONG":
        penalties += 10.0
    if snap.price_change_1m and snap.price_change_1m > 30:
        penalties += 15.0
    if snap.debt_to_equity and snap.debt_to_equity > 200:
        penalties += 5.0

    score = max(0.0, min(100.0, raw - penalties))

    if score >= 70:
        grade = "A등급"
    elif score >= 55:
        grade = "B등급"
    elif score >= 40:
        grade = "C등급"
    else:
        grade = "기준 미달"

    return score, grade


# ── Star rating ────────────────────────────────────────────────────────────────


def compute_star_rating(snap: StockAnalysisSnapshot) -> tuple[str, str]:
    """LONG 관찰 적합도 별 1~5개 계산.

    가중치:
        기술점수 (tech_score/40 → 0~100)  40%
        펀더멘탈 (val_score 0~100)         30%
        스윙점수 (swing_score 0~100)       30%

    Returns:
        (star_str, sub_info) 예: ("★★★☆☆", "기술:B / 펀더:A / 스윙:C")
    """
    tech_norm = (snap.tech_score / 40.0) * 100.0 if snap.tech_score else 0.0
    composite = tech_norm * 0.40 + snap.val_score * 0.30 + snap.swing_score * 0.30

    if composite >= 82:
        stars = 5
    elif composite >= 70:
        stars = 4
    elif composite >= 55:
        stars = 3
    elif composite >= 40:
        stars = 2
    else:
        stars = 1

    star_str = "★" * stars + "☆" * (5 - stars)

    def _grade(v: float) -> str:
        if v >= 75:
            return "A"
        if v >= 55:
            return "B"
        if v >= 40:
            return "C"
        return "D"

    sub_info = f"기술:{_grade(tech_norm)} / 펀더:{_grade(snap.val_score)} / 스윙:{_grade(snap.swing_score)}"
    return star_str, sub_info


# ── Core builder ───────────────────────────────────────────────────────────────


def build_stock_snapshot(
    symbol: str,
    market: str = "",
    store: Store | None = None,
    deep: bool = False,
    quick: bool = False,
) -> StockAnalysisSnapshot:
    """단일 종목 분석 스냅샷 생성.

    Args:
        symbol: 종목 코드 (예: 005930.KS, NVDA)
        market: KR | US (비어 있으면 symbol로 자동 판별)
        store:  DB Store (이슈·수혜주 조회용, optional)
        deep:   True이면 DB에서 이슈·수혜주 체인까지 조회
        quick:  True이면 가격/기술 중심, 이슈·실적·섹터분석 생략

    Returns:
        StockAnalysisSnapshot
    """
    from tele_quant.relation_feed import _NAME_MAP

    # bare 숫자 ticker → 6자리 KR canonical 형식
    try:
        from tele_quant.financial_sanity import canonicalize_kr_ticker, is_bare_kr_ticker
        if is_bare_kr_ticker(symbol):
            symbol = canonicalize_kr_ticker(symbol)
    except Exception:
        pass

    if not market:
        market = "KR" if symbol.endswith((".KS", ".KQ")) else "US"

    name = _NAME_MAP.get(symbol, symbol)
    snap = StockAnalysisSnapshot(symbol=symbol, market=market, name=name)

    # ── 티커 해소 (변경/OTC/마이크로캡/IPO 감지) ─────────────────────────────
    try:
        from tele_quant.ticker_resolver import resolve_ticker

        tr = resolve_ticker(symbol, market)
        snap.cap_bucket = tr.cap_bucket
        snap.exchange_label = tr.exchange
        snap.ticker_warnings = tr.warnings
        snap.ticker_changed = tr.ticker_changed
        if tr.long_name and tr.long_name != symbol:
            snap.name = tr.long_name
        if tr.ticker_changed and tr.resolved_symbol != symbol:
            symbol = tr.resolved_symbol
            snap.symbol = symbol
    except Exception as exc:
        log.debug("[stock_snapshot] ticker_resolver failed for %s: %s", symbol, exc)

    # ── 4H 기술적 분석 ───────────────────────────────────────────────────────
    tech_4h: dict[str, Any] = {}
    try:
        from tele_quant.daily_alpha import _fetch_4h_data

        tech_4h = _fetch_4h_data(symbol)
        snap.rsi = tech_4h.get("rsi")
        snap.close = tech_4h.get("close")
        snap.bb_pct = tech_4h.get("bb_pct")
        snap.vol_ratio = tech_4h.get("vol_ratio")
        snap.obv_trend = tech_4h.get("obv", "")

        snap.direction = "SHORT" if (snap.rsi or 50) > 65 else "LONG"
        long_score, long_reason = _quick_tech_score(tech_4h, "LONG")
        short_score, short_reason = _quick_tech_score(tech_4h, "SHORT")
        if snap.direction == "LONG":
            snap.tech_score, snap.tech_reason = long_score, long_reason
        else:
            snap.tech_score, snap.tech_reason = short_score, short_reason
    except Exception as exc:
        log.debug("[stock_snapshot] tech fetch failed for %s: %s", symbol, exc)
        snap.tech_reason = "기술 데이터 조회 실패"

    # ── 일봉 가격·기술 지표 ──────────────────────────────────────────────────
    daily_tech: dict[str, float | None] = {}
    price_changes: dict[str, float | None] = {}
    try:
        df = fetch_price_window(symbol, period="3mo")
        price_changes = compute_price_changes(df)
        snap.price_change_1d = price_changes.get("1d")
        snap.price_change_1w = price_changes.get("1w")
        snap.price_change_1m = price_changes.get("1m")
        snap.price_change_3m = price_changes.get("3m")

        daily_tech = compute_daily_technicals(df)
        snap.ma_20 = daily_tech.get("ma_20")
        snap.ma_60 = daily_tech.get("ma_60")
        snap.daily_rsi = daily_tech.get("rsi")

        # 스윙 셋업
        label, setup_sc = compute_swing_setup(tech_4h, daily_tech, price_changes, snap.direction)
        snap.setup_label = label
        snap.setup_score = setup_sc

        # 수급 패턴
        accum_sig, accum_sc = compute_accumulation_pattern(df)
        snap.accum_signal = accum_sig
        snap.accum_score = accum_sc

        # close 보완 (4H가 없을 때 일봉 종가 사용)
        if snap.close is None and df is not None and not df.empty:
            snap.close = float(df["Close"].dropna().iloc[-1])
    except Exception as exc:
        log.debug("[stock_snapshot] price window failed for %s: %s", symbol, exc)

    # ── 펀더멘탈 ─────────────────────────────────────────────────────────────
    try:
        from tele_quant.fundamentals import (
            build_fundamental_line,
            fetch_fundamentals,
            get_edge_label,
            is_institutional_blind_spot,
            score_fundamentals,
        )

        fund = fetch_fundamentals(symbol, market)
        snap.val_score, snap.val_reason = score_fundamentals(fund, snap.direction)
        snap.fund_line = build_fundamental_line(fund)
        snap.edge_label = get_edge_label(fund)
        snap.institutional_blind = is_institutional_blind_spot(fund)

        # 재무 이상치 경고 필드 복사
        snap.fund_sanity_note = getattr(fund, "sanity_note", "")  # type: ignore[attr-defined]
        snap.fund_confidence = getattr(fund, "data_confidence", "HIGH")  # type: ignore[attr-defined]

        # 섹터
        snap.sector = fund.sector or ""
        snap.industry = getattr(fund, "industry", "") or ""

        # 개별 재무지표 추출
        snap.pe_trailing = fund.pe_trailing
        snap.pe_forward = fund.pe_forward
        snap.pb = fund.pb
        snap.roe = fund.roe
        snap.eps_growth = fund.eps_growth
        snap.revenue_growth = fund.revenue_growth
        snap.op_margin = fund.op_margin
        snap.debt_to_equity = fund.debt_to_equity
        snap.dividend_yield = fund.dividend_yield

        # 시총 / 52주
        snap.market_cap_krw = fund.market_cap_krw
        snap.market_cap_usd = fund.market_cap_usd
        snap.w52_high = fund.w52_high
        snap.w52_low = fund.w52_low
        snap.w52_position_pct = fund.w52_position_pct

        # 심화 밸류에이션 + 애널리스트
        snap.ev_to_ebitda = fund.ev_to_ebitda
        snap.fcf_yield = fund.fcf_yield
        snap.gross_margin = fund.gross_margin
        snap.current_ratio = fund.current_ratio
        snap.peg_ratio = fund.peg_ratio
        snap.analyst_target = fund.analyst_target
        snap.analyst_target_upside = fund.analyst_target_upside
        snap.analyst_count = fund.analyst_count
        snap.analyst_rec_mean = fund.analyst_rec_mean

        # close 보완 (yfinance current_price)
        if snap.close is None and fund.current_price:
            snap.close = fund.current_price
    except Exception as exc:
        log.debug("[stock_snapshot] fundamentals failed for %s: %s", symbol, exc)

    # ── 섹터 ID 탐지 (섹터분석·매크로·sector_intel 공통) ─────────────────────
    _sector_id: str | None = None
    try:
        from tele_quant.sector_macro import (
            detect_seed_sector,
            guess_sector_id,
            symbol_sector_override,
        )
        _sector_id = symbol_sector_override(symbol)          # YAML + 하드코딩 override
        if _sector_id is None and store is not None:
            _sector_id = detect_seed_sector(symbol, store)   # DB 섹터 시드 우선
        if _sector_id is None and snap.industry:
            _sector_id = guess_sector_id(snap.industry)      # industry가 더 정밀
        if _sector_id is None and snap.sector:
            _sector_id = guess_sector_id(snap.sector)
    except Exception as exc:
        log.debug("[stock_snapshot] sector_id detect failed for %s: %s", symbol, exc)

    # ── 재무 품질 분석 (빠른 모드 제외) ──────────────────────────────────────
    if not quick:
        try:
            from tele_quant.financial_quality import (
                fetch_financial_quality,
                format_financial_quality,
            )

            fq = fetch_financial_quality(symbol, market)
            snap.piotroski_score = fq.piotroski_score
            snap.altman_z = fq.altman_z
            snap.altman_zone = fq.altman_zone
            snap.roic = fq.roic
            snap.revenue_cagr_3y = fq.revenue_cagr_3y
            snap.short_float_pct = fq.short_float_pct
            snap.insider_pct = fq.insider_pct
            snap.institutional_pct = fq.institutional_pct
            snap.financial_quality_text = format_financial_quality(fq)
            snap._fq = fq  # type: ignore[attr-defined]
        except Exception as exc:
            log.debug("[stock_snapshot] financial_quality failed for %s: %s", symbol, exc)

    # ── DCF 추정 (빠른 모드 제외, US 종목 EPS 있을 때) ─────────────────────
    if not quick:
        try:
            from tele_quant.dcf_estimator import estimate_dcf, format_dcf

            dcf = estimate_dcf(symbol, market)
            snap.dcf_text = format_dcf(dcf, market)
        except Exception as exc:
            log.debug("[stock_snapshot] dcf failed for %s: %s", symbol, exc)

    # ── 섹터 분석 ────────────────────────────────────────────────────────────
    if _sector_id or snap.sector:
        try:
            from tele_quant.sector_valuation import analyze_sector_value

            fund_dict: dict[str, Any] = {}
            if snap.pb is not None:
                fund_dict["pb"] = snap.pb
            if snap.revenue_growth is not None:
                fund_dict["revenueGrowth"] = snap.revenue_growth / 100
            if snap.op_margin is not None:
                fund_dict["operatingMargins"] = snap.op_margin / 100

            sa = analyze_sector_value(
                symbol=symbol,
                market=market,
                sector=_sector_id or snap.sector,
                fund_snapshot=fund_dict,
                issues=snap.recent_issues or None,
                store=store,
            )
            snap.sector_title = sa.title
            snap.sector_score = sa.score
            snap.sector_lines = sa.lines
            snap.sector_risks = sa.risks
            snap.sector_catalysts = sa.catalysts
            snap.sector_peers = sa.peer_symbols
            snap.sector_checkpoints = sa.next_checkpoints
        except Exception as exc:
            log.debug("[stock_snapshot] sector analysis failed for %s: %s", symbol, exc)

    # ── 종합 점수 ────────────────────────────────────────────────────────────
    snap.total_score = min(
        snap.tech_score / 40 * 50 + snap.val_score / 100 * 50, 100.0
    )
    if snap.total_score >= 80:
        snap.grade = "★★★"
    elif snap.total_score >= 65:
        snap.grade = "★★"
    elif snap.total_score >= 50:
        snap.grade = "★"

    # ── 스윙 트레이드 점수 ───────────────────────────────────────────────────
    snap.swing_score, snap.swing_grade = compute_swing_trade_score(snap)

    # ── 캘린더 정책 → 스윙 점수 보정 ────────────────────────────────────────
    try:
        from tele_quant.calendar_score_policy import apply_policy_to_score
        _adj_swing, _policy_adj_note = apply_policy_to_score(
            snap.swing_score,
            snap.direction,
            price_change_1d=snap.price_change_1d,
            rsi_4h=snap.rsi,
            price_change_1w=snap.price_change_1w,
        )
        if _adj_swing != snap.swing_score:
            snap.swing_score = _adj_swing
            if snap.swing_grade not in ("기준 미달", "—"):
                snap.swing_grade = f"{snap.swing_grade}*"
    except Exception as exc:
        log.debug("[stock_snapshot] calendar_policy adjust failed: %s", exc)

    # ── 이슈 (빠른 모드 제외 — 기본 3개, deep 5개) ─────────────────────────────
    if not quick:
        _max_issues = 5 if deep else 3
        try:
            from tele_quant.recent_issue_collector import (
                collect_recent_issues,
                format_recent_issues,
            )
            _issues = collect_recent_issues(
                symbol=symbol,
                name=snap.name,
                market=snap.market,
                store=store,
                days=7,
                max_items=_max_issues,
            )
            if _issues:
                snap.recent_issues = [f"{i.title}" for i in _issues]
                snap.recent_issues_formatted = format_recent_issues(_issues)
        except Exception as exc:
            log.debug("[stock_snapshot] recent_issues failed for %s: %s", symbol, exc)
            if deep:
                snap.recent_issues = _get_recent_issues(symbol, store)

    # ── 수혜주 (deep=True일 때만) ──────────────────────────────────────────────
    if deep:
        try:
            snap.beneficiaries = _get_beneficiary_symbols(symbol, store)
        except Exception as exc:
            log.debug("[stock_snapshot] beneficiaries failed for %s: %s", symbol, exc)

    # ── 섹터 시드 관계 힌트 (store 있을 때 항상) ──────────────────────────────
    if store is not None:
        try:
            from tele_quant.relation_seed_importer import get_relation_hints

            snap.relation_hints = get_relation_hints(symbol, store, max_per_category=3)
        except Exception as exc:
            log.debug("[stock_snapshot] relation_hints failed for %s: %s", symbol, exc)

    # ── 섹터 매크로 지표 ────────────────────────────────────────────────────────
    if _sector_id:
        try:
            from tele_quant.sector_macro import format_sector_macro
            snap.sector_macro_text = format_sector_macro(_sector_id)
        except Exception as exc:
            log.debug("[stock_snapshot] sector_macro failed for %s: %s", symbol, exc)

    # ── 실적 스냅샷 (빠른 모드 제외) ─────────────────────────────────────────
    if not quick:
        try:
            from tele_quant.earnings_snapshot import (
                fetch_earnings_snapshot,
                format_earnings_snapshot,
            )
            e_snap = fetch_earnings_snapshot(symbol, snap.market)
            snap.earnings_text = format_earnings_snapshot(e_snap)
        except Exception as exc:
            log.debug("[stock_snapshot] earnings_snapshot failed for %s: %s", symbol, exc)

    # ── 섹터 심층 분석 (sector_intelligence, 빠른 모드 제외) ─────────────────
    if not quick and _sector_id:
        try:
            from tele_quant.sector_intelligence import (
                build_sector_intelligence,
                format_sector_intelligence,
            )
            price_snap = {
                "1d": snap.price_change_1d,
                "1w": snap.price_change_1w,
                "1m": snap.price_change_1m,
                "3m": snap.price_change_3m,
            }
            fund_snap = {
                "pe_forward": snap.pe_forward,
                "pe_trailing": snap.pe_trailing,
                "pb": snap.pb,
                "roe": snap.roe,
                "eps_growth": snap.eps_growth,
                "revenue_growth": snap.revenue_growth,
                "op_margin": snap.op_margin,
                "dividend_yield": snap.dividend_yield,
            }
            intel = build_sector_intelligence(
                symbol=symbol,
                name=snap.name,
                market=snap.market,
                sector_id=_sector_id,
                store=store,
                price_snapshot=price_snap,
                fundamental_snapshot=fund_snap,
                recent_issues=list(snap.recent_issues),
                deep=deep,
            )
            if intel is not None:
                snap.sector_intelligence_text = format_sector_intelligence(intel)
                if intel.policy_note:
                    snap.policy_note = intel.policy_note
        except Exception as exc:
            log.debug("[stock_snapshot] sector_intelligence failed for %s: %s", symbol, exc)

    # ── 캘린더 정책 노트 (sector_intelligence에서 못 가져온 경우 fallback) ──────
    if not snap.policy_note:
        try:
            from tele_quant.calendar_score_policy import format_policy_note
            snap.policy_note = format_policy_note()
        except Exception as exc:
            log.debug("[stock_snapshot] calendar_policy failed: %s", exc)

    # ── TradingView 차트 링크 ────────────────────────────────────────────────
    try:
        from tele_quant.tradingview import chart_url
        snap.chart_url_4h = chart_url(symbol, market, interval="240")
        snap.chart_url_daily = chart_url(symbol, market, interval="D")
    except Exception as exc:
        log.debug("[stock_snapshot] tradingview link failed for %s: %s", symbol, exc)

    # ── 연간 실적 히스토리 (빠른 모드 제외) ──────────────────────────────────
    if not quick:
        try:
            from tele_quant.earnings_history import (
                fetch_earnings_history,
                format_earnings_history,
            )
            eh = fetch_earnings_history(symbol, snap.market)
            snap.earnings_history_text = format_earnings_history(eh)
        except Exception as exc:
            log.debug("[stock_snapshot] earnings_history failed for %s: %s", symbol, exc)

    # ── 모멘텀 신호 (빠른 모드 제외) ────────────────────────────────────────
    if not quick:
        try:
            from tele_quant.momentum_signals import (
                fetch_momentum_signals,
                format_momentum_signals,
            )
            msig = fetch_momentum_signals(symbol, market)
            snap.momentum_text = format_momentum_signals(msig)
            # scorecard 입력값 저장
            snap._msig = msig  # type: ignore[attr-defined]
        except Exception as exc:
            log.debug("[stock_snapshot] momentum_signals failed for %s: %s", symbol, exc)

    # ── EPS 서프라이즈 (빠른 모드 제외) ──────────────────────────────────────
    if not quick:
        try:
            from tele_quant.earnings_surprise import (
                fetch_earnings_surprise,
                format_earnings_surprise,
            )
            es = fetch_earnings_surprise(symbol)
            snap.earnings_surprise_text = format_earnings_surprise(es)
            snap._esurp = es  # type: ignore[attr-defined]
        except Exception as exc:
            log.debug("[stock_snapshot] earnings_surprise failed for %s: %s", symbol, exc)

    # ── 투자 스코어카드 (빠른 모드 제외) ─────────────────────────────────────
    if not quick:
        try:
            from tele_quant.investment_scorecard import build_scorecard, format_scorecard

            msig = getattr(snap, "_msig", None)
            esurp = getattr(snap, "_esurp", None)
            fq_obj = getattr(snap, "_fq", None)

            sc = build_scorecard(
                symbol,
                rs_3m_pct=msig.rs_3m_pct if msig else None,
                rs_1m_pct=msig.rs_1m_pct if msig else None,
                vol_surge_ratio=msig.vol_surge_ratio if msig else None,
                week52_pos_pct=msig.week52_pos_pct if msig else None,
                is_breakout=msig.is_breakout if msig else False,
                dtc=msig.dtc if msig else None,
                piotroski_score=snap.piotroski_score,
                roic=snap.roic,
                gross_margin=snap.gross_margin,
                current_ratio=snap.current_ratio,
                net_cash_positive=(msig.net_cash_per_share or 0) > 0 if msig else False,
                revenue_cagr_3y=snap.revenue_cagr_3y,
                earnings_growth=snap.eps_growth,
                beat_rate_pct=esurp.beat_rate_pct if esurp else None,
                avg_surprise_pct=esurp.avg_surprise_pct if esurp else None,
                surprise_trend=esurp.trend if esurp else "",
                piotroski_pass_count=len(fq_obj.piotroski_signals) if fq_obj else 0,
                altman_z=snap.altman_z,
                institutional_pct=snap.institutional_pct,
                short_float_pct=snap.short_float_pct,
                peg_ratio=snap.peg_ratio,
                dcf_upside_pct=None,  # parsed separately if needed
                fcf_yield=snap.fcf_yield,
                analyst_target_upside=snap.analyst_target_upside,
            )
            snap.scorecard_text = format_scorecard(sc)
        except Exception as exc:
            log.debug("[stock_snapshot] scorecard failed for %s: %s", symbol, exc)

    # ── 매집 의심 분석 ───────────────────────────────────────────────────────
    if not quick:
        try:
            from tele_quant.accumulation_detector import detect_accumulation, format_accumulation

            accum_df = fetch_price_window(symbol, period="6mo")
            if accum_df is not None and not accum_df.empty:
                # 수급 데이터 (KR 종목은 KRX 데이터 재사용)
                _inst_5d = _inst_20d = _for_5d = _for_20d = None
                try:
                    from tele_quant.analysis.institutional_flow import _fetch_krx_flow
                    _krx = _fetch_krx_flow(symbol) if market == "KR" else {}
                    _inst_5d = _krx.get("inst_net_5d")
                    _inst_20d = _krx.get("inst_net_20d")
                    _for_5d = _krx.get("foreign_net_5d")
                    _for_20d = _krx.get("foreign_net_20d")
                except Exception:
                    pass

                accum_result = detect_accumulation(
                    symbol=symbol,
                    df=accum_df,
                    inst_net_5d=_inst_5d,
                    inst_net_20d=_inst_20d,
                    foreign_net_5d=_for_5d,
                    foreign_net_20d=_for_20d,
                    news_texts=snap.recent_issues,
                )
                snap.accumulation_text = format_accumulation(accum_result)
        except Exception as exc:
            log.debug("[stock_snapshot] accumulation_detector failed for %s: %s", symbol, exc)

    # ── 실적-주가 괴리 분석 ──────────────────────────────────────────────────
    if not quick:
        try:
            from tele_quant.mispricing_detector import detect_mispricing, format_mispricing

            _price_pos = snap.w52_position_pct   # 52주 위치 (0~100)
            _p6m = snap.price_change_3m  # 6개월 대신 3개월 변동률 사용 (데이터 가용)
            msp = detect_mispricing(
                symbol=symbol,
                market=market,
                price_position_pct=_price_pos,
                price_6m_chg_pct=_p6m,
            )
            snap.mispricing_text = format_mispricing(msp)
        except Exception as exc:
            log.debug("[stock_snapshot] mispricing_detector failed for %s: %s", symbol, exc)

    # ── LONG 관찰 적합도 별점 ────────────────────────────────────────────────
    snap.star_rating, snap.star_sub = compute_star_rating(snap)

    return snap


def _get_recent_issues(symbol: str, store: Store | None) -> list[str]:
    """DB에서 최근 이슈 텍스트 목록 반환 (최대 3개)."""
    if store is None:
        return []
    try:
        rows = store.get_recent_sentiment_history(symbol=symbol, limit=3)
        return [(r.get("snippet") or r.get("title") or "") for r in rows if r]
    except Exception:
        return []


def _get_beneficiary_symbols(symbol: str, store: Store | None) -> list[str]:
    """관계 그래프에서 이 종목이 source인 수혜주 목록 반환 (최대 4개)."""
    if store is None:
        return []
    try:
        edges = store.get_all_relation_edges(active_only=True)
        benes = [
            str(e.get("target_symbol") or "")
            for e in edges
            if e.get("source_symbol") == symbol
            and e.get("relation_type") in ("BENEFICIARY", "PEER_MOMENTUM", "SUPPLIER")
        ]
        return [b for b in benes if b][:4]
    except Exception:
        return []


# ── Formatter ──────────────────────────────────────────────────────────────────


def _fmt_pct(v: float | None) -> str:
    """변동률 포맷 (None 이면 빈 문자열)."""
    if v is None:
        return ""
    sign = "+" if v >= 0 else ""
    return f"{sign}{v:.1f}%"


def format_stock_snapshot(snap: StockAnalysisSnapshot) -> str:
    """StockAnalysisSnapshot → 텔레그램용 텍스트."""
    lines: list[str] = []

    # ── 헤더 ─────────────────────────────────────────────────────────────────
    header_tags: list[str] = []
    if snap.cap_bucket:
        header_tags.append(snap.cap_bucket)
    if snap.exchange_label:
        header_tags.append(snap.exchange_label)
    tag_str = f"  [{'] ['.join(header_tags)}]" if header_tags else ""
    lines.append(f"🔍 **{snap.name}** ({snap.symbol}){tag_str}")
    lines.append("")

    # 티커 경고 (변경/OTC/마이크로캡/IPO)
    ticker_warnings = snap.ticker_warnings
    if snap.close is not None:
        ticker_warnings = [w for w in ticker_warnings if "yfinance KR 데이터 없음" not in w]

    for warn in ticker_warnings[:3]:
        lines.append(f"⚠ {warn}")
    if ticker_warnings:
        lines.append("")

    # ── 현재가 ───────────────────────────────────────────────────────────────
    if snap.close is not None:
        price_str = (
            f"{snap.close:,.0f}원" if snap.market == "KR" else f"${snap.close:.2f}"
        )
        lines.append(f"현재가: {price_str}")

    # ── 변동률 (있을 때만) ────────────────────────────────────────────────────
    change_pairs = [
        ("1D", snap.price_change_1d),
        ("1W", snap.price_change_1w),
        ("1M", snap.price_change_1m),
        ("3M", snap.price_change_3m),
    ]
    change_parts = [f"{lbl} {_fmt_pct(v)}" for lbl, v in change_pairs if v is not None]
    if change_parts:
        lines.append(f"변동: {' | '.join(change_parts)}")

    # ── 52주 위치 ─────────────────────────────────────────────────────────────
    if snap.w52_position_pct is not None:
        pos_int = int(snap.w52_position_pct / 10)
        bar = "▓" * pos_int + "░" * (10 - pos_int)
        lines.append(f"52주 위치: {snap.w52_position_pct:.0f}% [{bar}]")

    # ── 방향·기술 ─────────────────────────────────────────────────────────────
    lines.append("")
    lines.append(f"방향 시사: {snap.direction}  |  기술점수: {snap.tech_score:.0f}/40")
    if snap.tech_reason:
        lines.append(f"기술(4H): {snap.tech_reason}")

    # 스윙 셋업
    if snap.setup_label and snap.setup_label != "데이터 부족":
        lines.append(f"셋업: {snap.setup_label}")
    if snap.accum_signal and snap.accum_signal not in ("수급 패턴 불명확", "데이터 부족"):
        lines.append(f"수급: {snap.accum_signal}")

    # 이동평균
    ma_parts: list[str] = []
    if snap.close and snap.ma_20:
        diff_20 = (snap.close - snap.ma_20) / snap.ma_20 * 100
        ma_parts.append(f"MA20 {diff_20:+.1f}%")
    if snap.close and snap.ma_60:
        diff_60 = (snap.close - snap.ma_60) / snap.ma_60 * 100
        ma_parts.append(f"MA60 {diff_60:+.1f}%")
    if snap.daily_rsi:
        ma_parts.append(f"일봉RSI {snap.daily_rsi:.0f}")
    if ma_parts:
        lines.append(f"일봉: {' | '.join(ma_parts)}")

    # ── 펀더멘탈 ─────────────────────────────────────────────────────────────
    fund_parts: list[str] = []
    if snap.pe_trailing is not None:
        fund_parts.append(f"PER(TTM) {snap.pe_trailing:.1f}")
    if snap.pe_forward is not None:
        fund_parts.append(f"PER(F) {snap.pe_forward:.1f}")
    if snap.pb is not None:
        fund_parts.append(f"PBR {snap.pb:.2f}")
    if snap.roe is not None:
        fund_parts.append(f"ROE {snap.roe:.1f}%")
    if snap.eps_growth is not None:
        fund_parts.append(f"EPS성장 {_fmt_pct(snap.eps_growth)}")
    if snap.revenue_growth is not None:
        fund_parts.append(f"매출성장 {_fmt_pct(snap.revenue_growth)}")
    if snap.op_margin is not None:
        fund_parts.append(f"영업이익률 {snap.op_margin:.1f}%")
    if snap.dividend_yield is not None:
        fund_parts.append(f"배당 {snap.dividend_yield:.2f}%")

    if fund_parts:
        lines.append("")
        lines.append(" | ".join(fund_parts))
    elif snap.fund_line:
        lines.append("")
        lines.append(f"펀더멘탈: {snap.fund_line}")

    # ── 심화 지표 (EV/EBITDA, FCF, 매출총이익률, 유동비율, PEG) ─────────────
    adv_parts: list[str] = []
    if snap.ev_to_ebitda is not None:
        adv_parts.append(f"EV/EBITDA {snap.ev_to_ebitda:.1f}x")
    if snap.fcf_yield is not None:
        adv_parts.append(f"FCF수익률 {snap.fcf_yield:.1f}%")
    if snap.gross_margin is not None:
        adv_parts.append(f"매출총이익률 {snap.gross_margin:.1f}%")
    if snap.current_ratio is not None:
        adv_parts.append(f"유동비율 {snap.current_ratio:.1f}")
    if snap.peg_ratio is not None:
        adv_parts.append(f"PEG {snap.peg_ratio:.1f}")
    if adv_parts:
        lines.append(f"심화: {' | '.join(adv_parts)}")

    # ── 애널리스트 컨센서스 ──────────────────────────────────────────────────
    if snap.analyst_target is not None:
        tgt_str = (
            f"{snap.analyst_target:,.0f}원" if snap.market == "KR" else f"${snap.analyst_target:.2f}"
        )
        upside_str = (
            f" ({snap.analyst_target_upside:+.1f}%)" if snap.analyst_target_upside is not None else ""
        )
        n_str = f", {snap.analyst_count}명" if snap.analyst_count else ""
        lines.append(f"목표가: {tgt_str}{upside_str}{n_str}")
    if snap.analyst_rec_mean is not None:
        _rec_label = {1: "강매수", 2: "매수", 3: "중립", 4: "매도", 5: "강매도"}
        nearest = min(range(1, 6), key=lambda x: abs(x - snap.analyst_rec_mean))  # type: ignore[arg-type]
        lines.append(f"투자의견 평균: {snap.analyst_rec_mean:.1f} ({_rec_label.get(nearest, '')}권 근접)")

    if snap.val_reason:
        # ROE/EPS성장/매출성장/OPM/부채비율은 위 fund_parts 줄에 이미 표시됨 → 제거
        import re as _re
        _vr = _re.sub(r"ROE\d+[%\w]*우?수?\S*", "", snap.val_reason)
        _vr = _re.sub(r"EPS성장\d+%", "", _vr)
        _vr = _re.sub(r"매출성장\d+%", "", _vr)
        _vr = _re.sub(r"OPM\d+%", "", _vr)
        _vr = _re.sub(r"부채비율\d+%", "", _vr)
        _vr = _re.sub(r"W52\S*", "", _vr)
        _vr = _re.sub(r"[\s·]+", " ", _vr).strip(" ·")
        if _vr:
            lines.append(f"가치: {_vr[:100]}")
    if snap.edge_label:
        lines.append(f"엣지: {snap.edge_label}")
    if snap.institutional_blind:
        lines.append("🎯 기관 사각지대 구간")

    # ── 재무 품질 (Piotroski / Altman Z / ROIC / 지분 / 유동성) ─────────────
    if snap.financial_quality_text:
        lines.append("")
        lines.append(snap.financial_quality_text)

    # ── 섹터 분석 ────────────────────────────────────────────────────────────
    if snap.sector_title:
        lines.append("")
        lines.append(f"📊 섹터: {snap.sector_title}")
        for line in snap.sector_lines[:3]:
            lines.append(f"  {line}")
        if snap.sector_risks:
            lines.append(f"  ⚠ 리스크: {' / '.join(snap.sector_risks[:2])}")
        if snap.sector_catalysts:
            lines.append(f"  ✅ 촉매: {' / '.join(snap.sector_catalysts[:2])}")
        if snap.sector_peers:
            lines.append(f"  동종: {', '.join(snap.sector_peers[:4])}")
        if snap.sector_checkpoints:
            lines.append(f"  다음 확인: {snap.sector_checkpoints[0]}")

    # ── 종합 점수 ─────────────────────────────────────────────────────────────
    lines.append("")
    lines.append(f"종합: {snap.total_score:.0f}점 {snap.grade}")
    if snap.total_score >= 80:
        lines.append("→ 모의 포트폴리오 진입 기준 충족 (80점↑)")
    elif snap.total_score >= 70:
        lines.append("→ 관찰 후보 (추가 확인 권장)")
    else:
        lines.append("→ 현재 기준 미달")

    # 스윙 등급
    if snap.swing_grade and snap.swing_grade != "—":
        lines.append(f"스윙 등급: {snap.swing_grade} ({snap.swing_score:.0f}점)")
        if snap.swing_grade == "A등급":
            lines.append("  → 1~4주 기대 보상 구간 +5~15% (관찰 기준, 확정 아님)")
        elif snap.swing_grade == "기준 미달":
            lines.append("  → 현재 스윙 관찰 조건 미달")

    # ── 최근 이슈 ─────────────────────────────────────────────────────────────
    if snap.recent_issues_formatted:
        lines.append("")
        lines.append(snap.recent_issues_formatted)
    elif snap.recent_issues:
        lines.append("")
        lines.append("📰 최근 이슈:")
        for issue in snap.recent_issues[:3]:
            if issue:
                lines.append(f"  • {issue[:100]}")

    # ── 수혜 연관 ─────────────────────────────────────────────────────────────
    if snap.beneficiaries:
        lines.append("")
        lines.append(f"🔗 수혜 연관 종목: {', '.join(snap.beneficiaries)}")

    # ── 연간 실적 히스토리 ────────────────────────────────────────────────────
    if snap.earnings_history_text:
        lines.append("")
        lines.append(snap.earnings_history_text)

    # ── 실적 스냅샷 ───────────────────────────────────────────────────────────
    if snap.earnings_text:
        lines.append("")
        lines.append(snap.earnings_text)

    # ── 섹터 심층 분석 ────────────────────────────────────────────────────────
    if snap.sector_intelligence_text:
        lines.append("")
        lines.append(snap.sector_intelligence_text)

    # ── 섹터 시드 관계 힌트 ────────────────────────────────────────────────────
    if snap.relation_hints:
        try:
            from tele_quant.relation_seed_importer import format_relation_hints

            hints_text = format_relation_hints(snap.relation_hints)
            if hints_text:
                lines.append("")
                lines.append(hints_text)
        except Exception as exc:
            log.debug("[stock_snapshot] format_relation_hints failed: %s", exc)

    # ── 섹터 매크로 지표 ─────────────────────────────────────────────────────
    if snap.sector_macro_text:
        lines.append("")
        lines.append(snap.sector_macro_text)

    # ── 캘린더 정책 노트 ─────────────────────────────────────────────────────
    if snap.policy_note:
        lines.append("")
        lines.append(snap.policy_note)

    # ── DCF 추정 ─────────────────────────────────────────────────────────────
    if snap.dcf_text:
        lines.append("")
        lines.append(snap.dcf_text)

    # ── TradingView 차트 링크 ─────────────────────────────────────────────────
    if snap.chart_url_4h or snap.chart_url_daily:
        lines.append("")
        lines.append("📊 트레이딩뷰 차트:")
        if snap.chart_url_4h:
            lines.append(f"  4H: {snap.chart_url_4h}")
        if snap.chart_url_daily:
            lines.append(f"  일봉: {snap.chart_url_daily}")

    # ── 모멘텀 신호 ──────────────────────────────────────────────────────────
    if snap.momentum_text:
        lines.append("")
        lines.append(snap.momentum_text)

    # ── EPS 서프라이즈 ────────────────────────────────────────────────────────
    if snap.earnings_surprise_text:
        lines.append("")
        lines.append(snap.earnings_surprise_text)

    # ── 투자 스코어카드 ───────────────────────────────────────────────────────
    if snap.scorecard_text:
        lines.append("")
        lines.append(snap.scorecard_text)

    # ── 매집 의심 분석 ────────────────────────────────────────────────────────
    if snap.accumulation_text:
        lines.append("")
        lines.append(snap.accumulation_text)

    # ── 실적-주가 괴리 분석 ───────────────────────────────────────────────────
    if snap.mispricing_text:
        lines.append("")
        lines.append(snap.mispricing_text)

    # ── LONG 관찰 적합도 별점 ─────────────────────────────────────────────────
    if snap.star_rating:
        lines.append("")
        lines.append(f"🌟 LONG 관찰 적합도: {snap.star_rating}  ({snap.star_sub})")
        lines.append("  ⚠ 공개 정보 기반 관찰 지표. 매수/매도 확정 아님.")

    lines.append("")
    lines.append(_DISCLAIMER)

    return "\n".join(lines)


# ── Convenience alias ──────────────────────────────────────────────────────────


def analyze_single(
    symbol: str,
    market: str = "",
    store: Store | None = None,
) -> str:
    """단일 종목 즉시 분석 — 텔레그램 응답용 포맷 텍스트 반환."""
    snap = build_stock_snapshot(symbol, market, store, deep=False)
    return format_stock_snapshot(snap)
