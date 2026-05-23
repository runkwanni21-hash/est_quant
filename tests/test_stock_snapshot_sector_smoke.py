"""sector-aware 출력 검증 + stock snapshot smoke 안정화.

두 가지 목표:
1. format_stock_snapshot()이 sector_intelligence_text를 올바르게 포함하는지 검증
2. 10개 대표 티커에 대해 네트워크 없이 build_stock_snapshot → format 전 과정이
   크래시 없이 완주하고, 금지 표현이 없는지 확인

공개 정보 기반 리서치 보조. 투자 판단 책임은 사용자에게 있음.
"""
from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from tele_quant.sector_intelligence import (
    SectorIntelligence,
    build_sector_intelligence,
    format_sector_intelligence,
)
from tele_quant.stock_snapshot import (
    StockAnalysisSnapshot,
    build_stock_snapshot,
    format_stock_snapshot,
)

# ── 금지 표현 목록 ────────────────────────────────────────────────────────────

_FORBIDDEN = [
    "매수 권장",
    "매도 권장",
    "확정 수익",
    "수익 보장",
    "반드시 상승",
    "세력 매집 확정",
    "기관 매집 확정",
    "수혜 확정",
    "피해 확정",
    "4H 매매 어드바이징",
]


def _no_forbidden(text: str) -> None:
    for w in _FORBIDDEN:
        assert w not in text, f"금지 표현 발견: '{w}'"


# ── Sector intelligence YAML 기반 컨텐츠 검증 ────────────────────────────────


