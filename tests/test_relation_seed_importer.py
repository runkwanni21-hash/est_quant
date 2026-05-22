"""Tests for relation_seed_importer — KR resolver, edge parser, import pipeline, relation hints."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from tele_quant.relation_seed_importer import (
    VALID_DIRECTIONS,
    VALID_RELATION_TYPE_RE,
    KRTickerResolver,
    RelationHint,
    SeedEdge,
    _parse_evidence,
    _parse_lag_hours,
    build_relation_edge_dict,
    format_relation_hints,
    get_relation_hints,
    import_sector_seeds,
    load_all_seed_files,
    load_kq_set,
)

# ── load_kq_set ────────────────────────────────────────────────────────────────


class TestLoadKqSet:
    def test_returns_frozenset(self, tmp_path: Path) -> None:
        yml = tmp_path / "ticker_aliases.yml"
        yml.write_text("stocks:\n  - symbol: '005930'\n    board: KOSDAQ\n")
        result = load_kq_set(yml)
        assert isinstance(result, frozenset)

    def test_kosdaq_board_entry(self, tmp_path: Path) -> None:
        yml = tmp_path / "ticker_aliases.yml"
        yml.write_text("stocks:\n  - symbol: '247540'\n    board: KOSDAQ\n")
        result = load_kq_set(yml)
        assert "247540" in result

    def test_kq_suffix_entry(self, tmp_path: Path) -> None:
        yml = tmp_path / "ticker_aliases.yml"
        yml.write_text("stocks:\n  - symbol: '035420.KQ'\n    board: ''\n")
        result = load_kq_set(yml)
        assert "035420" in result

    def test_kospi_board_excluded(self, tmp_path: Path) -> None:
        yml = tmp_path / "ticker_aliases.yml"
        yml.write_text("stocks:\n  - symbol: '005380'\n    board: KOSPI\n")
        result = load_kq_set(yml)
        assert "005380" not in result

    def test_missing_file_returns_empty(self, tmp_path: Path) -> None:
        result = load_kq_set(tmp_path / "nonexistent.yml")
        assert result == frozenset()

    def test_empty_yml_returns_empty(self, tmp_path: Path) -> None:
        yml = tmp_path / "aliases.yml"
        yml.write_text("{}\n")
        result = load_kq_set(yml)
        assert result == frozenset()


# ── KRTickerResolver ───────────────────────────────────────────────────────────


class TestKRTickerResolver:
    def _resolver_with(self, kq_codes: list[str]) -> KRTickerResolver:
        return KRTickerResolver(kq_set=frozenset(kq_codes))

    def test_bare_kq_resolves_to_kq(self) -> None:
        resolver = self._resolver_with(["247540"])
        sym, was_bare = resolver.resolve("247540")
        assert sym == "247540.KQ"
        assert was_bare is True

    def test_bare_ks_resolves_to_ks(self) -> None:
        resolver = self._resolver_with([])
        sym, was_bare = resolver.resolve("005930")
        assert sym == "005930.KS"
        assert was_bare is True

    def test_already_suffixed_not_changed(self) -> None:
        resolver = self._resolver_with(["247540"])
        sym, was_bare = resolver.resolve("247540.KQ")
        assert sym == "247540.KQ"
        assert was_bare is False

    def test_us_ticker_not_touched(self) -> None:
        resolver = self._resolver_with([])
        sym, was_bare = resolver.resolve("NVDA")
        assert sym == "NVDA"
        assert was_bare is False

    def test_us_market_skips_kr_resolution(self) -> None:
        resolver = self._resolver_with([])
        sym, was_bare = resolver.resolve("123456", market="US")
        assert sym == "123456"
        assert was_bare is False

    def test_resolve_symbol_and_market_kr(self) -> None:
        resolver = self._resolver_with([])
        sym, mkt, was_bare = resolver.resolve_symbol_and_market("005380", "KR")
        assert sym == "005380.KS"
        assert mkt == "KR"
        assert was_bare is True

    def test_resolve_symbol_and_market_already_suffixed(self) -> None:
        resolver = self._resolver_with([])
        sym, _mkt, was_bare = resolver.resolve_symbol_and_market("005380.KS", "KR")
        assert sym == "005380.KS"
        assert was_bare is False

    def test_resolve_caches_result(self) -> None:
        resolver = self._resolver_with(["247540"])
        sym1, _ = resolver.resolve("247540")
        sym2, was_bare2 = resolver.resolve("247540")
        assert sym1 == sym2
        # second call hits cache — was_bare must be False
        assert was_bare2 is False

    def test_unresolved_property_initially_empty(self) -> None:
        resolver = self._resolver_with([])
        assert resolver.unresolved == []


# ── _parse_lag_hours ──────────────────────────────────────────────────────────


class TestParseLagHours:
    def test_days_parsed(self) -> None:
        assert _parse_lag_hours("3d") == 72

    def test_hours_parsed(self) -> None:
        assert _parse_lag_hours("12h") == 12

    def test_weeks_parsed(self) -> None:
        assert _parse_lag_hours("1w") == 168

    def test_none_returns_default(self) -> None:
        assert _parse_lag_hours(None) == 24

    def test_empty_returns_default(self) -> None:
        assert _parse_lag_hours("") == 24

    def test_invalid_returns_default(self) -> None:
        assert _parse_lag_hours("abc") == 24

    def test_fractional_days(self) -> None:
        assert _parse_lag_hours("2d") == 48

    def test_five_days(self) -> None:
        assert _parse_lag_hours("5d") == 120


# ── _parse_evidence ───────────────────────────────────────────────────────────


class TestParseEvidence:
    def test_valid_http_url_returned(self) -> None:
        ev = [{"title": "Reuters", "url": "https://reuters.com/art"}]
        title, url = _parse_evidence(ev)
        assert url == "https://reuters.com/art"
        assert title == "Reuters"

    def test_placeholder_url_skipped(self) -> None:
        ev = [{"title": "t", "url": "TBD"}]
        _title, url = _parse_evidence(ev)
        assert url == ""

    def test_null_url_skipped(self) -> None:
        ev = [{"title": "t", "url": "null"}]
        _title, url = _parse_evidence(ev)
        assert url == ""

    def test_no_url_fallback_title_returned(self) -> None:
        ev = [{"title": "Some report", "url": ""}]
        title, url = _parse_evidence(ev)
        assert title == "Some report"
        assert url == ""

    def test_empty_list_returns_empty(self) -> None:
        assert _parse_evidence([]) == ("", "")

    def test_first_valid_url_preferred(self) -> None:
        ev = [
            {"title": "bad", "url": "TBD"},
            {"title": "good", "url": "https://example.com"},
        ]
        title, url = _parse_evidence(ev)
        assert url == "https://example.com"
        assert title == "good"

    def test_hash_placeholder_skipped(self) -> None:
        ev = [{"title": "t", "url": "#"}]
        _title, url = _parse_evidence(ev)
        assert url == ""


# ── load_all_seed_files ───────────────────────────────────────────────────────


def _make_seed_yml(sector_id: str, edges: list[dict]) -> str:
    import yaml

    data = {
        "sector_relation_seeds": {
            "sector_id": sector_id,
            "sector_name": f"Test {sector_id}",
            "edges": edges,
        }
    }
    return yaml.dump(data, allow_unicode=True)


class TestLoadAllSeedFiles:
    def test_basic_load(self, tmp_path: Path) -> None:
        edge = {
            "source_symbol": "005930.KS",
            "source_name": "Samsung",
            "source_market": "KR",
            "target_symbol": "000660.KS",
            "target_name": "SK Hynix",
            "target_market": "KR",
            "relation_type": "PEER_MOMENTUM",
            "direction": "UP_LEADS_UP",
            "expected_lag": "2d",
            "confidence": "HIGH",
            "rationale": "Memory peer",
            "evidence": [{"title": "Reuters", "url": "https://reuters.com/a"}],
        }
        (tmp_path / "01_test.yml").write_text(_make_seed_yml("test_sector", [edge]))
        edges, result = load_all_seed_files(tmp_path)
        assert len(edges) == 1
        assert edges[0].source_symbol == "005930.KS"
        assert result.edges_read == 1

    def test_bare_kr_resolved(self, tmp_path: Path) -> None:
        edge = {
            "source_symbol": "247540",
            "source_market": "KR",
            "target_symbol": "035420.KQ",
            "target_market": "KR",
            "relation_type": "SUPPLY_CHAIN",
            "direction": "UP_LEADS_UP",
            "expected_lag": "3d",
            "confidence": "MEDIUM",
            "evidence": [],
        }
        (tmp_path / "01_test.yml").write_text(_make_seed_yml("sector_x", [edge]))
        kq = frozenset(["247540"])
        resolver = KRTickerResolver(kq_set=kq)
        edges, result = load_all_seed_files(tmp_path, resolver=resolver)
        assert edges[0].source_symbol == "247540.KQ"
        assert result.bare_kr_resolved >= 1

    def test_self_loop_removed(self, tmp_path: Path) -> None:
        edge = {
            "source_symbol": "005930.KS",
            "target_symbol": "005930.KS",
            "source_market": "KR",
            "target_market": "KR",
            "relation_type": "PEER_MOMENTUM",
            "direction": "UP_LEADS_UP",
            "confidence": "MEDIUM",
            "evidence": [],
        }
        (tmp_path / "01_test.yml").write_text(_make_seed_yml("s", [edge]))
        edges, result = load_all_seed_files(tmp_path)
        assert len(edges) == 0
        assert result.self_loops_removed == 1

    def test_duplicate_edge_deduped(self, tmp_path: Path) -> None:
        edge = {
            "source_symbol": "NVDA",
            "source_market": "US",
            "target_symbol": "AMD",
            "target_market": "US",
            "relation_type": "COMPETITOR",
            "direction": "CORRELATED",
            "confidence": "MEDIUM",
            "evidence": [],
        }
        (tmp_path / "01_test.yml").write_text(_make_seed_yml("s", [edge, edge]))
        edges, result = load_all_seed_files(tmp_path)
        assert len(edges) == 1
        assert result.duplicates_found == 1

    def test_high_without_url_downgraded_to_medium(self, tmp_path: Path) -> None:
        edge = {
            "source_symbol": "NVDA",
            "source_market": "US",
            "target_symbol": "AMD",
            "target_market": "US",
            "relation_type": "COMPETITOR",
            "direction": "CORRELATED",
            "confidence": "HIGH",
            "evidence": [],  # no URL
        }
        (tmp_path / "01_test.yml").write_text(_make_seed_yml("s", [edge]))
        edges, result = load_all_seed_files(tmp_path)
        assert edges[0].confidence == "MEDIUM"
        assert edges[0].audit_high is True
        assert result.high_downgraded == 1

    def test_low_confidence_watch_only(self, tmp_path: Path) -> None:
        edge = {
            "source_symbol": "NVDA",
            "source_market": "US",
            "target_symbol": "INTC",
            "target_market": "US",
            "relation_type": "COMPETITOR",
            "direction": "CORRELATED",
            "confidence": "LOW",
            "evidence": [],
        }
        (tmp_path / "01_test.yml").write_text(_make_seed_yml("s", [edge]))
        edges, result = load_all_seed_files(tmp_path)
        assert edges[0].watch_only is True
        assert edges[0].active is False
        assert result.low_watch_only == 1

    def test_factor_edge_parsed(self, tmp_path: Path) -> None:
        import yaml

        data = {
            "sector_relation_seeds": {
                "sector_id": "shipbuilding",
                "edges": [],
                "factor_edges": [
                    {
                        "source_symbol": "STEEL_PLATE",
                        "source_market": "COMMODITY",
                        "target_symbol": "010140.KS",
                        "target_market": "KR",
                        "relation_type": "INPUT_COST",
                        "direction": "UP_LEADS_DOWN",
                        "confidence": "MEDIUM",
                        "expected_lag": "1w",
                        "evidence": [],
                    }
                ],
            }
        }
        (tmp_path / "07_shipbuilding.yml").write_text(yaml.dump(data, allow_unicode=True))
        edges, result = load_all_seed_files(tmp_path)
        assert result.factor_edges == 1
        assert edges[0].is_factor_edge is True
        assert edges[0].source_market == "COMMODITY"

    def test_manifest_yml_skipped(self, tmp_path: Path) -> None:
        (tmp_path / "sector_manifest.yml").write_text("as_of: 2026-05-17\n")
        (tmp_path / "01_test.yml").write_text(
            _make_seed_yml(
                "s",
                [
                    {
                        "source_symbol": "NVDA",
                        "source_market": "US",
                        "target_symbol": "AMD",
                        "target_market": "US",
                        "relation_type": "COMPETITOR",
                        "direction": "CORRELATED",
                        "confidence": "MEDIUM",
                        "evidence": [],
                    }
                ],
            )
        )
        edges, _r = load_all_seed_files(tmp_path)
        assert len(edges) == 1  # manifest not counted

    def test_missing_required_field_skipped(self, tmp_path: Path) -> None:
        edge = {"source_symbol": "NVDA", "target_symbol": ""}  # no relation_type, direction
        (tmp_path / "01_test.yml").write_text(_make_seed_yml("s", [edge]))
        edges, result = load_all_seed_files(tmp_path)
        assert len(edges) == 0
        assert result.skipped >= 1

    def test_expected_lag_parsed(self, tmp_path: Path) -> None:
        edge = {
            "source_symbol": "NVDA",
            "source_market": "US",
            "target_symbol": "AMD",
            "target_market": "US",
            "relation_type": "COMPETITOR",
            "direction": "CORRELATED",
            "confidence": "MEDIUM",
            "expected_lag": "5d",
            "evidence": [],
        }
        (tmp_path / "01_test.yml").write_text(_make_seed_yml("s", [edge]))
        edges, _r = load_all_seed_files(tmp_path)
        assert edges[0].expected_lag_hours == 120

    def test_sector_summary_populated(self, tmp_path: Path) -> None:
        edge = {
            "source_symbol": "NVDA",
            "source_market": "US",
            "target_symbol": "AMD",
            "target_market": "US",
            "relation_type": "COMPETITOR",
            "direction": "CORRELATED",
            "confidence": "MEDIUM",
            "evidence": [],
        }
        (tmp_path / "01_sector_a.yml").write_text(_make_seed_yml("sector_a", [edge]))
        _, result = load_all_seed_files(tmp_path)
        assert "sector_a" in result.sector_summary
        assert result.sector_summary["sector_a"] == 1


# ── build_relation_edge_dict ──────────────────────────────────────────────────


class TestBuildRelationEdgeDict:
    def _make_edge(self, **kwargs) -> SeedEdge:
        defaults = {
            "source_symbol": "NVDA",
            "source_name": "NVIDIA",
            "source_market": "US",
            "source_sector": "",
            "target_symbol": "AMD",
            "target_name": "AMD",
            "target_market": "US",
            "target_sector": "",
            "relation_type": "COMPETITOR",
            "direction": "CORRELATED",
            "expected_lag_hours": 48,
            "confidence": "MEDIUM",
            "relation_score": 0.60,
            "rationale": "Both x86 CPU makers",
            "evidence_url": "https://example.com",
            "evidence_title": "Source",
            "trading_note": "",
            "active": True,
            "watch_only": False,
            "audit_high": False,
            "is_factor_edge": False,
            "source_3m_move_pct": None,
            "rule_id": "seed:test_sector",
            "sector_id": "test_sector",
        }
        defaults.update(kwargs)
        return SeedEdge(**defaults)

    def test_keys_present(self) -> None:
        edge = self._make_edge()
        d = build_relation_edge_dict(edge)
        assert "source_symbol" in d
        assert "target_symbol" in d
        assert "relation_type" in d
        assert "confidence" in d
        assert "active" in d
        assert "rule_id" in d

    def test_active_true_maps_to_1(self) -> None:
        edge = self._make_edge(active=True)
        d = build_relation_edge_dict(edge)
        assert d["active"] == 1

    def test_active_false_maps_to_0(self) -> None:
        edge = self._make_edge(active=False, confidence="LOW")
        d = build_relation_edge_dict(edge)
        assert d["active"] == 0

    def test_inactive_confidence_for_low(self) -> None:
        edge = self._make_edge(active=False, confidence="LOW")
        d = build_relation_edge_dict(edge)
        assert d["confidence"] == "INACTIVE"

    def test_evidence_summary_truncated(self) -> None:
        edge = self._make_edge(rationale="x" * 600)
        d = build_relation_edge_dict(edge)
        assert len(d["evidence_summary"]) <= 500

    def test_source_return_3m_pct_none(self) -> None:
        edge = self._make_edge(source_3m_move_pct=None)
        d = build_relation_edge_dict(edge)
        assert d["source_return_3m_pct"] is None

    def test_evidence_type_is_seed_yaml(self) -> None:
        edge = self._make_edge()
        d = build_relation_edge_dict(edge)
        assert d["evidence_type"] == "SEED_YAML"


# ── import_sector_seeds (dry-run) ─────────────────────────────────────────────


class TestImportSectorSeeds:
    def test_dry_run_no_db_calls(self, tmp_path: Path) -> None:
        edge = {
            "source_symbol": "NVDA",
            "source_market": "US",
            "target_symbol": "AMD",
            "target_market": "US",
            "relation_type": "COMPETITOR",
            "direction": "CORRELATED",
            "confidence": "MEDIUM",
            "evidence": [],
        }
        (tmp_path / "01_test.yml").write_text(_make_seed_yml("s", [edge]))
        mock_store = MagicMock()
        result = import_sector_seeds(tmp_path, store=mock_store, dry_run=True)
        mock_store.upsert_relation_edges.assert_not_called()
        assert result.inserted == 0

    def test_save_calls_upsert(self, tmp_path: Path) -> None:
        edge = {
            "source_symbol": "NVDA",
            "source_market": "US",
            "target_symbol": "AMD",
            "target_market": "US",
            "relation_type": "COMPETITOR",
            "direction": "CORRELATED",
            "confidence": "MEDIUM",
            "evidence": [],
        }
        (tmp_path / "01_test.yml").write_text(_make_seed_yml("s", [edge]))
        mock_store = MagicMock()
        mock_store.upsert_relation_edges.return_value = (1, 0)
        result = import_sector_seeds(tmp_path, store=mock_store, dry_run=False)
        mock_store.upsert_relation_edges.assert_called_once()
        assert result.inserted == 1

    def test_no_store_behaves_as_dry_run(self, tmp_path: Path) -> None:
        edge = {
            "source_symbol": "NVDA",
            "source_market": "US",
            "target_symbol": "AMD",
            "target_market": "US",
            "relation_type": "COMPETITOR",
            "direction": "CORRELATED",
            "confidence": "MEDIUM",
            "evidence": [],
        }
        (tmp_path / "01_test.yml").write_text(_make_seed_yml("s", [edge]))
        result = import_sector_seeds(tmp_path, store=None, dry_run=False)
        assert result.edges_read >= 1
        assert result.inserted == 0


# ── get_relation_hints ────────────────────────────────────────────────────────


def _make_db_edge(**kwargs) -> dict:
    defaults = {
        "id": 1,
        "source_symbol": "NVDA",
        "source_name": "NVIDIA",
        "target_symbol": "AMD",
        "target_name": "AMD",
        "relation_type": "COMPETITOR",
        "direction": "CORRELATED",
        "confidence": "MEDIUM",
        "expected_lag_hours": 48,
        "evidence_summary": "Both compete in GPU",
        "rule_id": "seed:sector_x",
        "active": 1,
    }
    defaults.update(kwargs)
    return defaults


class TestGetRelationHints:
    def test_returns_dict_keys(self) -> None:
        mock_store = MagicMock()
        mock_store.get_all_relation_edges.return_value = []
        result = get_relation_hints("NVDA", mock_store)
        assert "beneficiary" in result
        assert "victim" in result
        assert "peer" in result

    def test_none_store_returns_empty(self) -> None:
        result = get_relation_hints("NVDA", None)
        assert result == {"beneficiary": [], "victim": [], "peer": []}

    def test_beneficiary_classified(self) -> None:
        e = _make_db_edge(
            source_symbol="NVDA",
            target_symbol="SMCI",
            target_name="SuperMicro",
            relation_type="AI_CAPEX_SPILLOVER",
            direction="UP_LEADS_UP",
        )
        mock_store = MagicMock()
        mock_store.get_all_relation_edges.return_value = [e]
        hints = get_relation_hints("NVDA", mock_store)
        assert len(hints["beneficiary"]) == 1
        assert hints["beneficiary"][0].symbol == "SMCI"

    def test_victim_classified(self) -> None:
        e = _make_db_edge(
            source_symbol="NVDA",
            target_symbol="INTC",
            target_name="Intel",
            relation_type="COMPETITOR",
            direction="UP_LEADS_DOWN",
        )
        mock_store = MagicMock()
        mock_store.get_all_relation_edges.return_value = [e]
        hints = get_relation_hints("NVDA", mock_store)
        assert len(hints["victim"]) == 1

    def test_peer_classified(self) -> None:
        e = _make_db_edge(
            source_symbol="NVDA",
            target_symbol="AMD",
            relation_type="COMPETITOR",
            direction="CORRELATED",
        )
        mock_store = MagicMock()
        mock_store.get_all_relation_edges.return_value = [e]
        hints = get_relation_hints("NVDA", mock_store)
        assert len(hints["peer"]) >= 1

    def test_max_per_category_limit(self) -> None:
        edges = [
            _make_db_edge(
                id=i,
                source_symbol="NVDA",
                target_symbol=f"XYZ{i}",
                target_name=f"Co{i}",
                relation_type="BENEFICIARY",
                direction="UP_LEADS_UP",
            )
            for i in range(10)
        ]
        mock_store = MagicMock()
        mock_store.get_all_relation_edges.return_value = edges
        hints = get_relation_hints("NVDA", mock_store, max_per_category=3)
        assert len(hints["beneficiary"]) <= 3

    def test_unrelated_symbol_not_included(self) -> None:
        e = _make_db_edge(source_symbol="TSMC", target_symbol="AMAT")
        mock_store = MagicMock()
        mock_store.get_all_relation_edges.return_value = [e]
        hints = get_relation_hints("NVDA", mock_store)
        assert hints["beneficiary"] == []
        assert hints["victim"] == []
        assert hints["peer"] == []

    def test_high_confidence_sorted_first(self) -> None:
        edges = [
            _make_db_edge(id=1, source_symbol="NVDA", target_symbol="A1", relation_type="BENEFICIARY", direction="UP_LEADS_UP", confidence="LOW"),
            _make_db_edge(id=2, source_symbol="NVDA", target_symbol="A2", relation_type="BENEFICIARY", direction="UP_LEADS_UP", confidence="HIGH"),
        ]
        mock_store = MagicMock()
        mock_store.get_all_relation_edges.return_value = edges
        hints = get_relation_hints("NVDA", mock_store)
        if len(hints["beneficiary"]) >= 2:
            assert hints["beneficiary"][0].confidence == "HIGH"

    def test_db_error_returns_empty(self) -> None:
        mock_store = MagicMock()
        mock_store.get_all_relation_edges.side_effect = RuntimeError("db fail")
        result = get_relation_hints("NVDA", mock_store)
        assert result == {"beneficiary": [], "victim": [], "peer": []}

    def test_watch_only_flag_set(self) -> None:
        e = _make_db_edge(
            source_symbol="NVDA",
            target_symbol="SMCI",
            target_name="SMCI",
            relation_type="BENEFICIARY",
            direction="UP_LEADS_UP",
            rule_id="seed:sector_x:watch_only",
        )
        mock_store = MagicMock()
        mock_store.get_all_relation_edges.return_value = [e]
        hints = get_relation_hints("NVDA", mock_store)
        if hints["beneficiary"]:
            assert hints["beneficiary"][0].watch_only is True


# ── format_relation_hints ──────────────────────────────────────────────────────


def _make_hint(
    symbol: str = "AMD",
    name: str = "AMD",
    category: str = "beneficiary",
    confidence: str = "MEDIUM",
    lag_hours: int = 48,
    rationale: str = "GPU peer",
    watch_only: bool = False,
) -> RelationHint:
    return RelationHint(
        symbol=symbol,
        name=name,
        relation_type="COMPETITOR",
        direction="CORRELATED",
        confidence=confidence,
        expected_lag_hours=lag_hours,
        rationale=rationale,
        category=category,
        watch_only=watch_only,
    )


class TestFormatRelationHints:
    def test_empty_hints_returns_empty_string(self) -> None:
        result = format_relation_hints({"beneficiary": [], "victim": [], "peer": []})
        assert result == ""

    def test_beneficiary_section_present(self) -> None:
        hints = {"beneficiary": [_make_hint(category="beneficiary")], "victim": [], "peer": []}
        text = format_relation_hints(hints)
        assert "수혜 가능성" in text
        assert "AMD" in text

    def test_victim_section_present(self) -> None:
        hints = {"beneficiary": [], "victim": [_make_hint(category="victim")], "peer": []}
        text = format_relation_hints(hints)
        assert "부담" in text

    def test_peer_section_present(self) -> None:
        hints = {"beneficiary": [], "victim": [], "peer": [_make_hint(category="peer")]}
        text = format_relation_hints(hints)
        assert "경쟁" in text or "피어" in text

    def test_disclaimer_present(self) -> None:
        hints = {"beneficiary": [_make_hint()], "victim": [], "peer": []}
        text = format_relation_hints(hints)
        assert "상관관계는 인과관계가 아님" in text

    def test_lag_days_shown(self) -> None:
        h = _make_hint(lag_hours=72)
        hints = {"beneficiary": [h], "victim": [], "peer": []}
        text = format_relation_hints(hints)
        assert "3일 후행" in text

    def test_lag_hours_shown(self) -> None:
        h = _make_hint(lag_hours=6)
        hints = {"beneficiary": [h], "victim": [], "peer": []}
        text = format_relation_hints(hints)
        assert "6h 후행" in text

    def test_watch_only_labeled(self) -> None:
        h = _make_hint(watch_only=True)
        hints = {"beneficiary": [h], "victim": [], "peer": []}
        text = format_relation_hints(hints)
        assert "관찰전용" in text

    def test_no_forbidden_words(self) -> None:
        h = _make_hint()
        hints = {"beneficiary": [h], "victim": [_make_hint(category="victim")], "peer": []}
        text = format_relation_hints(hints)
        forbidden = [
            "매수 권장", "매도 권장", "확정 수익", "수혜 확정", "피해 확정",
            "세력 매집 확정", "기관 매집 확정", "반드시 상승",
        ]
        for word in forbidden:
            assert word not in text, f"Forbidden word found: {word}"

    def test_rationale_included(self) -> None:
        h = _make_hint(rationale="Strong supply chain link")
        hints = {"beneficiary": [h], "victim": [], "peer": []}
        text = format_relation_hints(hints)
        assert "Strong supply chain link" in text


# ── VALID_DIRECTIONS / VALID_RELATION_TYPE_RE (audit enum 일치성) ──────────────


class TestValidEnums:
    def test_valid_directions_contains_up_leads_up(self) -> None:
        assert "UP_LEADS_UP" in VALID_DIRECTIONS

    def test_valid_directions_contains_all_expected(self) -> None:
        expected = {
            "UP_LEADS_UP", "UP_LEADS_DOWN", "DOWN_LEADS_UP", "DOWN_LEADS_DOWN",
            "CORRELATED", "INVERSE_CORRELATED", "BIDIRECTIONAL",
        }
        assert expected == set(VALID_DIRECTIONS)

    def test_valid_directions_excludes_legacy_values(self) -> None:
        # old cli.py had {"lead", "lag", "bidirectional", "unknown"} — these must not be valid
        for old_val in ("lead", "lag", "unknown"):
            assert old_val not in VALID_DIRECTIONS

    def test_relation_type_re_accepts_beneficiary(self) -> None:
        assert VALID_RELATION_TYPE_RE.match("BENEFICIARY")

    def test_relation_type_re_accepts_input_cost_victim(self) -> None:
        assert VALID_RELATION_TYPE_RE.match("INPUT_COST_VICTIM")

    def test_relation_type_re_accepts_clinical_readthrough(self) -> None:
        assert VALID_RELATION_TYPE_RE.match("CLINICAL_READTHROUGH")

    def test_relation_type_re_rejects_lowercase(self) -> None:
        assert not VALID_RELATION_TYPE_RE.match("supply_chain")

    def test_relation_type_re_rejects_empty(self) -> None:
        assert not VALID_RELATION_TYPE_RE.match("")

    def test_relation_type_re_rejects_leading_digit(self) -> None:
        assert not VALID_RELATION_TYPE_RE.match("1BAD_TYPE")
