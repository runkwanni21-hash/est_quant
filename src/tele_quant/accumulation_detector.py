"""매집 의심 분석 모듈 (Wyckoff-inspired Accumulation Detector).

공개 정보 기반 리서치 보조 — 투자 판단 책임은 사용자에게 있음.
매수·매도 권장 표현 없음. "가능성/의심/주의" 수준으로만 표현.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger(__name__)

_RISK_KEYWORDS = [
    "전환사채", "CB ", "BW ", "신주인수권", "유상증자", "보호예수",
    "대주주매도", "대주주 매도", "관리종목", "불성실공시", "횡령",
    "배임", "상장폐지", "감사의견", "주식담보", "반대매매",
]


# ── 결과 모델 ─────────────────────────────────────────────────────────────────

@dataclass
class AccumulationResult:
    score: int                       # 0~100
    confidence: str                  # 낮음/보통/높음
    key_reasons: list[str] = field(default_factory=list)   # 핵심근거 ≤3줄
    risk_factors: list[str] = field(default_factory=list)  # 위험요소 ≤3줄
    support: float | None = None     # 지지선
    resistance: float | None = None  # 저항선
    stop_loss: float | None = None   # 손절기준
    breakout_confirm: float | None = None  # 돌파확인선
    conclusion: str = "중립"         # 매집의심/중립/분산위험/위험주의
    component_scores: dict[str, int] = field(default_factory=dict)


def format_accumulation(result: AccumulationResult) -> str:
    """AccumulationResult → 텔레그램용 텍스트."""
    lines: list[str] = []
    lines.append(f"🔬 매집 의심 분석 [{result.conclusion}]")
    lines.append(f"  매집점수: {result.score}/100 | 신뢰도: {result.confidence}")

    if result.key_reasons:
        lines.append("  📌 핵심근거:")
        for r in result.key_reasons[:3]:
            lines.append(f"    • {r}")

    if result.risk_factors:
        lines.append("  ⚠ 위험요소:")
        for r in result.risk_factors[:3]:
            lines.append(f"    • {r}")

    price_parts: list[str] = []
    if result.support is not None:
        price_parts.append(f"지지 {result.support:,.0f}")
    if result.resistance is not None:
        price_parts.append(f"저항 {result.resistance:,.0f}")
    if result.stop_loss is not None:
        price_parts.append(f"손절 {result.stop_loss:,.0f}")
    if result.breakout_confirm is not None:
        price_parts.append(f"돌파확인 {result.breakout_confirm:,.0f}")
    if price_parts:
        lines.append(f"  📐 관찰가격: {' | '.join(price_parts)}")

    lines.append("  ※ 공개 정보 기반 관찰 지표. 매수/매도 확정 아님.")
    return "\n".join(lines)


# ── 세부 분석 함수 ────────────────────────────────────────────────────────────

def _score_position(df: Any) -> tuple[int, str | None]:
    """위치: 장기하락 후 바닥권 여부 (0~20점)."""
    try:
        close = df["Close"].dropna()
        if len(close) < 20:
            return 0, None

        high_52 = close.rolling(min(len(close), 252)).max().iloc[-1]
        low_52 = close.rolling(min(len(close), 252)).min().iloc[-1]
        cur = float(close.iloc[-1])

        if high_52 == low_52:
            return 5, None

        pos_pct = (cur - low_52) / (high_52 - low_52) * 100

        # 20일 이전 대비 하락폭
        peak_20 = float(close.iloc[-20:].max()) if len(close) >= 20 else cur
        drawdown_pct = (peak_20 - cur) / peak_20 * 100 if peak_20 > 0 else 0

        if pos_pct < 25:  # 52주 하위 25% 구간
            score = 20
            reason = f"52주 위치 {pos_pct:.0f}% — 바닥권 가능성"
        elif pos_pct < 45:
            score = 12
            reason = f"52주 위치 {pos_pct:.0f}% — 하단 구간"
        elif pos_pct < 70:
            score = 6
            reason = None
        else:  # 고점권 — 매집보다 분산 주의
            score = 0
            reason = f"52주 위치 {pos_pct:.0f}% — 고점권 (분산 주의)"

        # 최근 눌림 가산
        if drawdown_pct >= 15:
            score = min(score + 3, 20)

        return score, reason
    except Exception as exc:
        log.debug("[accum] position score failed: %s", exc)
        return 0, None


def _score_support(df: Any) -> tuple[int, str | None]:
    """지지: 특정 가격대 반복 방어, 아래꼬리, 신저가 실패 (0~15점)."""
    try:
        import numpy as np
        close = df["Close"].dropna().values
        low = df["Low"].dropna().values
        n = min(len(close), len(low))
        if n < 10:
            return 0, None

        close = close[-n:]
        low = low[-n:]

        # 아래꼬리 비율 (Low << Close 비율)
        wick_ratio = (close - low) / (close + 1e-9)
        long_wick_days = int((wick_ratio > 0.01).sum())
        wick_score = min(long_wick_days // 3, 5)

        # 신저가 실패: 최근 low가 이전 저점보다 낮지만 종가는 방어
        failed_new_low = 0
        for i in range(5, n):
            prev_low = float(np.min(low[max(0, i - 10):i]))
            if low[i] < prev_low and close[i] > prev_low:
                failed_new_low += 1

        failed_score = min(failed_new_low * 3, 6)

        # 특정 가격대 반복 방어: 최근 저점 군집
        recent_lows = low[-20:] if n >= 20 else low
        low_mean = float(np.mean(recent_lows))
        tight_lows = int((np.abs(recent_lows - low_mean) / low_mean < 0.03).sum())
        cluster_score = min(tight_lows // 2, 4)

        total = wick_score + failed_score + cluster_score
        if total >= 8:
            reason = f"지지대 반복 방어 신호 — 아래꼬리 {long_wick_days}일, 신저가 실패 {failed_new_low}회 가능성"
        elif total >= 4:
            reason = f"부분적 지지 신호 — 아래꼬리 {long_wick_days}일 관찰"
        else:
            reason = None

        return min(total, 15), reason
    except Exception as exc:
        log.debug("[accum] support score failed: %s", exc)
        return 0, None


def _score_volume_pattern(df: Any) -> tuple[int, str | None]:
    """거래량: 하락시 감소, 상승시 증가, 저점 대량거래 후 가격 방어 (0~15점)."""
    try:
        import numpy as np
        close = df["Close"].dropna().values
        volume = df["Volume"].dropna().values
        n = min(len(close), len(volume))
        if n < 15:
            return 0, None

        close = close[-n:]
        volume = volume[-n:]
        vol_mean = float(np.mean(volume)) + 1e-9

        up_days = close[1:] > close[:-1]
        down_days = ~up_days

        up_vol_mean = float(np.mean(volume[1:][up_days])) if up_days.sum() > 0 else 0
        dn_vol_mean = float(np.mean(volume[1:][down_days])) if down_days.sum() > 0 else 0

        # 상승 시 거래량 > 하락 시 거래량
        vol_ratio = up_vol_mean / (dn_vol_mean + 1e-9)
        vol_score = 0
        if vol_ratio >= 1.5:
            vol_score = 8
        elif vol_ratio >= 1.2:
            vol_score = 5
        elif vol_ratio >= 0.9:
            vol_score = 2

        # 저점 대량거래 후 가격 방어: 최근 저점 부근에서 거래량 급증 + 가격 방어
        low_threshold = float(np.percentile(close, 20))
        spike_defense = 0
        for i in range(1, n - 1):
            if close[i] < low_threshold and volume[i] > vol_mean * 1.5 and close[i + 1] >= close[i] * 0.99:
                spike_defense += 1

        spike_score = min(spike_defense * 3, 7)

        total = min(vol_score + spike_score, 15)
        if total >= 10:
            reason = f"거래량 패턴 양호 — 상승 거래량 하락 대비 {vol_ratio:.1f}배, 저점 방어 {spike_defense}회 가능성"
        elif total >= 5:
            reason = f"부분적 거래량 신호 — 상/하락 거래량 비율 {vol_ratio:.1f}배"
        else:
            reason = None

        return total, reason
    except Exception as exc:
        log.debug("[accum] volume score failed: %s", exc)
        return 0, None


def _score_absorption(df: Any) -> tuple[int, str | None]:
    """흡수: 매도량 대비 가격 하락 제한 여부 (0~15점)."""
    try:
        import numpy as np
        close = df["Close"].dropna().values
        volume = df["Volume"].dropna().values
        high = df["High"].dropna().values
        low = df["Low"].dropna().values
        n = min(len(close), len(volume), len(high), len(low))
        if n < 10:
            return 0, None

        close = close[-n:]
        volume = volume[-n:]
        high = high[-n:]
        low = low[-n:]
        vol_mean = float(np.mean(volume)) + 1e-9

        absorption_count = 0
        for i in range(1, n):
            bar_range = high[i] - low[i]
            if bar_range < 1e-9:
                continue
            close_pos = (close[i] - low[i]) / bar_range
            is_high_vol = volume[i] > vol_mean * 1.2
            price_drop_pct = (close[i] - close[i - 1]) / (close[i - 1] + 1e-9) * 100
            # 고거래량이지만 가격 하락 제한 (종가가 바 상단 40% 이상 위치)
            if is_high_vol and close_pos >= 0.4 and price_drop_pct > -1.5:
                absorption_count += 1

        score = min(absorption_count * 3, 15)
        if score >= 9:
            reason = f"매도 흡수 신호 {absorption_count}회 — 고거래량 하락 제한 가능성"
        elif score >= 5:
            reason = f"부분적 흡수 신호 {absorption_count}회"
        else:
            reason = None

        return score, reason
    except Exception as exc:
        log.debug("[accum] absorption score failed: %s", exc)
        return 0, None


def _score_spring(df: Any) -> tuple[int, str | None]:
    """스프링: 지지선 이탈 후 빠른 회복 여부 (0~10점)."""
    try:
        import numpy as np
        close = df["Close"].dropna().values
        low = df["Low"].dropna().values
        n = min(len(close), len(low))
        if n < 15:
            return 0, None

        close = close[-n:]
        low = low[-n:]

        # 최근 지지선: 과거 20일 저점 평균
        support_level = float(np.min(low)) if n < 20 else float(np.mean(np.sort(low)[:5]))

        spring_count = 0
        for i in range(5, n - 2):
            # 지지선 이탈
            if low[i] < support_level * 0.99:
                # 빠른 회복: 2일 내 지지선 상회
                for j in range(i + 1, min(i + 3, n)):
                    if close[j] > support_level:
                        spring_count += 1
                        break

        if spring_count >= 2:
            return 10, f"스프링 패턴 {spring_count}회 — 지지선 이탈 후 빠른 회복 가능성"
        elif spring_count == 1:
            return 5, "스프링 패턴 1회 — 지지선 이탈 후 회복 관찰"
        return 0, None
    except Exception as exc:
        log.debug("[accum] spring score failed: %s", exc)
        return 0, None


def _score_breakout(df: Any) -> tuple[int, str | None]:
    """돌파: 박스 상단 거래량 동반 돌파 여부 (0~15점)."""
    try:
        import numpy as np
        close = df["Close"].dropna().values
        high = df["High"].dropna().values
        volume = df["Volume"].dropna().values
        n = min(len(close), len(high), len(volume))
        if n < 20:
            return 0, None

        close = close[-n:]
        high = high[-n:]
        volume = volume[-n:]

        # 박스 상단: 최근 20~60일 고점 (제외 최근 5일)
        lookback = min(60, n - 5)
        box_top = float(np.max(high[-(lookback + 5):-5]))
        vol_mean = float(np.mean(volume[:-5])) + 1e-9

        cur_close = float(close[-1])
        cur_vol = float(volume[-1])
        recent_high = float(np.max(high[-5:]))

        breakout_vol_ok = cur_vol > vol_mean * 1.3

        if recent_high > box_top * 1.02 and breakout_vol_ok:
            return 15, f"박스 상단({box_top:,.0f}) 거래량 동반 돌파 가능성"
        elif cur_close > box_top * 0.98 and breakout_vol_ok:
            return 8, f"박스 상단({box_top:,.0f}) 근접 — 돌파 시도 관찰"
        elif cur_close > box_top * 0.95:
            return 3, None

        return 0, None
    except Exception as exc:
        log.debug("[accum] breakout score failed: %s", exc)
        return 0, None


def _score_flow(
    inst_net_5d: float | None,
    inst_net_20d: float | None,
    foreign_net_5d: float | None,
    foreign_net_20d: float | None,
) -> tuple[int, str | None]:
    """수급: 기관/외국인 누적 순매수, 개인 추격매수 여부 (0~15점)."""
    score = 0
    signals: list[str] = []

    if inst_net_5d is not None and inst_net_5d > 0:
        score += 4
        signals.append(f"기관 5일 순매수 +{inst_net_5d:.0f}억")
    if inst_net_20d is not None and inst_net_20d > 0:
        score += 3
        if not signals:
            signals.append(f"기관 20일 순매수 +{inst_net_20d:.0f}억")
    if foreign_net_5d is not None and foreign_net_5d > 0:
        score += 4
        signals.append(f"외국인 5일 순매수 +{foreign_net_5d:.0f}억")
    if foreign_net_20d is not None and foreign_net_20d > 0:
        score += 4
        if len(signals) < 2:
            signals.append(f"외국인 20일 순매수 +{foreign_net_20d:.0f}억")

    # 기관+외국인 동시 누적 보너스
    both_accum = (inst_net_20d or 0) > 0 and (foreign_net_20d or 0) > 0
    if both_accum:
        score += 3
        signals.append("기관·외국인 동반 누적 가능성")

    reason = " / ".join(signals[:2]) if signals else None
    return min(score, 15), reason


def _score_risk(
    df: Any,
    news_texts: list[str],
) -> tuple[int, list[str]]:
    """위험: 고점 대량거래·윗꼬리·CB/BW/유증 등 공시 리스크 (-5 ~ -30점 페널티).

    반환: (페널티점수: 음수, 위험요소 리스트)
    """
    risks: list[str] = []
    penalty = 0

    # 1. 공시/뉴스 키워드 리스크
    found_keywords: list[str] = []
    for text in news_texts:
        for kw in _RISK_KEYWORDS:
            if kw in text and kw not in found_keywords:
                found_keywords.append(kw)
    if found_keywords:
        risks.append(f"리스크 공시 키워드 감지: {', '.join(found_keywords[:3])}")
        penalty -= min(len(found_keywords) * 5, 15)

    # 2. 고점 대량거래 + 윗꼬리
    try:
        import numpy as np
        close = df["Close"].dropna().values[-30:]
        high = df["High"].dropna().values[-30:]
        volume = df["Volume"].dropna().values[-30:]
        n = min(len(close), len(high), len(volume))
        if n >= 10:
            vol_mean = float(np.mean(volume)) + 1e-9
            high_threshold = float(np.percentile(close, 80))
            upper_wick_risk = 0
            for i in range(n):
                bar_range = high[i] - close[i]
                full_range = high[i] - (df["Low"].dropna().values[-n:][i] if len(df["Low"].dropna()) >= n else close[i])
                if full_range > 1e-9:
                    wick_ratio = bar_range / full_range
                    if close[i] > high_threshold and volume[i] > vol_mean * 1.5 and wick_ratio > 0.4:
                        upper_wick_risk += 1
            if upper_wick_risk >= 2:
                risks.append(f"고점 대량거래 + 윗꼬리 {upper_wick_risk}회 — 분산 의심")
                penalty -= min(upper_wick_risk * 5, 10)
    except Exception:
        pass

    # 3. 52주 고점 근접 (매집보다 분산 위험)
    try:
        close_all = df["Close"].dropna().values
        if len(close_all) >= 20:
            high_52 = float(np.max(close_all))
            cur = float(close_all[-1])
            if cur > high_52 * 0.95:
                risks.append("52주 고점 근접 — 분산 가능성 주의")
                penalty -= 5
    except Exception:
        pass

    return penalty, risks[:3]


# ── 메인 함수 ─────────────────────────────────────────────────────────────────

def detect_accumulation(
    symbol: str,
    df: Any,
    inst_net_5d: float | None = None,
    inst_net_20d: float | None = None,
    foreign_net_5d: float | None = None,
    foreign_net_20d: float | None = None,
    news_texts: list[str] | None = None,
) -> AccumulationResult:
    """매집 의심 종합 분석.

    Args:
        symbol:        종목 코드
        df:            OHLCV DataFrame (일봉, 최소 20일, 권장 60~120일)
        inst_net_5d:   기관 5일 순매수 (억원)
        inst_net_20d:  기관 20일 순매수 (억원)
        foreign_net_5d:  외국인 5일 순매수 (억원)
        foreign_net_20d: 외국인 20일 순매수 (억원)
        news_texts:    최근 공시/뉴스 텍스트 리스트

    Returns:
        AccumulationResult
    """
    news_texts = news_texts or []

    # 개별 점수 계산
    pos_score, pos_reason = _score_position(df)
    sup_score, sup_reason = _score_support(df)
    vol_score, vol_reason = _score_volume_pattern(df)
    abs_score, abs_reason = _score_absorption(df)
    spr_score, spr_reason = _score_spring(df)
    brk_score, brk_reason = _score_breakout(df)
    flow_score, flow_reason = _score_flow(inst_net_5d, inst_net_20d, foreign_net_5d, foreign_net_20d)
    risk_penalty, risks = _score_risk(df, news_texts)

    raw_score = pos_score + sup_score + vol_score + abs_score + spr_score + brk_score + flow_score + risk_penalty
    score = max(0, min(100, raw_score))

    # 핵심근거 (양수 점수 높은 순)
    reasons_with_score: list[tuple[int, str]] = []
    for sc, reason in [
        (pos_score, pos_reason),
        (sup_score, sup_reason),
        (vol_score, vol_reason),
        (abs_score, abs_reason),
        (spr_score, spr_reason),
        (brk_score, brk_reason),
        (flow_score, flow_reason),
    ]:
        if reason:
            reasons_with_score.append((sc, reason))
    reasons_with_score.sort(key=lambda x: x[0], reverse=True)
    key_reasons = [r for _, r in reasons_with_score[:3]]

    # 신뢰도: 데이터 충분도 + 신호 수
    try:
        n_rows = len(df["Close"].dropna())
    except Exception:
        n_rows = 0
    signal_count = sum(1 for _, r in reasons_with_score if r)
    if n_rows >= 60 and signal_count >= 3:
        confidence = "높음"
    elif n_rows >= 30 and signal_count >= 2:
        confidence = "보통"
    else:
        confidence = "낮음"

    # 관찰 가격
    support = _calc_support(df)
    resistance = _calc_resistance(df)
    stop_loss = support * 0.97 if support else None
    breakout_confirm = resistance * 1.02 if resistance else None

    # 결론
    if score >= 70:
        conclusion = "매집의심"
    elif score >= 50:
        conclusion = "중립"
    elif score >= 30:
        conclusion = "분산위험"
    else:
        conclusion = "위험주의"

    return AccumulationResult(
        score=score,
        confidence=confidence,
        key_reasons=key_reasons,
        risk_factors=risks,
        support=support,
        resistance=resistance,
        stop_loss=stop_loss,
        breakout_confirm=breakout_confirm,
        conclusion=conclusion,
        component_scores={
            "위치": pos_score,
            "지지": sup_score,
            "거래량": vol_score,
            "흡수": abs_score,
            "스프링": spr_score,
            "돌파": brk_score,
            "수급": flow_score,
            "위험페널티": risk_penalty,
        },
    )


def _calc_support(df: Any) -> float | None:
    """최근 지지선 추정."""
    try:
        import numpy as np
        low = df["Low"].dropna().values
        n = min(len(low), 60)
        recent = low[-n:]
        return float(np.mean(np.sort(recent)[:max(3, n // 10)]))
    except Exception:
        return None


def _calc_resistance(df: Any) -> float | None:
    """최근 저항선 추정."""
    try:
        import numpy as np
        high = df["High"].dropna().values
        n = min(len(high), 60)
        recent = high[-n:]
        return float(np.mean(np.sort(recent)[-max(3, n // 10):]))
    except Exception:
        return None
