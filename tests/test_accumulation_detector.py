"""Tests for accumulation_detector.py."""
from __future__ import annotations

import numpy as np
import pandas as pd


def _make_df(
    n: int = 60,
    trend: str = "flat",  # "down", "up", "flat", "recovery"
    volume_pattern: str = "neutral",  # "accum", "dist", "neutral"
) -> pd.DataFrame:
    """테스트용 OHLCV DataFrame 생성."""
    rng = np.random.default_rng(42)
    base = 10000.0
    closes: list[float] = []

    for i in range(n):
        if trend == "down":
            base *= (1 - 0.003 + rng.normal(0, 0.005))
        elif trend == "up":
            base *= (1 + 0.003 + rng.normal(0, 0.005))
        elif trend == "recovery":
            # 앞 절반 하락, 뒤 절반 상승
            if i < n // 2:
                base *= (1 - 0.004 + rng.normal(0, 0.004))
            else:
                base *= (1 + 0.004 + rng.normal(0, 0.004))
        else:
            base *= (1 + rng.normal(0, 0.008))
        closes.append(max(base, 100.0))

    closes_arr = np.array(closes)
    highs = closes_arr * (1 + np.abs(rng.normal(0, 0.005, n)))
    lows = closes_arr * (1 - np.abs(rng.normal(0, 0.005, n)))
    opens = closes_arr * (1 + rng.normal(0, 0.003, n))

    base_vol = 1_000_000
    if volume_pattern == "accum":
        # 상승 시 거래량 높음
        vols = np.where(
            np.diff(closes_arr, prepend=closes_arr[0]) > 0,
            base_vol * 1.5,
            base_vol * 0.7,
        )
    elif volume_pattern == "dist":
        vols = np.where(
            np.diff(closes_arr, prepend=closes_arr[0]) < 0,
            base_vol * 1.5,
            base_vol * 0.7,
        )
    else:
        vols = np.full(n, base_vol) * (1 + np.abs(rng.normal(0, 0.3, n)))

    return pd.DataFrame({
        "Open": opens,
        "High": highs,
        "Low": lows,
        "Close": closes_arr,
        "Volume": vols.astype(int),
    })


# ── detect_accumulation ───────────────────────────────────────────────────────

def test_detect_accumulation_returns_result():
    from tele_quant.accumulation_detector import detect_accumulation
    df = _make_df(60, trend="flat")
    result = detect_accumulation("TEST", df)
    assert 0 <= result.score <= 100
    assert result.confidence in ("낮음", "보통", "높음")
    assert result.conclusion in ("매집의심", "중립", "분산위험", "위험주의")


def test_detect_accumulation_score_range():
    from tele_quant.accumulation_detector import detect_accumulation
    df = _make_df(80, trend="recovery", volume_pattern="accum")
    result = detect_accumulation(
        "TEST", df,
        inst_net_5d=500.0,
        inst_net_20d=2000.0,
        foreign_net_5d=300.0,
        foreign_net_20d=1200.0,
    )
    assert 0 <= result.score <= 100
    # 양호한 조건이면 중립 이상
    assert result.conclusion in ("매집의심", "중립")


def test_detect_accumulation_risk_keywords():
    from tele_quant.accumulation_detector import detect_accumulation
    df = _make_df(60)
    result = detect_accumulation(
        "TEST", df,
        news_texts=["전환사채 발행 결정", "대주주 매도 공시"],
    )
    assert len(result.risk_factors) > 0
    # 리스크 있으면 점수 깎임
    result_no_risk = detect_accumulation("TEST", df, news_texts=[])
    assert result.score <= result_no_risk.score


def test_detect_accumulation_short_df():
    from tele_quant.accumulation_detector import detect_accumulation
    df = _make_df(10)  # 데이터 부족
    result = detect_accumulation("TEST", df)
    assert result.confidence == "낮음"
    assert 0 <= result.score <= 100


def test_detect_accumulation_key_reasons_max3():
    from tele_quant.accumulation_detector import detect_accumulation
    df = _make_df(90, trend="recovery", volume_pattern="accum")
    result = detect_accumulation("TEST", df, inst_net_5d=100.0, foreign_net_5d=50.0)
    assert len(result.key_reasons) <= 3
    assert len(result.risk_factors) <= 3


def test_detect_accumulation_prices():
    from tele_quant.accumulation_detector import detect_accumulation
    df = _make_df(60)
    result = detect_accumulation("TEST", df)
    if result.support is not None and result.stop_loss is not None:
        assert result.stop_loss < result.support
    if result.resistance is not None and result.breakout_confirm is not None:
        assert result.breakout_confirm > result.resistance


# ── format_accumulation ───────────────────────────────────────────────────────

def test_format_accumulation_contains_score():
    from tele_quant.accumulation_detector import AccumulationResult, format_accumulation
    result = AccumulationResult(
        score=72,
        confidence="높음",
        key_reasons=["기관 순매수 3일 연속"],
        risk_factors=["52주 고점 근접"],
        support=9500.0,
        resistance=11000.0,
        stop_loss=9215.0,
        breakout_confirm=11220.0,
        conclusion="매집의심",
    )
    text = format_accumulation(result)
    assert "72" in text
    assert "매집의심" in text
    assert "9,500" in text
    assert "매수 권장" not in text  # 매수 권장 표현 금지


def test_format_accumulation_no_forbidden_expressions():
    from tele_quant.accumulation_detector import AccumulationResult, format_accumulation
    result = AccumulationResult(
        score=45,
        confidence="보통",
        key_reasons=["거래량 패턴 양호"],
        risk_factors=[],
        conclusion="중립",
    )
    text = format_accumulation(result)
    forbidden = ["매수 권장", "매도 권장", "확정 수익", "자동매매"]
    for f in forbidden:
        assert f not in text, f"금지 표현 '{f}' 발견"


# ── 개별 스코어 함수 ──────────────────────────────────────────────────────────

def test_score_position_bottom_zone():
    from tele_quant.accumulation_detector import _score_position
    df = _make_df(100, trend="down")
    score, _ = _score_position(df)
    assert score >= 10  # 하락 후 바닥권이면 점수 높음


def test_score_position_top_zone():
    from tele_quant.accumulation_detector import _score_position
    df = _make_df(100, trend="up")
    score, _ = _score_position(df)
    assert score <= 10  # 상승 후 고점권이면 점수 낮음


def test_score_volume_pattern_accum():
    from tele_quant.accumulation_detector import _score_volume_pattern
    df = _make_df(60, volume_pattern="accum")
    score, _ = _score_volume_pattern(df)
    assert score >= 0


def test_score_flow_positive():
    from tele_quant.accumulation_detector import _score_flow
    score, reason = _score_flow(500.0, 2000.0, 300.0, 1200.0)
    assert score > 0
    assert reason is not None


def test_score_flow_negative():
    from tele_quant.accumulation_detector import _score_flow
    score, _reason = _score_flow(-100.0, -500.0, -50.0, -200.0)
    assert score == 0


def test_score_risk_with_keywords():
    from tele_quant.accumulation_detector import _score_risk
    df = _make_df(30)
    penalty, risks = _score_risk(df, ["전환사채 발행", "유상증자 결정"])
    assert penalty < 0
    assert len(risks) > 0


def test_score_risk_no_keywords():
    from tele_quant.accumulation_detector import _score_risk
    df = _make_df(30)
    penalty, _risks = _score_risk(df, [])
    # 키워드 없으면 공시 페널티 없음 (차트 기반 페널티만 가능)
    assert penalty <= 0
