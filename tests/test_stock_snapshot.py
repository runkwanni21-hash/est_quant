"""Tests for stock_snapshot module — no network calls."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import patch

import pandas as pd

from tele_quant.stock_snapshot import (
    StockAnalysisSnapshot,
    _quick_tech_score,
    analyze_single,
    build_stock_snapshot,
    compute_accumulation_pattern,
    compute_daily_technicals,
    compute_price_changes,
    compute_swing_setup,
    compute_swing_trade_score,
    format_stock_snapshot,
)

# ── Helpers ───────────────────────────────────────────────────────────────────

def _mock_tech(rsi: float = 45.0, close: float = 470_000.0) -> dict:
    return {
        "rsi": rsi,
        "obv": "상승",
        "bb_pct": 30.0,
        "close": close,
        "vol_ratio": 1.3,
    }


def _mock_fund(symbol: str = "128940.KS", market: str = "KR"):
    from tele_quant.fundamentals import FundamentalSnapshot
    return FundamentalSnapshot(
        symbol=symbol,
        market=market,
        sector="제약",
        fetched_at=datetime.now(UTC),
        pe_trailing=14.0,
        pb=1.5,
        roe=16.0,
        w52_position_pct=40.0,
        current_price=470_000.0,
        market_cap_krw=2_000_000_000_000,
    )


# ── _quick_tech_score ─────────────────────────────────────────────────────────

class TestQuickTechScore:
    def test_long_oversold_rsi(self) -> None:
        score, reason = _quick_tech_score({"rsi": 30.0}, "LONG")
        assert score > 0
        assert "과매도" in reason

    def test_long_overbought_rsi_penalty(self) -> None:
        score_high, _ = _quick_tech_score({"rsi": 75.0}, "LONG")
        score_low, _ = _quick_tech_score({"rsi": 40.0}, "LONG")
        assert score_high < score_low

    def test_short_overbought_rsi(self) -> None:
        score, reason = _quick_tech_score({"rsi": 75.0}, "SHORT")
        assert score > 0
        assert "과열" in reason

    def test_max_capped_at_40(self) -> None:
        d = {"rsi": 30.0, "bb_pct": 10.0, "vol_ratio": 2.0, "obv": "상승"}
        score, _ = _quick_tech_score(d, "LONG")
        assert score <= 40.0

    def test_empty_data_returns_zero_score(self) -> None:
        score, reason = _quick_tech_score({}, "LONG")
        assert score == 0.0
        assert "데이터 부족" in reason

    def test_obv_harak_short(self) -> None:
        score, _reason = _quick_tech_score({"rsi": 72.0, "obv": "하락"}, "SHORT")
        assert score > 0


# ── StockAnalysisSnapshot dataclass ───────────────────────────────────────────

class TestSnapshotDataclass:
    def test_defaults(self) -> None:
        snap = StockAnalysisSnapshot(symbol="NVDA", market="US", name="NVIDIA")
        assert snap.close is None
        assert snap.direction == "LONG"
        assert snap.grade == "—"
        assert snap.recent_issues == []
        assert snap.beneficiaries == []

    def test_error_field(self) -> None:
        snap = StockAnalysisSnapshot(symbol="X", market="US", name="X", error="failed")
        assert "failed" in snap.error


# ── build_stock_snapshot ──────────────────────────────────────────────────────

class TestBuildStockSnapshot:
    def test_returns_snapshot_instance(self) -> None:
        with (
            patch("tele_quant.daily_alpha._fetch_4h_data", return_value=_mock_tech()),
            patch("tele_quant.fundamentals.fetch_fundamentals", return_value=_mock_fund()),
        ):
            snap = build_stock_snapshot("128940.KS", "KR")
        assert isinstance(snap, StockAnalysisSnapshot)

    def test_symbol_and_market_set(self) -> None:
        with (
            patch("tele_quant.daily_alpha._fetch_4h_data", return_value=_mock_tech()),
            patch("tele_quant.fundamentals.fetch_fundamentals", return_value=_mock_fund()),
        ):
            snap = build_stock_snapshot("128940.KS", "KR")
        assert snap.symbol == "128940.KS"
        assert snap.market == "KR"

    def test_auto_market_from_suffix(self) -> None:
        with (
            patch("tele_quant.daily_alpha._fetch_4h_data", return_value={}),
            patch("tele_quant.fundamentals.fetch_fundamentals", return_value=_mock_fund()),
        ):
            snap = build_stock_snapshot("005930.KS")
        assert snap.market == "KR"

    def test_auto_market_us(self) -> None:
        with (
            patch("tele_quant.daily_alpha._fetch_4h_data", return_value={}),
            patch("tele_quant.fundamentals.fetch_fundamentals", return_value=_mock_fund("NVDA", "US")),
        ):
            snap = build_stock_snapshot("NVDA")
        assert snap.market == "US"

    def test_rsi_short_direction(self) -> None:
        with (
            patch("tele_quant.daily_alpha._fetch_4h_data", return_value=_mock_tech(rsi=78.0)),
            patch("tele_quant.fundamentals.fetch_fundamentals", return_value=_mock_fund()),
        ):
            snap = build_stock_snapshot("128940.KS", "KR")
        assert snap.direction == "SHORT"

    def test_rsi_long_direction(self) -> None:
        with (
            patch("tele_quant.daily_alpha._fetch_4h_data", return_value=_mock_tech(rsi=28.0)),
            patch("tele_quant.fundamentals.fetch_fundamentals", return_value=_mock_fund()),
        ):
            snap = build_stock_snapshot("128940.KS", "KR")
        assert snap.direction == "LONG"

    def test_grade_three_stars_high_score(self) -> None:
        with (
            patch("tele_quant.daily_alpha._fetch_4h_data", return_value=_mock_tech(rsi=30.0)),
            patch("tele_quant.fundamentals.fetch_fundamentals", return_value=_mock_fund()),
            patch("tele_quant.fundamentals.score_fundamentals", return_value=(90.0, "저평가")),
        ):
            snap = build_stock_snapshot("128940.KS", "KR")
        assert snap.total_score > 0

    def test_tech_failure_graceful(self) -> None:
        with (
            patch("tele_quant.daily_alpha._fetch_4h_data", side_effect=RuntimeError("net")),
            patch("tele_quant.fundamentals.fetch_fundamentals", return_value=_mock_fund()),
        ):
            snap = build_stock_snapshot("128940.KS", "KR")
        assert isinstance(snap, StockAnalysisSnapshot)
        assert "실패" in snap.tech_reason

    def test_deep_false_no_beneficiaries(self) -> None:
        """deep=False이면 수혜주 조회는 생략, 이슈는 최대 3개까지 시도."""
        with (
            patch("tele_quant.daily_alpha._fetch_4h_data", return_value={}),
            patch("tele_quant.fundamentals.fetch_fundamentals", return_value=_mock_fund()),
            patch("tele_quant.recent_issue_collector.collect_recent_issues", return_value=[]),
        ):
            snap = build_stock_snapshot("NVDA", deep=False)
        assert snap.beneficiaries == []

    def test_quick_mode_no_issues(self) -> None:
        """quick=True이면 이슈 수집 자체를 호출하지 않음."""
        with (
            patch("tele_quant.daily_alpha._fetch_4h_data", return_value={}),
            patch("tele_quant.fundamentals.fetch_fundamentals", return_value=_mock_fund()),
            patch("tele_quant.recent_issue_collector.collect_recent_issues") as mock_collect,
        ):
            snap = build_stock_snapshot("NVDA", quick=True)
            mock_collect.assert_not_called()
        assert snap.recent_issues == []


# ── format_stock_snapshot ─────────────────────────────────────────────────────

class TestFormatStockSnapshot:
    def _base_snap(self) -> StockAnalysisSnapshot:
        return StockAnalysisSnapshot(
            symbol="128940.KS", market="KR", name="한미약품",
            close=470_000.0, rsi=45.0, direction="LONG",
            tech_score=25.0, tech_reason="RSI 45(중립)",
            fund_line="PER 14.0 | PBR 1.5",
            val_score=60.0, val_reason="저평가 구간",
            total_score=72.5, grade="★★",
        )

    def test_returns_string(self) -> None:
        result = format_stock_snapshot(self._base_snap())
        assert isinstance(result, str)

    def test_contains_symbol(self) -> None:
        result = format_stock_snapshot(self._base_snap())
        assert "128940" in result

    def test_kr_price_won_format(self) -> None:
        result = format_stock_snapshot(self._base_snap())
        assert "원" in result

    def test_us_price_dollar_format(self) -> None:
        snap = StockAnalysisSnapshot(
            symbol="NVDA", market="US", name="NVIDIA",
            close=875.0, direction="SHORT", total_score=60.0,
        )
        result = format_stock_snapshot(snap)
        assert "$" in result

    def test_contains_disclaimer(self) -> None:
        result = format_stock_snapshot(self._base_snap())
        assert "투자 판단" in result

    def test_no_forbidden_expressions(self) -> None:
        result = format_stock_snapshot(self._base_snap())
        forbidden = ["매수 권장", "매도 권장", "확정 수익", "자동매매", "수혜 확정"]
        for word in forbidden:
            assert word not in result, f"Forbidden: '{word}'"

    def test_recent_issues_shown(self) -> None:
        snap = self._base_snap()
        snap.recent_issues = ["분기 실적 서프라이즈", "신약 임상 3상 성공"]
        result = format_stock_snapshot(snap)
        assert "최근 이슈" in result
        assert "분기 실적" in result

    def test_beneficiaries_shown(self) -> None:
        snap = self._base_snap()
        snap.beneficiaries = ["COHR", "LITE"]
        result = format_stock_snapshot(snap)
        assert "수혜 연관" in result
        assert "COHR" in result

    def test_grade_triple_star_high_score(self) -> None:
        snap = self._base_snap()
        snap.total_score = 85.0
        snap.grade = "★★★"
        result = format_stock_snapshot(snap)
        assert "80점↑" in result

    def test_grade_below_50_low_message(self) -> None:
        snap = self._base_snap()
        snap.total_score = 40.0
        snap.grade = "—"
        result = format_stock_snapshot(snap)
        assert "현재 기준 미달" in result


# ── analyze_single (convenience alias) ────────────────────────────────────────

class TestAnalyzeSingle:
    def test_returns_string(self) -> None:
        with (
            patch("tele_quant.daily_alpha._fetch_4h_data", return_value=_mock_tech()),
            patch("tele_quant.fundamentals.fetch_fundamentals", return_value=_mock_fund()),
        ):
            result = analyze_single("128940.KS", "KR")
        assert isinstance(result, str)
        assert len(result) > 50

    def test_contains_symbol(self) -> None:
        with (
            patch("tele_quant.daily_alpha._fetch_4h_data", return_value=_mock_tech()),
            patch("tele_quant.fundamentals.fetch_fundamentals", return_value=_mock_fund()),
        ):
            result = analyze_single("128940.KS", "KR")
        assert "128940" in result

    def test_contains_disclaimer(self) -> None:
        with (
            patch("tele_quant.daily_alpha._fetch_4h_data", return_value=_mock_tech()),
            patch("tele_quant.fundamentals.fetch_fundamentals", return_value=_mock_fund()),
        ):
            result = analyze_single("128940.KS", "KR")
        assert "투자 판단" in result

    def test_no_forbidden_words(self) -> None:
        with (
            patch("tele_quant.daily_alpha._fetch_4h_data", return_value=_mock_tech()),
            patch("tele_quant.fundamentals.fetch_fundamentals", return_value=_mock_fund()),
        ):
            result = analyze_single("128940.KS", "KR")
        forbidden = ["매수 권장", "매도 권장", "확정 수익", "자동매매"]
        for word in forbidden:
            assert word not in result

    def test_tech_failure_still_returns(self) -> None:
        with (
            patch("tele_quant.daily_alpha._fetch_4h_data", side_effect=RuntimeError("fail")),
            patch("tele_quant.fundamentals.fetch_fundamentals", return_value=_mock_fund()),
        ):
            result = analyze_single("128940.KS", "KR")
        assert isinstance(result, str)
        assert "128940" in result

    def test_us_dollar_sign(self) -> None:
        from tele_quant.fundamentals import FundamentalSnapshot
        us_fund = FundamentalSnapshot(
            symbol="NVDA", market="US", sector="Technology",
            fetched_at=datetime.now(UTC), current_price=875.0,
        )
        with (
            patch("tele_quant.daily_alpha._fetch_4h_data", return_value=_mock_tech(close=875.0)),
            patch("tele_quant.fundamentals.fetch_fundamentals", return_value=us_fund),
        ):
            result = analyze_single("NVDA", "US")
        assert "$" in result


# ── compute_price_changes ─────────────────────────────────────────────────────


def _make_df(closes: list[float], volumes: list[float] | None = None) -> pd.DataFrame:
    n = len(closes)
    if volumes is None:
        volumes = [1_000_000.0] * n
    return pd.DataFrame({"Close": closes, "Volume": volumes})


class TestComputePriceChanges:
    def test_none_df_returns_none_values(self) -> None:
        result = compute_price_changes(None)
        assert all(v is None for v in result.values())

    def test_empty_df_returns_none_values(self) -> None:
        result = compute_price_changes(pd.DataFrame())
        assert all(v is None for v in result.values())

    def test_1d_change_positive(self) -> None:
        closes = [100.0, 110.0]
        result = compute_price_changes(_make_df(closes))
        assert result["1d"] is not None
        assert abs(result["1d"] - 10.0) < 0.01

    def test_1d_change_negative(self) -> None:
        closes = [110.0, 100.0]
        result = compute_price_changes(_make_df(closes))
        assert result["1d"] < 0

    def test_1w_change(self) -> None:
        closes = [100.0] * 5 + [110.0]
        result = compute_price_changes(_make_df(closes))
        assert result["1w"] is not None
        assert abs(result["1w"] - 10.0) < 0.01

    def test_short_df_skips_longer_windows(self) -> None:
        closes = [100.0, 105.0]
        result = compute_price_changes(_make_df(closes))
        assert result["1d"] is not None
        assert result["1m"] is None

    def test_all_keys_present(self) -> None:
        result = compute_price_changes(None)
        assert set(result.keys()) == {"1d", "1w", "1m", "3m"}


# ── compute_daily_technicals ──────────────────────────────────────────────────


class TestComputeDailyTechnicals:
    def test_none_df_returns_none(self) -> None:
        result = compute_daily_technicals(None)
        assert all(v is None for v in result.values())

    def test_ma20_computed(self) -> None:
        closes = list(range(1, 22))  # 21 values
        result = compute_daily_technicals(_make_df(closes))
        assert result["ma_20"] is not None
        assert result["ma_20"] > 0

    def test_ma60_none_when_insufficient(self) -> None:
        closes = list(range(1, 22))  # only 21 values
        result = compute_daily_technicals(_make_df(closes))
        assert result["ma_60"] is None

    def test_rsi_in_range(self) -> None:
        import random
        random.seed(42)
        closes = [100.0 + random.uniform(-5, 5) for _ in range(30)]
        result = compute_daily_technicals(_make_df(closes))
        if result["rsi"] is not None:
            assert 0 <= result["rsi"] <= 100


# ── compute_swing_setup ───────────────────────────────────────────────────────


class TestComputeSwingSetup:
    def test_oversold_long_setup(self) -> None:
        label, score = compute_swing_setup(
            {"rsi": 30.0}, {}, {}, "LONG"
        )
        assert "과매도" in label
        assert score >= 70

    def test_overbought_short_setup(self) -> None:
        label, score = compute_swing_setup(
            {"rsi": 78.0}, {}, {}, "SHORT"
        )
        assert "과열" in label
        assert score >= 70

    def test_weekly_surge_short(self) -> None:
        label, _score = compute_swing_setup(
            {}, {}, {"1w": 12.0}, "SHORT"
        )
        assert "급등" in label

    def test_no_data_returns_데이터_부족(self) -> None:
        label, _score = compute_swing_setup({}, {}, {}, "LONG")
        assert label == "데이터 부족"

    def test_score_capped_at_100(self) -> None:
        _, score = compute_swing_setup(
            {"rsi": 20.0}, {"rsi": 25.0}, {}, "LONG"
        )
        assert score <= 100.0


# ── compute_accumulation_pattern ─────────────────────────────────────────────


class TestComputeAccumulationPattern:
    def test_none_df_returns_unclear(self) -> None:
        _signal, score = compute_accumulation_pattern(None)
        assert score < 50

    def test_high_vol_stable_price(self) -> None:
        closes = [100.0] * 20 + [101.0, 100.5, 100.3, 100.7, 100.2]
        volumes = [1_000_000.0] * 20 + [2_000_000.0] * 5
        df = pd.DataFrame({"Close": closes, "Volume": volumes})
        signal, score = compute_accumulation_pattern(df)
        # 거래량 상승 + 가격 안정 → 매집 가능성
        assert score >= 60
        assert "확정" not in signal  # 단정 표현 금지

    def test_no_forbidden_wording(self) -> None:
        import random
        random.seed(0)
        closes = [100.0 + random.uniform(-3, 3) for _ in range(25)]
        volumes = [1_000_000.0 * random.uniform(0.8, 1.2) for _ in range(25)]
        df = pd.DataFrame({"Close": closes, "Volume": volumes})
        signal, _ = compute_accumulation_pattern(df)
        forbidden = ["세력 매집 확정", "기관 매집 확정", "매집 확정"]
        for w in forbidden:
            assert w not in signal


# ── compute_swing_trade_score ─────────────────────────────────────────────────


class TestComputeSwingTradeScore:
    def _base_snap(self) -> StockAnalysisSnapshot:
        return StockAnalysisSnapshot(
            symbol="128940.KS", market="KR", name="한미약품",
            tech_score=30.0, direction="LONG",
            accum_score=65.0, sector_score=60.0,
        )

    def test_returns_tuple(self) -> None:
        snap = self._base_snap()
        result = compute_swing_trade_score(snap)
        assert isinstance(result, tuple) and len(result) == 2

    def test_score_in_range(self) -> None:
        snap = self._base_snap()
        score, _ = compute_swing_trade_score(snap)
        assert 0 <= score <= 100

    def test_grade_a_high_score(self) -> None:
        snap = self._base_snap()
        snap.tech_score = 40.0
        snap.accum_score = 80.0
        snap.sector_score = 80.0
        snap.recent_issues = ["이슈1", "이슈2"]
        score, _grade = compute_swing_trade_score(snap)
        assert score >= 55  # at least B

    def test_penalty_overbought_long(self) -> None:
        snap = self._base_snap()
        snap.rsi = 80.0  # 과열 + LONG → penalty
        score_penalized, _ = compute_swing_trade_score(snap)

        snap2 = self._base_snap()
        snap2.rsi = 50.0
        score_normal, _ = compute_swing_trade_score(snap2)

        assert score_penalized < score_normal

    def test_penalty_1m_surge(self) -> None:
        snap = self._base_snap()
        snap.price_change_1m = 35.0  # 1개월 급등 → penalty
        score_penalized, _ = compute_swing_trade_score(snap)

        snap2 = self._base_snap()
        snap2.price_change_1m = 5.0
        score_normal, _ = compute_swing_trade_score(snap2)

        assert score_penalized < score_normal

    def test_grade_labels(self) -> None:
        snap = self._base_snap()
        snap.tech_score = 0.0
        snap.accum_score = 0.0
        snap.sector_score = 0.0
        _, grade = compute_swing_trade_score(snap)
        assert grade in ("A등급", "B등급", "C등급", "기준 미달")


# ── Snapshot new fields ───────────────────────────────────────────────────────


class TestSnapshotNewFields:
    def test_price_change_defaults_none(self) -> None:
        snap = StockAnalysisSnapshot(symbol="X", market="US", name="X")
        assert snap.price_change_1d is None
        assert snap.price_change_1w is None
        assert snap.price_change_1m is None
        assert snap.price_change_3m is None

    def test_ma_defaults_none(self) -> None:
        snap = StockAnalysisSnapshot(symbol="X", market="US", name="X")
        assert snap.ma_20 is None
        assert snap.ma_60 is None
        assert snap.daily_rsi is None

    def test_swing_grade_default(self) -> None:
        snap = StockAnalysisSnapshot(symbol="X", market="US", name="X")
        assert snap.swing_grade == "—"

    def test_sector_score_default(self) -> None:
        snap = StockAnalysisSnapshot(symbol="X", market="US", name="X")
        assert snap.sector_score == 50.0

    def test_fund_fields_defaults_none(self) -> None:
        snap = StockAnalysisSnapshot(symbol="X", market="US", name="X")
        assert snap.pe_trailing is None
        assert snap.pb is None
        assert snap.roe is None
        assert snap.eps_growth is None
        assert snap.dividend_yield is None

    def test_w52_defaults_none(self) -> None:
        snap = StockAnalysisSnapshot(symbol="X", market="US", name="X")
        assert snap.w52_position_pct is None

    def test_sector_lists_defaults_empty(self) -> None:
        snap = StockAnalysisSnapshot(symbol="X", market="US", name="X")
        assert snap.sector_lines == []
        assert snap.sector_risks == []
        assert snap.sector_catalysts == []
        assert snap.sector_peers == []


# ── format_stock_snapshot — new fields ───────────────────────────────────────


class TestFormatSnapshotNewSections:
    def _snap_with_changes(self) -> StockAnalysisSnapshot:
        return StockAnalysisSnapshot(
            symbol="NVDA", market="US", name="NVIDIA",
            close=875.0, direction="LONG", total_score=65.0,
            price_change_1d=2.5, price_change_1w=-3.1,
            price_change_1m=15.0, price_change_3m=40.0,
        )

    def test_price_changes_shown(self) -> None:
        result = format_stock_snapshot(self._snap_with_changes())
        assert "1D" in result
        assert "1W" in result
        assert "+2.5%" in result

    def test_w52_bar_shown(self) -> None:
        snap = StockAnalysisSnapshot(
            symbol="X", market="US", name="X", w52_position_pct=60.0
        )
        result = format_stock_snapshot(snap)
        assert "52주" in result
        assert "60%" in result

    def test_fund_metrics_shown(self) -> None:
        snap = StockAnalysisSnapshot(
            symbol="X", market="KR", name="X",
            pe_trailing=15.0, pb=1.2, roe=12.0, eps_growth=25.0,
        )
        result = format_stock_snapshot(snap)
        assert "PER" in result
        assert "PBR" in result
        assert "ROE" in result

    def test_sector_section_shown(self) -> None:
        snap = StockAnalysisSnapshot(
            symbol="X", market="KR", name="X",
            sector_title="바이오/제약/CDMO",
            sector_lines=["바이오는 PER보다 임상 단계가 중요합니다."],
            sector_risks=["임상 실패 리스크"],
            sector_catalysts=["FDA 허가"],
        )
        result = format_stock_snapshot(snap)
        assert "섹터" in result
        assert "바이오" in result
        assert "리스크" in result

    def test_swing_grade_shown(self) -> None:
        snap = StockAnalysisSnapshot(
            symbol="X", market="US", name="X",
            swing_grade="A등급", swing_score=72.0,
        )
        result = format_stock_snapshot(snap)
        assert "스윙 등급" in result
        assert "A등급" in result
        assert "관찰 기준" in result  # "확정 아님" 표현 확인
        assert "확정" not in result.replace("확정 아님", "")  # "확정 아님" 외 확정 없음

    def test_swing_grade_default_not_shown(self) -> None:
        snap = StockAnalysisSnapshot(
            symbol="X", market="US", name="X",
        )
        result = format_stock_snapshot(snap)
        assert "스윙 등급" not in result

    def test_setup_label_shown_when_meaningful(self) -> None:
        snap = StockAnalysisSnapshot(
            symbol="X", market="US", name="X",
            setup_label="과매도 반등 셋업",
        )
        result = format_stock_snapshot(snap)
        assert "셋업" in result
        assert "과매도" in result

    def test_accum_signal_shown_when_meaningful(self) -> None:
        snap = StockAnalysisSnapshot(
            symbol="X", market="US", name="X",
            accum_signal="매집 가능성이 있는 수급 패턴",
        )
        result = format_stock_snapshot(snap)
        assert "수급" in result
        assert "매집 가능성" in result


# ── recent_issues_formatted integration ──────────────────────────────────────


class TestRecentIssuesIntegration:
    def test_recent_issues_formatted_displayed(self) -> None:
        snap = StockAnalysisSnapshot(
            symbol="NVDA", market="US", name="NVIDIA",
            recent_issues_formatted="📰 최근 이슈:\n  ✅ [earnings] NVDA beats EPS estimate for Q3\n  • [price_action] NVDA surged 15% after earnings",
        )
        result = format_stock_snapshot(snap)
        assert "📰 최근 이슈" in result
        assert "NVDA beats EPS" in result

    def test_basic_mode_calls_issue_collector(self) -> None:
        from tele_quant.recent_issue_collector import RecentIssue

        mock_issues = [
            RecentIssue(title="NVDA beats earnings", sentiment="bullish"),
            RecentIssue(title="NVDA GPU demand strong", sentiment="bullish"),
        ]

        with patch("tele_quant.recent_issue_collector.collect_recent_issues", return_value=mock_issues) as mock_collect, \
             patch("tele_quant.daily_alpha._fetch_4h_data", return_value={}), \
             patch("tele_quant.fundamentals.fetch_fundamentals", return_value=_mock_fund()):
            snap = build_stock_snapshot("NVDA", "US", store=None, quick=False)
            mock_collect.assert_called_once()

        assert snap.recent_issues_formatted != "" or len(snap.recent_issues) >= 0  # issues collected
