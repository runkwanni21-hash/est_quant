"""Tests for sector_valuation module."""

from __future__ import annotations

from tele_quant.sector_valuation import (
    SectorAnalysis,
    analyze_sector_value,
    detect_sector_key,
)

# ── detect_sector_key ─────────────────────────────────────────────────────────


class TestDetectSectorKey:
    def test_bio_korean(self) -> None:
        assert detect_sector_key("제약") == "bio"

    def test_bio_english(self) -> None:
        assert detect_sector_key("Biotechnology") == "bio"

    def test_bio_cdmo(self) -> None:
        assert detect_sector_key("CDMO") == "bio"

    def test_semiconductor_korean(self) -> None:
        assert detect_sector_key("반도체") == "semiconductor"

    def test_semiconductor_english(self) -> None:
        assert detect_sector_key("Semiconductors") == "semiconductor"

    def test_shipbuilding(self) -> None:
        assert detect_sector_key("조선") == "shipbuilding"

    def test_defense(self) -> None:
        assert detect_sector_key("방산") == "defense"

    def test_finance_korean(self) -> None:
        assert detect_sector_key("금융") == "finance"

    def test_finance_bank(self) -> None:
        assert detect_sector_key("은행") == "finance"

    def test_beauty(self) -> None:
        assert detect_sector_key("화장품") == "beauty"

    def test_software(self) -> None:
        assert detect_sector_key("소프트웨어") == "software"

    def test_ev_battery(self) -> None:
        assert detect_sector_key("이차전지") == "ev"

    def test_symbol_override_nvda(self) -> None:
        assert detect_sector_key("Technology", "NVDA") == "semiconductor"

    def test_symbol_override_mrna(self) -> None:
        assert detect_sector_key("Healthcare", "MRNA") == "bio"

    def test_technology_non_semi_symbol(self) -> None:
        key = detect_sector_key("Technology", "AAPL")
        assert key == "software"

    def test_unknown_sector_returns_general(self) -> None:
        assert detect_sector_key("Unknown XYZ Sector") == "general"

    def test_partial_match(self) -> None:
        assert detect_sector_key("Korean 제약 company") == "bio"


# ── SectorAnalysis dataclass ──────────────────────────────────────────────────


class TestSectorAnalysisDataclass:
    def test_defaults(self) -> None:
        sa = SectorAnalysis(sector="반도체")
        assert sa.key == ""
        assert sa.score == 50.0
        assert sa.lines == []
        assert sa.risks == []
        assert sa.catalysts == []
        assert sa.peer_symbols == []
        assert sa.victim_symbols == []
        assert sa.next_checkpoints == []

    def test_field_assignment(self) -> None:
        sa = SectorAnalysis(sector="바이오", key="bio", title="바이오/제약", score=65.0)
        assert sa.key == "bio"
        assert sa.score == 65.0


# ── analyze_sector_value ──────────────────────────────────────────────────────


class TestAnalyzeSectorValue:
    def test_bio_returns_sector_analysis(self) -> None:
        result = analyze_sector_value("128940.KS", "KR", "제약")
        assert isinstance(result, SectorAnalysis)
        assert result.key == "bio"

    def test_bio_has_risks_and_catalysts(self) -> None:
        result = analyze_sector_value("128940.KS", "KR", "제약")
        assert len(result.risks) > 0
        assert len(result.catalysts) > 0

    def test_bio_title(self) -> None:
        result = analyze_sector_value("128940.KS", "KR", "바이오")
        assert "바이오" in result.title

    def test_semiconductor_score_above_50(self) -> None:
        result = analyze_sector_value("NVDA", "US", "Semiconductors")
        assert result.score > 50.0

    def test_semiconductor_has_peer_symbols(self) -> None:
        result = analyze_sector_value("NVDA", "US", "Semiconductors")
        assert len(result.peer_symbols) > 0

    def test_shipbuilding_kr(self) -> None:
        result = analyze_sector_value("009540.KS", "KR", "조선")
        assert result.key == "shipbuilding"
        assert "수주" in " ".join(result.catalysts)

    def test_defense_kr(self) -> None:
        result = analyze_sector_value("012450.KS", "KR", "방산")
        assert result.key == "defense"

    def test_finance_pbr_line(self) -> None:
        fund_dict = {"pb": 0.6}
        result = analyze_sector_value("105560.KS", "KR", "금융", fund_snapshot=fund_dict)
        assert result.key == "finance"
        # PBR < 0.7 → 장부가 대비 저평가 언급
        assert any("저평가" in line or "PBR" in line for line in result.lines)

    def test_beauty_kr_peer_symbols(self) -> None:
        result = analyze_sector_value("090430.KS", "KR", "화장품")
        assert result.key == "beauty"
        assert len(result.peer_symbols) > 0

    def test_software_rule40_met(self) -> None:
        fund_dict = {"revenueGrowth": 0.25, "operatingMargins": 0.20}
        result = analyze_sector_value("CRM", "US", "소프트웨어", fund_snapshot=fund_dict)
        assert result.key == "software"
        assert any("Rule of 40" in line for line in result.lines)

    def test_software_rule40_not_met(self) -> None:
        fund_dict = {"revenueGrowth": 0.10, "operatingMargins": 0.05}
        result = analyze_sector_value("CRM", "US", "소프트웨어", fund_snapshot=fund_dict)
        assert any("미충족" in line or "Rule of 40" in line for line in result.lines)

    def test_general_fallback(self) -> None:
        result = analyze_sector_value("XYZ", "US", "Miscellaneous Unknown")
        assert result.key == "general"
        assert result.score == 50.0

    def test_ai_power_checkpoints(self) -> None:
        result = analyze_sector_value("010120.KS", "KR", "전기장비")
        assert result.key == "ai_power"
        assert len(result.next_checkpoints) > 0

    def test_ev_battery_risks(self) -> None:
        result = analyze_sector_value("LG.KS", "KR", "이차전지")
        assert result.key == "ev"
        assert any("IRA" in r or "리튬" in r for r in result.risks)

    def test_no_forbidden_words_in_output(self) -> None:
        forbidden = ["매수 권장", "매도 권장", "확정 수익", "수혜 확정", "피해 확정"]
        for sector in ["제약", "반도체", "조선", "방산", "금융", "화장품", "소프트웨어"]:
            result = analyze_sector_value("X", "KR", sector)
            all_text = " ".join(result.lines + result.risks + result.catalysts)
            for word in forbidden:
                assert word not in all_text, f"금지 표현 '{word}' 발견 in sector={sector}"

    def test_bio_issues_matched(self) -> None:
        issues = ["FDA 심사 통과 예상", "임상 3상 결과 발표 예정"]
        result = analyze_sector_value("MRNA", "US", "Biotechnology", issues=issues)
        assert result.key == "bio"
        # 이슈가 반영되었는지 확인 (bio keywords 매칭)
        assert len(result.lines) > 1

    def test_exception_falls_back_to_general(self) -> None:
        # fund_snapshot with bad data should not raise
        result = analyze_sector_value("X", "US", "금융", fund_snapshot={"pb": "not_a_float"})
        assert isinstance(result, SectorAnalysis)
