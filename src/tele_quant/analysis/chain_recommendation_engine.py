"""Chain Recommendation Engine — 관계 체인 기반 후보 점수화.

relation_seed_importer.get_relation_hints()를 넘어서 실제 체인 후보 점수화.

점수 공식 (100점):
- relation_confidence: 25점 (HIGH=25, MEDIUM=15, LOW=5)
- evidence_quality: 20점 (소스 이벤트 증거 품질)
- source_event_score: 15점 (소스 폴라리티·가격 반응·신뢰도)
- target_technical_readiness: 20점 (타깃 RSI/MA/OBV)
- target_institutional_flow: 10점 (타깃 수급)
- sector_momentum: 10점 (섹터 모멘텀)
- overheat_penalty: 차감

LOW confidence → watch_only=True (관찰전용).
'수혜 확정' / '피해 확정' 금지.
공개 정보 기반 리서치 보조. 투자 판단 책임은 사용자에게 있음.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from tele_quant.analysis.report_models import ChainCandidate
    from tele_quant.db import Store

log = logging.getLogger(__name__)

_RELATION_CONFIDENCE: dict[str, float] = {
    "HIGH": 25.0,
    "MEDIUM": 15.0,
    "LOW": 5.0,
}

# lag 기준: 1일~1개월 이내 우선
_LAG_PRIORITY: dict[str, int] = {
    "1d": 5, "2d": 4, "3d": 4, "5d": 3, "1w": 3, "2w": 2, "1m": 1, "3m": 0,
}


# ── relation edges 조회 ───────────────────────────────────────────────────────


def _get_edges_for_source(symbol: str, store: Store | None) -> list[dict[str, Any]]:
    """DB relation_edges에서 source=symbol인 엣지 목록."""
    if store is None:
        return []
    try:
        edges = store.get_all_relation_edges(active_only=True)
        return [e for e in edges if e.get("source_symbol") == symbol]
    except Exception as exc:
        log.debug("[chain_engine] edges failed %s: %s", symbol, exc)
        return []


def _get_sector_seed_hints(symbol: str, store: Store | None) -> list[dict[str, Any]]:
    """relation_seed_importer에서 sector seed 기반 힌트."""
    try:

        if store is None:
            return []
        # DB에서 직접 조회 (import 없이)
        return _get_edges_for_source(symbol, store)
    except Exception as exc:
        log.debug("[chain_engine] seed hints failed: %s", exc)
        return []


# ── 타깃 기술적 준비도 점수 ────────────────────────────────────────────────


def _target_technical_score(target_sym: str) -> tuple[float, float | None, str]:
    """타깃 종목의 기술적 준비도 점수 (0~100) + RSI + MA 위치."""
    try:
        from tele_quant.analysis.technical_signal_engine import (
            compute_technical_accumulation_signal,
        )

        sig = compute_technical_accumulation_signal(target_sym, period="3mo")
        rsi = sig.rsi_1d
        score = max(0, sig.score - 15) if sig.overheat else sig.score
        above_ma = "MA20 위" if sig.above_ma20 else ("MA20 아래" if sig.above_ma20 is False else "확인 제한")
        return score, rsi, above_ma
    except Exception as exc:
        log.debug("[chain_engine] tech score failed %s: %s", target_sym, exc)
        return 40.0, None, "확인 제한"


# ── 타깃 수급 점수 ────────────────────────────────────────────────────────


def _target_flow_score(target_sym: str, rsi: float | None) -> float:
    """타깃 종목의 수급 점수 (0~100 → 0~10점으로 환산)."""
    try:
        from tele_quant.analysis.institutional_flow import compute_institutional_flow

        sig = compute_institutional_flow(target_sym, rsi=rsi)
        return sig.flow_score / 10.0
    except Exception:
        return 5.0


# ── 증거 품질 점수 ────────────────────────────────────────────────────────


def _evidence_quality_score(
    evidence_items: list[Any],
    source_return: float | None,
    source_polarity: str,
    source_confidence: str,
) -> tuple[float, float]:
    """증거 품질 점수(0~20) + 소스 이벤트 점수(0~15)."""
    ev_score = 8.0  # 기본
    if evidence_items:
        high_conf = sum(1 for e in evidence_items if getattr(e, "confidence", "") == "HIGH")
        ev_score = min(20.0, 8.0 + high_conf * 4.0)

    src_score = 7.0
    if source_polarity in ("POSITIVE", "NEGATIVE"):
        src_score += 4.0
    if source_confidence == "HIGH":
        src_score += 4.0
    elif source_confidence == "MEDIUM":
        src_score += 2.0
    if source_return is not None and abs(source_return) > 3:
        src_score += 3.0
    src_score = min(15.0, src_score)

    return ev_score, src_score


# ── 섹터 모멘텀 ───────────────────────────────────────────────────────────


def _sector_momentum_score(sector_id: str) -> float:
    """섹터 모멘텀 점수 (0~10). 단순 proxy."""
    # 섹터별 ETF 수익률 등으로 대체 가능 — 현재는 중립 5점 반환
    try:
        from tele_quant.sector_macro import get_sector_macro_score

        raw = get_sector_macro_score(sector_id)
        return min(10.0, raw / 10.0)
    except Exception:
        return 5.0


# ── 과열 패널티 ───────────────────────────────────────────────────────────


def _overheat_penalty(target_rsi: float | None, target_ret_20d: float | None) -> float:
    penalty = 0.0
    if target_rsi is not None and target_rsi > 75:
        penalty += 8.0
    elif target_rsi is not None and target_rsi > 70:
        penalty += 4.0
    if target_ret_20d is not None and target_ret_20d > 30:
        penalty += 5.0
    return penalty


# ── 체인 후보 분류 ────────────────────────────────────────────────────────


_BENEFICIARY_TYPES = {"BENEFICIARY", "CUSTOMER", "SUPPLIER", "PEER_MOMENTUM"}
_BURDEN_TYPES = {"VICTIM", "INPUT_COST_VICTIM", "COMPETITOR"}
_PEER_TYPES = {"PEER", "BIDIRECTIONAL", "CORRELATED"}


def _classify_candidate(rel_type: str, direction: str) -> str:
    """relation_type 기반 분류: beneficiary / burden / peer."""
    if rel_type in _BENEFICIARY_TYPES or direction in ("UP_LEADS_UP", "DOWN_LEADS_DOWN"):
        return "beneficiary"
    if rel_type in _BURDEN_TYPES or direction in ("UP_LEADS_DOWN", "DOWN_LEADS_UP"):
        return "burden"
    if rel_type in _PEER_TYPES:
        return "peer"
    return "peer"


# ── lag 우선순위 점수 ─────────────────────────────────────────────────────


def _lag_score(lag: str) -> int:
    lag_clean = lag.lower().strip() if lag else ""
    return _LAG_PRIORITY.get(lag_clean, 0)


# ── 메인 ──────────────────────────────────────────────────────────────────────


def build_chain_candidates(
    symbol: str,
    market: str,
    store: Store | None,
    evidence_items: list[Any] | None = None,
    source_return: float | None = None,
    source_polarity: str = "NEUTRAL",
    source_confidence: str = "MEDIUM",
    sector_id: str = "",
    max_per_type: int = 3,
) -> tuple[list[ChainCandidate], list[ChainCandidate], list[ChainCandidate]]:  # type: ignore[name-defined]
    """관계 체인 후보 빌드.

    Returns:
        (beneficiaries, burdens, peers) — 각 max_per_type개 이하
    """
    from tele_quant.analysis.report_models import ChainCandidate
    from tele_quant.relation_feed import _NAME_MAP

    ev_items = evidence_items or []

    # 엣지 수집
    edges = _get_edges_for_source(symbol, store)
    if not edges:
        # supply_chain_alpha fallback
        try:
            from tele_quant.supply_chain_alpha import (
                MoverEvent,
                _match_mover_to_rules,
                load_supply_chain_rules,
            )

            name = _NAME_MAP.get(symbol, symbol)
            rules = load_supply_chain_rules()
            mover = MoverEvent(
                symbol=symbol, name=name, market=market,
                return_1d=source_return or 5.0,
                direction="BULLISH" if source_polarity != "NEGATIVE" else "BEARISH",
                confidence=source_confidence,
                volume_ratio=1.5, reason_type="catalyst", reason_ko="체인 조회",
            )
            matched = _match_mover_to_rules(mover, rules)
            for rule in matched[:4]:
                for grp in rule.get("beneficiaries", []):
                    for sym_e in grp.get("symbols", []):
                        tsym = sym_e.get("symbol", "")
                        if tsym and tsym != symbol:
                            edges.append({
                                "source_symbol": symbol,
                                "target_symbol": tsym,
                                "relation_type": "BENEFICIARY",
                                "direction": "UP_LEADS_UP",
                                "confidence": grp.get("confidence", "MEDIUM"),
                                "expected_lag": grp.get("expected_lag", "1w"),
                                "connection_reason": grp.get("connection", ""),
                                "relation_score": 0.6,
                                "active": True,
                            })
                for grp in rule.get("victims_on_bearish", [])[:2]:
                    for sym_e in grp.get("symbols", []):
                        tsym = sym_e.get("symbol", "")
                        if tsym and tsym != symbol:
                            edges.append({
                                "source_symbol": symbol,
                                "target_symbol": tsym,
                                "relation_type": "VICTIM",
                                "direction": "UP_LEADS_DOWN",
                                "confidence": "MEDIUM",
                                "expected_lag": "1w",
                                "connection_reason": grp.get("connection", ""),
                                "relation_score": 0.5,
                                "active": True,
                            })
        except Exception as exc:
            log.debug("[chain_engine] supply_chain fallback failed: %s", exc)

    # 공통 증거 점수 계산
    ev_score, src_score = _evidence_quality_score(ev_items, source_return, source_polarity, source_confidence)

    # 섹터 모멘텀
    sec_score = _sector_momentum_score(sector_id) if sector_id else 5.0

    beneficiaries: list[ChainCandidate] = []
    burdens: list[ChainCandidate] = []
    peers: list[ChainCandidate] = []
    seen: set[str] = set()

    for edge in edges:
        tsym = edge.get("target_symbol", "")
        if not tsym or tsym in seen or tsym == symbol:
            continue
        # 숫자만으로 이루어진 심볼(가격 오인) 및 유효하지 않은 심볼 필터링
        try:
            from tele_quant.ticker_universe import is_valid_symbol
            if not is_valid_symbol(tsym):
                log.debug("[chain_engine] invalid symbol filtered: %s", tsym)
                continue
        except Exception:
            pass
        seen.add(tsym)

        rel_type = edge.get("relation_type", "PEER")
        direction = edge.get("direction", "")
        confidence = edge.get("confidence", "MEDIUM") or "MEDIUM"
        lag = edge.get("expected_lag", "") or ""
        reason = edge.get("connection_reason", "") or edge.get("reason", "")
        cat = _classify_candidate(rel_type, direction)
        # ticker_universe DB에서 이름 조회 (fallback: _NAME_MAP → symbol)
        try:
            from tele_quant.ticker_universe import get_display_name
            name = get_display_name(tsym, store)
        except Exception:
            name = _NAME_MAP.get(tsym, tsym)

        # 타깃 기술 점수 (빠른 계산 — 이미 캐시됨)
        tech_score, t_rsi, t_ma = _target_technical_score(tsym)
        flow_score = _target_flow_score(tsym, t_rsi)
        penalty = _overheat_penalty(t_rsi, None)

        # 최종 체인 점수
        conf_pts = _RELATION_CONFIDENCE.get(confidence, 15.0)
        total = (
            conf_pts            # 25
            + ev_score          # 20
            + src_score         # 15
            + tech_score * 0.2  # 20
            + flow_score        # 10
            + sec_score         # 10
            - penalty
        )
        total = min(max(total, 0), 100)

        cand = ChainCandidate(
            symbol=tsym,
            name=name,
            relation_type=rel_type,
            direction=direction,
            confidence=confidence,
            expected_lag=lag,
            connection_reason=reason,
            relation_confidence_score=conf_pts,
            evidence_quality_score=ev_score,
            source_event_score=src_score,
            target_technical_score=tech_score * 0.2,
            target_flow_score=flow_score,
            sector_momentum_score=sec_score,
            overheat_penalty=penalty,
            chain_score=total,
            target_rsi=t_rsi,
            target_ma_position=t_ma,
            watch_only=(confidence == "LOW"),
        )

        if cat == "beneficiary":
            beneficiaries.append(cand)
        elif cat == "burden":
            burdens.append(cand)
        else:
            peers.append(cand)

    # lag 우선순위 + 점수 정렬
    def _sort_key(c: ChainCandidate) -> float:
        lag_pts = _lag_score(c.expected_lag)
        return c.chain_score + lag_pts * 2

    beneficiaries.sort(key=_sort_key, reverse=True)
    burdens.sort(key=_sort_key, reverse=True)
    peers.sort(key=_sort_key, reverse=True)

    return (
        beneficiaries[:max_per_type],
        burdens[:max_per_type],
        peers[:max_per_type],
    )