class TestSectorIntelligenceContent:
    """build_sector_intelligence + format_sector_intelligence → 섹터별 키워드 검증."""

    def _build(self, sector_id: str, **kwargs) -> SectorIntelligence | None:
        default_fund = {"pe_forward": 25.0, "roe": 20.0}
        return build_sector_intelligence(
            symbol=kwargs.get("symbol", "TEST"),
            name=kwargs.get("name", "Test"),
            market=kwargs.get("market", "US"),
            sector_id=sector_id,
            price_snapshot={"1w": 2.0, "1m": 8.0},
            fundamental_snapshot=kwargs.get("fundamental_snapshot", default_fund),
        )

    def test_semiconductor_not_none(self) -> None:
        intel = self._build("ai_semiconductor_hbm_foundry")
        assert intel is not None

    def test_semiconductor_title_contains_keyword(self) -> None:
        intel = self._build("ai_semiconductor_hbm_foundry")
        assert intel is not None
        assert "반도체" in intel.title or "HBM" in intel.title or "파운드리" in intel.title

    def test_semiconductor_key_metrics_include_hbm(self) -> None:
        intel = self._build("ai_semiconductor_hbm_foundry")
        assert intel is not None
        combined = " ".join(intel.key_metrics)
        assert "HBM" in combined or "CAPEX" in combined or "파운드리" in combined

    def test_semiconductor_valuation_note_enriched(self) -> None:
        intel = self._build("ai_semiconductor_hbm_foundry")
        assert intel is not None
        # enrich_sector_intelligence가 pe_note 채워야 함
        assert intel.valuation_note != ""

    def test_semiconductor_catalysts_present(self) -> None:
        intel = self._build("ai_semiconductor_hbm_foundry")
        assert intel is not None
        assert len(intel.catalysts) >= 1

    def test_semiconductor_risks_present(self) -> None:
        intel = self._build("ai_semiconductor_hbm_foundry")
        assert intel is not None
        assert len(intel.risks) >= 1

    def test_biotech_title_contains_keyword(self) -> None:
        with patch("tele_quant.clinical_pipeline.fetch_clinical_pipeline") as mock_cp:
            mock_cp.return_value = MagicMock(
                trials=[],
                headline_signals=[],
                cash_burn_note="",
                partner_note="",
                market_note="",
                data_limited=True,
                limitation_note="공개자료 기준 확인 제한",
            )
            intel = self._build(
                "biotech_pharma_clinical_medtech",
                symbol="128940.KS",
                name="한미약품",
                market="KR",
            )
        assert intel is not None
        assert "바이오" in intel.title or "제약" in intel.title or "임상" in intel.title

    def test_biotech_key_metrics_clinical(self) -> None:
        with patch("tele_quant.clinical_pipeline.fetch_clinical_pipeline") as mock_cp:
            mock_cp.return_value = MagicMock(
                trials=[],
                headline_signals=[],
                cash_burn_note="",
                partner_note="",
                market_note="",
                data_limited=True,
                limitation_note="공개자료 기준 확인 제한",
            )
            intel = self._build("biotech_pharma_clinical_medtech")
        assert intel is not None
        combined = " ".join(intel.key_metrics)
        assert "임상" in combined or "현금" in combined or "burn" in combined.lower()

    def test_saas_key_metrics_arr(self) -> None:
        intel = self._build("ai_software_cloud_cybersecurity")
        assert intel is not None
        combined = " ".join(intel.key_metrics)
        assert "ARR" in combined or "NRR" in combined or "Rule of 40" in combined

    def test_saas_rule40_computed_when_data_available(self) -> None:
        intel = self._build(
            "ai_software_cloud_cybersecurity",
            fundamental_snapshot={"pe_forward": 55.0, "roe": 30.0,
                                   "revenue_growth": 22.0, "op_margin": 26.0},
        )
        assert intel is not None
        text = format_sector_intelligence(intel)
        assert "Rule of 40" in text
        assert "48.0" in text  # 22 + 26 = 48
        assert "충족" in text

    def test_saas_rule40_boundary(self) -> None:
        intel = self._build(
            "ai_software_cloud_cybersecurity",
            fundamental_snapshot={"revenue_growth": 9.0, "op_margin": 22.0},
        )
        assert intel is not None
        text = format_sector_intelligence(intel)
        assert "Rule of 40" in text
        assert "경계" in text  # 9+22=31 → 경계

    def test_saas_rule40_below(self) -> None:
        intel = self._build(
            "ai_software_cloud_cybersecurity",
            fundamental_snapshot={"revenue_growth": 8.0, "op_margin": 5.0},
        )
        assert intel is not None
        text = format_sector_intelligence(intel)
        assert "Rule of 40" in text
        assert "미충족" in text  # 8+5=13

    def test_saas_arr_nrr_disclaimer(self) -> None:
        intel = self._build(
            "ai_software_cloud_cybersecurity",
            fundamental_snapshot={"revenue_growth": 18.0, "op_margin": 25.0},
        )
        assert intel is not None
        text = format_sector_intelligence(intel)
        assert "ARR" in text or "NRR" in text  # 핵심지표 또는 disclaimer에 있어야 함

    def test_saas_no_data_shows_fallback(self) -> None:
        intel = self._build(
            "ai_software_cloud_cybersecurity",
            fundamental_snapshot={},  # 데이터 없음
        )
        assert intel is not None
        text = format_sector_intelligence(intel)
        assert "Rule of 40" in text or "SaaS" in text  # fallback 메시지 존재

    def test_shipbuilding_key_metrics_backlog(self) -> None:
        intel = self._build(
            "shipbuilding_shipping_lng_equipment",
            symbol="329180.KS",
            name="HD현대중공업",
            market="KR",
        )
        assert intel is not None
        combined = " ".join(intel.key_metrics)
        assert "수주" in combined or "CGT" in combined or "선가" in combined

    def test_semicap_valuation_note(self) -> None:
        intel = self._build("semicap_equipment_materials_osat")
        assert intel is not None
        assert intel.valuation_note != ""

    def test_format_semiconductor_no_forbidden(self) -> None:
        intel = self._build("ai_semiconductor_hbm_foundry")
        assert intel is not None
        text = format_sector_intelligence(intel)
        _no_forbidden(text)

    def test_format_biotech_no_forbidden(self) -> None:
        with patch("tele_quant.clinical_pipeline.fetch_clinical_pipeline") as mock_cp:
            mock_cp.return_value = MagicMock(
                trials=[],
                headline_signals=[],
                cash_burn_note="",
                partner_note="",
                market_note="",
                data_limited=True,
                limitation_note="공개자료 기준 확인 제한",
            )
            intel = self._build("biotech_pharma_clinical_medtech")
        assert intel is not None
        text = format_sector_intelligence(intel)
        _no_forbidden(text)

    def test_format_saas_rule_of_40(self) -> None:
        intel = self._build("ai_software_cloud_cybersecurity")
        assert intel is not None
        text = format_sector_intelligence(intel)
        assert "ARR" in text or "NRR" in text or "Rule of 40" in text

    def test_format_shipbuilding_backlog(self) -> None:
        intel = self._build("shipbuilding_shipping_lng_equipment")
        assert intel is not None
        text = format_sector_intelligence(intel)
        assert "수주" in text or "조선" in text

    def test_format_financial_has_nim_or_pbr(self) -> None:
        intel = self._build(
            "financials_banks_insurance_brokers",
            fundamental_snapshot={"pe_forward": 8.0, "roe": 10.0},
        )
        assert intel is not None
        text = format_sector_intelligence(intel)
        assert "NIM" in text or "PBR" in text or "배당" in text or "금융" in text

    def test_format_always_has_sector_title(self) -> None:
        for sector_id in [
            "ai_semiconductor_hbm_foundry",
            "ai_software_cloud_cybersecurity",
            "auto_ev_battery_robotaxi",
        ]:
            intel = self._build(sector_id)
            if intel is None:
                continue
            text = format_sector_intelligence(intel)
            assert intel.title in text


