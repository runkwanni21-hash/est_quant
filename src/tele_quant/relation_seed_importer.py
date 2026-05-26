"""Relation Seed Importer — sector_relation_seeds YAML → relation_edges DB.

보안 정책:
- "수혜 확정", "피해 확정" 등 단정 표현 절대 금지.
- 상관관계는 인과관계가 아님. 출력 시 반드시 명시.
- evidence_url 없는 HIGH → MEDIUM 강등 + rule_id에 "audit_high" 플래그.
- LOW confidence → active=False (watch_only). DB에는 저장하되 비활성.
- 임의로 모든 KR 티커에 .KS를 붙이지 말 것. KOSDAQ은 .KQ 필요.
- 브로커명·단기 오탐 티커 오인 방지.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from tele_quant.db import Store

log = logging.getLogger(__name__)

__all__ = [
    "VALID_DIRECTIONS",
    "VALID_RELATION_TYPE_RE",
    "ImportResult",
    "KRTickerResolver",
    "SeedEdge",
    "build_relation_edge_dict",
    "import_sector_seeds",
    "load_all_seed_files",
    "load_kq_set",
]

# ── 허용 enum ─────────────────────────────────────────────────────────────────

_VALID_CONFIDENCES: frozenset[str] = frozenset({"HIGH", "MEDIUM", "LOW"})

_VALID_DIRECTIONS: frozenset[str] = frozenset({
    "UP_LEADS_UP",
    "UP_LEADS_DOWN",
    "DOWN_LEADS_UP",
    "DOWN_LEADS_DOWN",
    "CORRELATED",
    "INVERSE_CORRELATED",
    "BIDIRECTIONAL",
})

# relation_type는 열린 집합 — enum 검증 대신 형식 검증만
_RELATION_TYPE_RE = re.compile(r"^[A-Z][A-Z0-9_]{1,49}$")

# ── 공개 alias (cli.py 등 외부에서 중복 정의 없이 import 가능) ──────────────
VALID_DIRECTIONS: frozenset[str] = _VALID_DIRECTIONS
VALID_RELATION_TYPE_RE = _RELATION_TYPE_RE

# expected_lag 파싱
_LAG_RE = re.compile(r"^(\d+(?:\.\d+)?)(h|d|w)$")

# KR bare ticker
_BARE_KR_RE = re.compile(r"^\d{6}$")

# Confidence → relation_score
_CONF_SCORE: dict[str, float] = {
    "HIGH": 0.80,
    "MEDIUM": 0.60,
    "LOW": 0.30,
}


# ── KR 티커 리졸버 ─────────────────────────────────────────────────────────────


def load_kq_set(aliases_path: str | Path | None = None) -> frozenset[str]:
    """ticker_aliases.yml에서 KOSDAQ 종목 bare 6자리 코드 집합 반환.

    KOSDAQ bare 코드가 집합에 있으면 .KQ, 없으면 .KS로 보정한다.
    """
    try:
        import yaml

        path = Path(aliases_path or "config/ticker_aliases.yml")
        if not path.exists():
            log.warning("ticker_aliases.yml not found at %s — KQ resolution degraded", path)
            return frozenset()

        with open(path) as f:
            data = yaml.safe_load(f) or {}

        kq: set[str] = set()
        for entry in data.get("stocks", []):
            sym = str(entry.get("symbol", ""))
            board = str(entry.get("board", ""))
            if sym.endswith(".KQ"):
                kq.add(sym[:-3])
            elif board == "KOSDAQ" and re.match(r"^\d{6}$", sym):
                kq.add(sym)
        return frozenset(kq)
    except Exception as exc:
        log.warning("load_kq_set failed: %s", exc)
        return frozenset()


class KRTickerResolver:
    """6자리 bare KR 티커를 .KS/.KQ로 보정하는 리졸버.

    보정 순서:
    1. 이미 suffix가 있으면 그대로.
    2. KQ 집합에 있으면 .KQ.
    3. KQ 집합에 없으면 .KS.
    4. 미확인은 unresolved 로 기록.
    """

    def __init__(self, kq_set: frozenset[str] | None = None, aliases_path: str | Path | None = None) -> None:
        self._kq = kq_set if kq_set is not None else load_kq_set(aliases_path)
        self._resolved: dict[str, str] = {}
        self._unresolved: list[str] = []

    def resolve(self, symbol: str, market: str = "") -> tuple[str, bool]:
        """(resolved_symbol, was_bare) 반환.

        was_bare=True이면 suffix를 새로 붙인 것.
        """
        if symbol in self._resolved:
            return self._resolved[symbol], False

        # 이미 suffix 있음
        if "." in symbol or not _BARE_KR_RE.match(symbol):
            return symbol, False

        # KR market이거나 market 미지정
        if market and market.upper() not in ("KR", ""):
            return symbol, False

        suffix = ".KQ" if symbol in self._kq else ".KS"
        resolved = symbol + suffix
        self._resolved[symbol] = resolved
        return resolved, True

    def resolve_symbol_and_market(self, symbol: str, market: str) -> tuple[str, str, bool]:
        """(resolved_symbol, resolved_market, was_bare) 반환."""
        if market.upper() == "KR" or (not market and _BARE_KR_RE.match(symbol)):
            res, was_bare = self.resolve(symbol, "KR")
            return res, "KR", was_bare
        return symbol, market, False

    @property
    def unresolved(self) -> list[str]:
        return list(self._unresolved)


# ── 데이터 모델 ────────────────────────────────────────────────────────────────


@dataclass
class SeedEdge:
    """YAML에서 파싱된 relation edge."""

    source_symbol: str
    source_name: str
    source_market: str
    source_sector: str
    target_symbol: str
    target_name: str
    target_market: str
    target_sector: str
    relation_type: str
    direction: str
    expected_lag_hours: int
    confidence: str               # HIGH / MEDIUM / LOW
    relation_score: float
    rationale: str
    evidence_url: str
    evidence_title: str
    trading_note: str
    active: bool
    watch_only: bool              # LOW confidence
    audit_high: bool              # HIGH downgraded to MEDIUM (no URL)
    is_factor_edge: bool
    source_3m_move_pct: float | None
    rule_id: str
    sector_id: str


@dataclass
class ImportResult:
    """import_sector_seeds 실행 결과 요약."""

    edges_read: int = 0
    self_loops_removed: int = 0
    duplicates_found: int = 0
    bare_kr_resolved: int = 0
    bare_kr_unresolved: int = 0
    high_downgraded: int = 0      # HIGH without URL → MEDIUM
    low_watch_only: int = 0
    factor_edges: int = 0
    inserted: int = 0
    updated: int = 0
    skipped: int = 0
    unresolved_symbols: list[str] = field(default_factory=list)
    sector_summary: dict[str, int] = field(default_factory=dict)
    audit_notes: list[str] = field(default_factory=list)


# ── 파서 헬퍼 ─────────────────────────────────────────────────────────────────


def _parse_lag_hours(lag_str: str | None) -> int:
    """'3d' / '5d' / '1w' / '12h' → 시간(int) 변환."""
    if not lag_str:
        return 24
    m = _LAG_RE.match(str(lag_str).strip().lower())
    if not m:
        return 24
    n = float(m.group(1))
    unit = m.group(2)
    if unit == "h":
        return int(n)
    if unit == "d":
        return int(n * 24)
    if unit == "w":
        return int(n * 168)
    return 24


def _parse_evidence(evidence_list: list[dict[str, Any]]) -> tuple[str, str]:
    """evidence 리스트에서 첫 번째 유효한 (title, url) 반환."""
    for ev in evidence_list or []:
        url = str(ev.get("url") or "").strip()
        title = str(ev.get("title") or "").strip()
        # placeholder URL 제외
        if url and url not in ("", "null", "N/A", "TBD", "#") and url.startswith("http"):
            return title, url
    # fallback: url 없어도 title은 반환
    for ev in evidence_list or []:
        title = str(ev.get("title") or "").strip()
        if title:
            return title, ""
    return "", ""


def _is_valid_relation_type(rt: str) -> bool:
    return bool(_RELATION_TYPE_RE.match(rt))


# ── Edge 파싱 ─────────────────────────────────────────────────────────────────


def _parse_edge(
    raw: dict[str, Any],
    sector_id: str,
    resolver: KRTickerResolver,
    is_factor: bool,
    result: ImportResult,
) -> SeedEdge | None:
    """raw dict → SeedEdge. 문제 있으면 None."""
    src_sym = str(raw.get("source_symbol") or "").strip()
    src_name = str(raw.get("source_name") or "").strip()
    src_mkt = str(raw.get("source_market") or "").strip().upper()
    tgt_sym = str(raw.get("target_symbol") or "").strip()
    tgt_name = str(raw.get("target_name") or "").strip()
    tgt_mkt = str(raw.get("target_market") or "").strip().upper()
    relation_type = str(raw.get("relation_type") or "").strip()
    direction = str(raw.get("direction") or "").strip()
    expected_lag = str(raw.get("expected_lag") or "").strip()
    confidence = str(raw.get("confidence") or "MEDIUM").strip().upper()
    rationale = str(raw.get("rationale") or "").strip()
    trading_note = str(raw.get("trading_note") or "").strip()
    evidence_list: list[dict[str, Any]] = raw.get("evidence") or []
    src_3m = raw.get("source_3m_move_pct")

    # 필수 필드
    if not src_sym or not tgt_sym or not relation_type or not direction:
        log.debug("Edge skipped — missing required field: %s→%s", src_sym, tgt_sym)
        result.skipped += 1
        return None

    # factor edge는 source가 commodity symbol이므로 KR resolver 건너뜀
    if is_factor:
        result.factor_edges += 1
    else:
        # KR bare ticker 보정 (source)
        if _BARE_KR_RE.match(src_sym) and src_mkt in ("KR", ""):
            resolved, was_bare = resolver.resolve(src_sym, "KR")
            if was_bare:
                result.bare_kr_resolved += 1
            src_sym = resolved  # 캐시 hit(was_bare=False)일 때도 항상 갱신
            src_mkt = "KR"

        # KR bare ticker 보정 (target)
        if _BARE_KR_RE.match(tgt_sym) and tgt_mkt in ("KR", ""):
            resolved, was_bare = resolver.resolve(tgt_sym, "KR")
            if was_bare:
                result.bare_kr_resolved += 1
            tgt_sym = resolved  # 캐시 hit(was_bare=False)일 때도 항상 갱신
            tgt_mkt = "KR"

    # self-loop 제거
    if src_sym == tgt_sym:
        log.debug("Self-loop removed: %s", src_sym)
        result.self_loops_removed += 1
        return None

    # direction enum 검증
    if direction not in _VALID_DIRECTIONS:
        log.warning("Unknown direction=%s for %s→%s, keeping", direction, src_sym, tgt_sym)

    # relation_type 형식 검증
    if not _is_valid_relation_type(relation_type):
        log.warning("Invalid relation_type=%s, skipping", relation_type)
        result.skipped += 1
        return None

    # confidence 정규화
    if confidence not in _VALID_CONFIDENCES:
        confidence = "MEDIUM"

    # evidence URL
    ev_title, ev_url = _parse_evidence(evidence_list)

    # HIGH without evidence_url → MEDIUM + audit_high 플래그
    audit_high = False
    if confidence == "HIGH" and not ev_url:
        confidence = "MEDIUM"
        audit_high = True
        result.high_downgraded += 1
        result.audit_notes.append(
            f"audit_high: {src_sym}→{tgt_sym} [{relation_type}] evidence_url 없어 MEDIUM 강등"
        )

    # LOW → watch_only + active=False
    watch_only = confidence == "LOW"
    active = not watch_only
    if watch_only:
        result.low_watch_only += 1

    score = _CONF_SCORE.get(confidence, 0.30)

    lag_hours = _parse_lag_hours(expected_lag)

    flags: list[str] = []
    if audit_high:
        flags.append("audit_high")
    if watch_only:
        flags.append("watch_only")
    if is_factor:
        flags.append("factor_edge")
    rule_id = f"seed:{sector_id}" + (":" + ":".join(flags) if flags else "")

    return SeedEdge(
        source_symbol=src_sym,
        source_name=src_name,
        source_market=src_mkt or ("COMMODITY" if is_factor else ""),
        source_sector="",
        target_symbol=tgt_sym,
        target_name=tgt_name,
        target_market=tgt_mkt or "",
        target_sector="",
        relation_type=relation_type,
        direction=direction,
        expected_lag_hours=lag_hours,
        confidence=confidence,
        relation_score=score,
        rationale=rationale,
        evidence_url=ev_url,
        evidence_title=ev_title,
        trading_note=trading_note,
        active=active,
        watch_only=watch_only,
        audit_high=audit_high,
        is_factor_edge=is_factor,
        source_3m_move_pct=float(src_3m) if src_3m is not None else None,
        rule_id=rule_id,
        sector_id=sector_id,
    )


# ── 파일 로더 ─────────────────────────────────────────────────────────────────


def load_all_seed_files(
    seed_dir: str | Path,
    resolver: KRTickerResolver | None = None,
) -> tuple[list[SeedEdge], ImportResult]:
    """seed_dir의 모든 sector yml을 읽어 SeedEdge 리스트 반환."""
    import yaml

    seed_path = Path(seed_dir)
    if resolver is None:
        resolver = KRTickerResolver()

    result = ImportResult()
    all_edges: list[SeedEdge] = []
    seen_keys: set[tuple[str, str, str, str]] = set()

    yml_files = sorted(f for f in seed_path.glob("*.yml") if f.name != "sector_manifest.yml")

    for yml_path in yml_files:
        try:
            with open(yml_path, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
        except Exception as exc:
            log.error("Failed to parse %s: %s", yml_path.name, exc)
            continue

        sr: dict[str, Any] = data.get("sector_relation_seeds", {})
        sector_id: str = str(sr.get("sector_id", yml_path.stem))
        edges_raw: list[dict[str, Any]] = sr.get("edges") or []
        factor_raw: list[dict[str, Any]] = sr.get("factor_edges") or []
        file_count = 0

        for raw in edges_raw:
            result.edges_read += 1
            edge = _parse_edge(raw, sector_id, resolver, is_factor=False, result=result)
            if edge is None:
                continue

            key = (edge.source_symbol, edge.target_symbol, edge.relation_type, edge.direction)
            if key in seen_keys:
                result.duplicates_found += 1
                continue
            seen_keys.add(key)
            all_edges.append(edge)
            file_count += 1

        for raw in factor_raw:
            result.edges_read += 1
            edge = _parse_edge(raw, sector_id, resolver, is_factor=True, result=result)
            if edge is None:
                continue

            key = (edge.source_symbol, edge.target_symbol, edge.relation_type, edge.direction)
            if key in seen_keys:
                result.duplicates_found += 1
                continue
            seen_keys.add(key)
            all_edges.append(edge)
            file_count += 1

        result.sector_summary[sector_id] = file_count

    return all_edges, result


# ── DB edge 딕셔너리 변환 ─────────────────────────────────────────────────────


def build_relation_edge_dict(edge: SeedEdge) -> dict[str, Any]:
    """SeedEdge → upsert_relation_edges에 넘길 dict."""
    return {
        "source_symbol": edge.source_symbol,
        "source_name": edge.source_name,
        "source_market": edge.source_market,
        "source_sector": edge.source_sector,
        "target_symbol": edge.target_symbol,
        "target_name": edge.target_name,
        "target_market": edge.target_market,
        "target_sector": edge.target_sector,
        "relation_type": edge.relation_type,
        "direction": edge.direction,
        "expected_lag_hours": edge.expected_lag_hours,
        "confidence": "INACTIVE" if not edge.active else edge.confidence,
        "relation_score": edge.relation_score,
        "evidence_type": "SEED_YAML",
        "evidence_title": edge.evidence_title,
        "evidence_url": edge.evidence_url,
        "evidence_summary": edge.rationale[:500] if edge.rationale else "",
        "rule_id": edge.rule_id,
        "source_return_3m_pct": edge.source_3m_move_pct,
        # active: LOW confidence는 0 (DB 쪽에서 INACTIVE 처리)
        "active": 1 if edge.active else 0,
    }


# ── 메인 엔트리포인트 ─────────────────────────────────────────────────────────


def import_sector_seeds(
    seed_dir: str | Path,
    store: Store | None = None,
    dry_run: bool = True,
    aliases_path: str | Path | None = None,
) -> ImportResult:
    """sector relation seed YAML 전체를 읽어 DB에 저장.

    Args:
        seed_dir:     sector yml 디렉토리.
        store:        DB Store. None이면 dry_run과 동일하게 동작.
        dry_run:      True면 DB에 저장하지 않고 결과만 반환.
        aliases_path: ticker_aliases.yml 경로.

    Returns:
        ImportResult — import 통계 요약.

    Note:
        "상관관계는 인과관계가 아님". 저장된 edge는 리서치 보조 목적.
        매수·매도 권장 아님.
    """
    resolver = KRTickerResolver(aliases_path=aliases_path)
    edges, result = load_all_seed_files(seed_dir, resolver)

    if not dry_run and store is not None:
        edge_dicts = [build_relation_edge_dict(e) for e in edges]
        inserted, updated = store.upsert_relation_edges(edge_dicts)
        result.inserted = inserted
        result.updated = updated
        # 이전 run에서 bare KR 티커로 저장된 seed 엣지 정리
        _cleanup_bare_kr_seed_edges(store)
    else:
        result.inserted = 0
        result.updated = 0

    result.unresolved_symbols = resolver.unresolved

    log.info(
        "import_sector_seeds: read=%d self_loop=%d dup=%d kr_resolved=%d "
        "high_downgraded=%d low_watch=%d factor=%d inserted=%d updated=%d dry=%s",
        result.edges_read,
        result.self_loops_removed,
        result.duplicates_found,
        result.bare_kr_resolved,
        result.high_downgraded,
        result.low_watch_only,
        result.factor_edges,
        result.inserted,
        result.updated,
        dry_run,
    )
    return result


def _cleanup_bare_kr_seed_edges(store: Store) -> int:
    """seed: rule_id를 가진 bare KR 티커(6자리 숫자) 엣지를 DB에서 삭제.

    resolver 캐시 버그로 이전 run에 bare 코드로 저장된 행 정리용.
    Returns: 삭제된 행 수.
    """
    with store.connect() as conn:
        rows = conn.execute(
            "SELECT id, source_symbol, target_symbol FROM relation_edges WHERE rule_id LIKE 'seed:%'"
        ).fetchall()
        to_delete = [
            r["id"]
            for r in rows
            if _BARE_KR_RE.match(str(r["source_symbol"] or ""))
            or _BARE_KR_RE.match(str(r["target_symbol"] or ""))
        ]
        if to_delete:
            placeholders = ",".join("?" * len(to_delete))
            conn.execute(
                f"DELETE FROM relation_edges WHERE id IN ({placeholders})", to_delete
            )
            conn.commit()
            log.info("_cleanup_bare_kr_seed_edges: %d bare KR seed 엣지 삭제", len(to_delete))
    return len(to_delete)


# ── stock_snapshot용 relation 조회 헬퍼 ──────────────────────────────────────


_BENEFICIARY_TYPES = frozenset({
    "BENEFICIARY", "AI_CAPEX_SPILLOVER", "SUPPLIER", "CUSTOMER",
    "PEER_MOMENTUM", "SUPPLY_CHAIN",
})
_VICTIM_TYPES = frozenset({
    "COMPETITOR", "INPUT_COST_VICTIM", "COST_BURDEN", "DEMAND_SHIFT",
    "SUBSTITUTE_RISK",
})
_PEER_TYPES = frozenset({"PEER", "COMPETITOR"})

_FORBIDDEN_OUTPUT = frozenset({
    "매수 권장", "매도 권장", "확정 수익", "수혜 확정", "피해 확정",
    "세력 매집 확정", "기관 매집 확정", "반드시 상승",
})


@dataclass
class RelationHint:
    """/분석 출력용 관계 힌트."""

    symbol: str
    name: str
    relation_type: str
    direction: str
    confidence: str
    expected_lag_hours: int
    rationale: str            # 1줄 요약
    category: str             # BENEFICIARY / VICTIM / PEER
    watch_only: bool


def get_relation_hints(
    symbol: str,
    store: Store | None,
    max_per_category: int = 3,
) -> dict[str, list[RelationHint]]:
    """relation_edges DB에서 심볼 관련 힌트 조회.

    반환:
        {"beneficiary": [...], "victim": [...], "peer": [...]}

    주의: 확정 표현 없이 "수혜 가능성", "후행 반응 관찰" 수준으로만 표현.
    상관관계는 인과관계가 아님.
    """
    if store is None:
        return {"beneficiary": [], "victim": [], "peer": []}

    try:
        all_edges = store.get_all_relation_edges(active_only=True)
    except Exception as exc:
        log.debug("get_relation_hints: DB error for %s: %s", symbol, exc)
        return {"beneficiary": [], "victim": [], "peer": []}

    beneficiaries: list[RelationHint] = []
    victims: list[RelationHint] = []
    peers: list[RelationHint] = []

    for e in all_edges:
        src = str(e.get("source_symbol") or "")
        tgt = str(e.get("target_symbol") or "")
        rtype = str(e.get("relation_type") or "")
        direction = str(e.get("direction") or "")
        conf = str(e.get("confidence") or "LOW")
        lag = int(e.get("expected_lag_hours") or 24)
        rationale = str(e.get("evidence_summary") or "")[:120]
        rule_id = str(e.get("rule_id") or "")
        watch_only = "watch_only" in rule_id

        if src == symbol:
            peer_sym, peer_name = tgt, str(e.get("target_name") or tgt)
        elif tgt == symbol:
            peer_sym, peer_name = src, str(e.get("source_name") or src)
        else:
            continue

        # 숫자만으로 된 심볼(가격 오인 값)은 제외
        try:
            from tele_quant.ticker_universe import is_valid_symbol
            if not is_valid_symbol(peer_sym):
                continue
        except Exception:
            pass

        hint = RelationHint(
            symbol=peer_sym,
            name=peer_name,
            relation_type=rtype,
            direction=direction,
            confidence=conf,
            expected_lag_hours=lag,
            rationale=rationale,
            category="",
            watch_only=watch_only,
        )

        if rtype in _BENEFICIARY_TYPES and direction in ("UP_LEADS_UP", "DOWN_LEADS_DOWN"):
            hint.category = "beneficiary"
            beneficiaries.append(hint)
        elif rtype in _VICTIM_TYPES or direction in ("UP_LEADS_DOWN", "DOWN_LEADS_UP"):
            hint.category = "victim"
            victims.append(hint)
        if rtype in _PEER_TYPES:
            hint.category = "peer"
            peers.append(hint)

    # confidence 우선 정렬: HIGH > MEDIUM > LOW
    _conf_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}

    def _sort_key(h: RelationHint) -> int:
        return _conf_order.get(h.confidence, 9)

    beneficiaries.sort(key=_sort_key)
    victims.sort(key=_sort_key)
    peers.sort(key=_sort_key)

    # canonical symbol 기준 중복 제거 (한글명/영문명 같은 종목 중복 방지)
    def _dedup(hints: list[RelationHint]) -> list[RelationHint]:
        try:
            from tele_quant.financial_sanity import canonicalize_kr_ticker
            seen: dict[str, RelationHint] = {}
            for h in hints:
                canon = canonicalize_kr_ticker(h.symbol)
                if canon not in seen:
                    seen[canon] = h
                else:
                    # HIGH confidence 우선 유지
                    if _conf_order.get(h.confidence, 9) < _conf_order.get(seen[canon].confidence, 9):
                        seen[canon] = h
            return list(seen.values())
        except Exception:
            return hints

    beneficiaries = _dedup(beneficiaries)
    victims = _dedup(victims)
    peers = _dedup(peers)

    return {
        "beneficiary": beneficiaries[:max_per_category],
        "victim": victims[:max_per_category],
        "peer": peers[:max_per_category],
    }


def format_relation_hints(hints: dict[str, list[RelationHint]]) -> str:
    """RelationHint dict → 텔레그램 출력 텍스트.

    금지: "수혜 확정", "피해 확정", "매수 권장" 등.
    허용: "수혜 가능성", "후행 반응 관찰", "상대적 비용 압박 리스크".
    상관관계는 인과관계가 아님.
    """
    lines: list[str] = []

    def _lag_str(h: RelationHint) -> str:
        if h.expected_lag_hours < 24:
            return f"{h.expected_lag_hours}h 후행"
        d = h.expected_lag_hours // 24
        return f"{d}일 후행"

    def _fmt_sym(h: RelationHint) -> str:
        """canonical 형식 symbol, bare 1~5자리 숫자는 표시 금지."""
        try:
            from tele_quant.financial_sanity import canonicalize_kr_ticker, is_bare_kr_ticker
            sym = canonicalize_kr_ticker(h.symbol)
            if is_bare_kr_ticker(sym):
                return ""
        except Exception:
            sym = h.symbol
        return sym

    def _fmt_hint(h: RelationHint) -> str | None:
        sym = _fmt_sym(h)
        if not sym:
            return None
        name = h.name or sym
        tag = f"[{h.confidence}·{_lag_str(h)}]"
        watch = " (관찰전용)" if h.watch_only else ""
        base = f"  • {name}({sym}) {tag}{watch}"
        if h.rationale:
            return base + f"\n    └ {h.rationale[:100]}"
        return base

    bene = hints.get("beneficiary", [])
    if bene:
        bene_lines = [_fmt_hint(h) for h in bene]
        bene_lines = [x for x in bene_lines if x]
        if bene_lines:
            lines.append("🟢 수혜 가능성 후보:")
            lines.extend(bene_lines)

    vict = hints.get("victim", [])
    if vict:
        vict_lines = [_fmt_hint(h) for h in vict]
        vict_lines = [x for x in vict_lines if x]
        if vict_lines:
            lines.append("🔴 상대적 부담 후보:")
            lines.extend(vict_lines)

    peer = hints.get("peer", [])
    if peer:
        peer_lines = [_fmt_hint(h) for h in peer]
        peer_lines = [x for x in peer_lines if x]
        if peer_lines:
            lines.append("🔵 경쟁/피어 후보:")
            lines.extend(peer_lines)

    if lines:
        lines.append("  ※ 상관관계는 인과관계가 아님. 리서치 보조 목적.")

    return "\n".join(lines)