# ── sector_intelligence_text 가 format_stock_snapshot에 포함되는지 ──────────


class TestFormatSnapshotSectorIntelText:
    def test_sector_intelligence_text_shown(self) -> None:
        snap = StockAnalysisSnapshot(
            symbol="NVDA",
            market="US",
            name="NVIDIA",
            sector_intelligence_text="🔍 AI 반도체 분석:\n  HBM 수요 확인 필요",
        )
        result = format_stock_snapshot(snap)
        assert "AI 반도체" in result
        assert "HBM 수요" in result

    def test_sector_intelligence_text_empty_not_shown(self) -> None:
        snap = StockAnalysisSnapshot(
            symbol="NVDA",
            market="US",
            name="NVIDIA",
            sector_intelligence_text="",
        )
        result = format_stock_snapshot(snap)
        assert "AI 반도체" not in result

    def test_val_reason_no_duplicate_roe(self) -> None:
        snap = StockAnalysisSnapshot(
            symbol="005930.KS",
            market="KR",
            name="삼성전자",
            pe_forward=5.4,
            roe=18.9,
            eps_growth=496.0,
            revenue_growth=69.3,
            val_reason="P/E5.4극저평가 · ROE19%우수 · EPS성장496% · 매출성장69%",
        )
        result = format_stock_snapshot(snap)
        # 가치: 줄에서 ROE19%/EPS성장496%/매출성장69%가 제거돼야 함
        val_lines = [ln for ln in result.splitlines() if ln.startswith("가치:")]
        if val_lines:
            val_line = val_lines[0]
            assert "ROE19" not in val_line
            assert "EPS성장496" not in val_line
            assert "매출성장69" not in val_line
            # 정성 평가는 남아야 함
            assert "극저평가" in val_line

    def test_val_reason_qualitative_only_kept(self) -> None:
        snap = StockAnalysisSnapshot(
            symbol="JPM",
            market="US",
            name="JPMorgan",
            pe_trailing=14.0,
            val_reason="P/E14.0저평가 · ROE15%우수 · EPS성장20%",
        )
        result = format_stock_snapshot(snap)
        val_lines = [ln for ln in result.splitlines() if ln.startswith("가치:")]
        if val_lines:
            assert "저평가" in val_lines[0]
            assert "ROE15" not in val_lines[0]

    def test_disclaimer_always_present(self) -> None:
        snap = StockAnalysisSnapshot(symbol="X", market="US", name="X")
        result = format_stock_snapshot(snap)
        assert "공개 정보 기반" in result or "투자 판단" in result

    def test_sector_section_shown_when_populated(self) -> None:
        snap = StockAnalysisSnapshot(
            symbol="005930.KS",
            market="KR",
            name="삼성전자",
            sector_title="반도체 / 전자",
            sector_lines=["HBM 수요 성장 지속 여부 관찰"],
            sector_risks=["CAPEX 사이클 하강"],
            sector_catalysts=["HBM4 공급 계약"],
        )
        result = format_stock_snapshot(snap)
        assert "📊 섹터" in result
        assert "반도체" in result
        assert "CAPEX" in result
        assert "HBM4" in result


# ── 10-ticker smoke tests (no network) ───────────────────────────────────────


def _make_fake_ohlcv(n: int = 65) -> pd.DataFrame:
    idx = pd.date_range("2026-01-01", periods=n, freq="D")
    close = [50_000 + i * 100 for i in range(n)]  # 오름 추세
    vol = [1_000_000] * n
    return pd.DataFrame(
        {"Open": close, "High": [c * 1.01 for c in close],
         "Low": [c * 0.99 for c in close], "Close": close, "Volume": vol},
        index=idx,
    )


def _make_fake_fund(symbol: str, market: str):
    from tele_quant.fundamentals import FundamentalSnapshot
    is_kr = market == "KR"
    return FundamentalSnapshot(
        symbol=symbol,
        market=market,
        sector="Technology" if not is_kr else "반도체",
        industry="Semiconductors" if not is_kr else "반도체 및 관련 장비",
        fetched_at=datetime.now(UTC),
        pe_trailing=20.0,
        pe_forward=18.0,
        pb=3.0,
        roe=25.0,
        eps_growth=30.0,
        revenue_growth=15.0,
        op_margin=25.0,
        dividend_yield=0.5,
        w52_position_pct=65.0,
        current_price=50000.0 if is_kr else 500.0,
        market_cap_krw=5_000_000_000_000 if is_kr else None,
        market_cap_usd=None if is_kr else 1_000_000_000_000,
    )


_SMOKE_TICKERS = [
    ("005930.KS", "KR"),  # 삼성전자
    ("000660.KS", "KR"),  # SK하이닉스
    ("042700.KQ", "KR"),  # 한미반도체
    ("128940.KS", "KR"),  # 한미약품
    ("329180.KS", "KR"),  # HD현대중공업
    ("207940.KS", "KR"),  # 삼성바이오로직스
    ("NVDA", "US"),
    ("CRM", "US"),
    ("JPM", "US"),
    ("PWR", "US"),
]


@pytest.mark.parametrize("symbol,market", _SMOKE_TICKERS)
def test_smoke_no_crash(symbol: str, market: str) -> None:
    """All 10 tickers: build + format without network, no crash."""
    fake_df = _make_fake_ohlcv()
    fake_fund = _make_fake_fund(symbol, market)

    with (
        patch("tele_quant.stock_data_provider.get_ohlcv", return_value=fake_df),
        patch("tele_quant.stock_data_provider.get_ticker_info", return_value={}),
        patch("tele_quant.daily_alpha._fetch_4h_data", return_value={
            "rsi": 52.0, "obv": "상승", "bb_pct": 40.0, "close": 50000.0, "vol_ratio": 1.1,
        }),
        patch("tele_quant.fundamentals.fetch_fundamentals", return_value=fake_fund),
        patch("tele_quant.recent_issue_collector.collect_recent_issues", return_value=[]),
        patch("tele_quant.earnings_snapshot.fetch_earnings_snapshot", return_value=None),
        patch("tele_quant.sector_macro.format_sector_macro", return_value=""),
        patch("tele_quant.clinical_pipeline.fetch_clinical_pipeline",
              return_value=MagicMock(trials=[], headline_signals=[], cash_burn_note="",
                                    partner_note="", market_note="", data_limited=True,
                                    limitation_note="공개자료 기준")),
    ):
        snap = build_stock_snapshot(symbol, market, store=None, deep=False, quick=False)
        result = format_stock_snapshot(snap)

    assert isinstance(result, str)
    assert len(result) > 50  # 최소 내용 존재
    assert symbol in result or snap.name in result


@pytest.mark.parametrize("symbol,market", _SMOKE_TICKERS)
def test_smoke_no_forbidden(symbol: str, market: str) -> None:
    """All 10 tickers: output must not contain forbidden expressions."""
    fake_df = _make_fake_ohlcv()
    fake_fund = _make_fake_fund(symbol, market)

    with (
        patch("tele_quant.stock_data_provider.get_ohlcv", return_value=fake_df),
        patch("tele_quant.stock_data_provider.get_ticker_info", return_value={}),
        patch("tele_quant.daily_alpha._fetch_4h_data", return_value={
            "rsi": 52.0, "obv": "상승", "bb_pct": 40.0, "close": 50000.0, "vol_ratio": 1.1,
        }),
        patch("tele_quant.fundamentals.fetch_fundamentals", return_value=fake_fund),
        patch("tele_quant.recent_issue_collector.collect_recent_issues", return_value=[]),
        patch("tele_quant.earnings_snapshot.fetch_earnings_snapshot", return_value=None),
        patch("tele_quant.sector_macro.format_sector_macro", return_value=""),
        patch("tele_quant.clinical_pipeline.fetch_clinical_pipeline",
              return_value=MagicMock(trials=[], headline_signals=[], cash_burn_note="",
                                    partner_note="", market_note="", data_limited=True,
                                    limitation_note="공개자료 기준")),
    ):
        snap = build_stock_snapshot(symbol, market, store=None, deep=False, quick=False)
        result = format_stock_snapshot(snap)

    _no_forbidden(result)


@pytest.mark.parametrize("symbol,market", _SMOKE_TICKERS)
def test_smoke_has_disclaimer(symbol: str, market: str) -> None:
    """All 10 tickers: disclaimer must appear."""
    fake_df = _make_fake_ohlcv()
    fake_fund = _make_fake_fund(symbol, market)

    with (
        patch("tele_quant.stock_data_provider.get_ohlcv", return_value=fake_df),
        patch("tele_quant.stock_data_provider.get_ticker_info", return_value={}),
        patch("tele_quant.daily_alpha._fetch_4h_data", return_value={
            "rsi": 52.0, "obv": "상승", "bb_pct": 40.0, "close": 50000.0, "vol_ratio": 1.1,
        }),
        patch("tele_quant.fundamentals.fetch_fundamentals", return_value=fake_fund),
        patch("tele_quant.recent_issue_collector.collect_recent_issues", return_value=[]),
        patch("tele_quant.earnings_snapshot.fetch_earnings_snapshot", return_value=None),
        patch("tele_quant.sector_macro.format_sector_macro", return_value=""),
        patch("tele_quant.clinical_pipeline.fetch_clinical_pipeline",
              return_value=MagicMock(trials=[], headline_signals=[], cash_burn_note="",
                                    partner_note="", market_note="", data_limited=True,
                                    limitation_note="공개자료 기준")),
    ):
        snap = build_stock_snapshot(symbol, market, store=None, deep=False, quick=False)
        result = format_stock_snapshot(snap)

    assert "공개 정보" in result or "투자 판단" in result


@pytest.mark.parametrize("symbol,market", _SMOKE_TICKERS)
def test_smoke_sector_intelligence_populated(symbol: str, market: str) -> None:
    """Each ticker should trigger sector_intelligence_text (sector ID detected)."""
    fake_df = _make_fake_ohlcv()
    fake_fund = _make_fake_fund(symbol, market)

    with (
        patch("tele_quant.stock_data_provider.get_ohlcv", return_value=fake_df),
        patch("tele_quant.stock_data_provider.get_ticker_info", return_value={}),
        patch("tele_quant.daily_alpha._fetch_4h_data", return_value={
            "rsi": 52.0, "obv": "상승", "bb_pct": 40.0, "close": 50000.0, "vol_ratio": 1.1,
        }),
        patch("tele_quant.fundamentals.fetch_fundamentals", return_value=fake_fund),
        patch("tele_quant.recent_issue_collector.collect_recent_issues", return_value=[]),
        patch("tele_quant.earnings_snapshot.fetch_earnings_snapshot", return_value=None),
        patch("tele_quant.sector_macro.format_sector_macro", return_value=""),
        patch("tele_quant.clinical_pipeline.fetch_clinical_pipeline",
              return_value=MagicMock(trials=[], headline_signals=[], cash_burn_note="",
                                    partner_note="", market_note="", data_limited=True,
                                    limitation_note="공개자료 기준")),
    ):
        snap = build_stock_snapshot(symbol, market, store=None, deep=False, quick=False)

    # sector_intelligence_text 또는 sector_title 중 하나는 있어야 함
    assert snap.sector_intelligence_text or snap.sector_title, (
        f"{symbol}: sector section not populated (sector={snap.sector!r}, "
        f"industry={snap.industry!r})"
    )
