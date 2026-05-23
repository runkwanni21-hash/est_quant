"""Institutional Report Builder — 기관식 스윙 리포트 오케스트레이터.

build_institutional_report()가 메인 진입점.
각 서브 엔진 실패 시 graceful fallback — 전체 리포트 죽지 않음.
공개 정보 기반 리서치 보조. 투자 판단 책임은 사용자에게 있음.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from tele_quant.analysis.report_models import (
        InstitutionalInvestmentReport,
        ReportEvidence,
        SwingReportScore,
    )
    from tele_quant.db import Store
    from tele_quant.settings import Settings

log = logging.getLogger(__name__)

_DISCLAIMER = "⚠ 공개 정보 기반 리서치 보조 — 투자 판단 책임은 사용자에게 있음"


# ── 증거 수집 ─────────────────────────────────────────────────────────────────


def collect_report_evidence(
    symbol: str,
    market: str,
    store: Store | None,
    deep: bool = False,
) -> list[ReportEvidence]:  # type: ignore[name-defined]
    """뉴스/공시/리포트 증거 수집. 실패 시 빈 목록 반환."""
    from tele_quant.analysis.report_models import ReportEvidence
    from tele_quant.relation_feed import _NAME_MAP

    items: list[ReportEvidence] = []
    name = _NAME_MAP.get(symbol, symbol)
    bare = symbol.split(".")[0]

    # 1. DB recent_issues 조회
    if store is not None:
        try:
            from datetime import timedelta

            from tele_quant.models import utc_now

            since = utc_now() - timedelta(days=30)
            raw = store.search_raw_items([bare, name], since=since, limit=20)
            for r in raw:
                text = (r.get("title") or r.get("text") or "")[:120]
                if not text.strip():
                    continue
                published = r.get("published_at", "")
                src_type = r.get("source_type", "")
                confidence = "HIGH" if src_type in ("dart", "sec", "ecos") else "MEDIUM"
                items.append(ReportEvidence(
                    title=text,
                    source=src_type or "db",
                    published_at=published,
                    confidence=confidence,
                ))
        except Exception as exc:
            log.debug("[report_builder] db evidence failed: %s", exc)

    # 2. recent_issue_collector (공시/뉴스)
    try:
        from tele_quant.recent_issue_collector import collect_recent_issues

        issues = collect_recent_issues(symbol, market, store=store, max_items=10)
        for iss in issues:
            if isinstance(iss, str):
                items.append(ReportEvidence(
                    title=iss[:120], source="recent_issues", confidence="MEDIUM",
                ))
    except Exception as exc:
        log.debug("[report_builder] recent_issues failed: %s", exc)

    # 3. DART 공시 (KR, deep mode)
    if deep and market == "KR":
        try:
            from tele_quant.opendart_client import fetch_dart_disclosures

            disclosures = fetch_dart_disclosures(bare, days=30)
            for d in disclosures[:5]:
                items.append(ReportEvidence(
                    title=d.get("report_nm", "")[:120],
                    source="DART",
                    published_at=d.get("rcept_dt", ""),
                    confidence="HIGH",
                    url=d.get("url", ""),
                ))
        except Exception as exc:
            log.debug("[report_builder] dart failed: %s", exc)

    # 4. SEC 8-K (US, deep mode)
    if deep and market == "US":
        try:
            from tele_quant.sec_client import fetch_recent_8k

            filings = fetch_recent_8k(symbol, days=30)
            for f in filings[:5]:
                items.append(ReportEvidence(
                    title=f.get("title", "")[:120],
                    source="SEC",
                    published_at=f.get("filed", ""),
                    confidence="HIGH",
                ))
        except Exception as exc:
            log.debug("[report_builder] sec failed: %s", exc)

    # freshness 계산
    now = datetime.now(UTC)
    for ev in items:
        if ev.published_at:
            try:
                from tele_quant.models import parse_dt

                dt = parse_dt(ev.published_at)
                if dt:
                    ev.freshness_days = (now - dt).total_seconds() / 86400
            except Exception:
                pass

    # 중복 제거 (제목 기준)
    seen: set[str] = set()
    deduped: list[ReportEvidence] = []
    for ev in items:
        key = ev.title[:50]
        if key not in seen:
            seen.add(key)
            deduped.append(ev)

    return deduped[:15]


# ── 관찰 기준 생성 ────────────────────────────────────────────────────────────


def _build_entry_exit(
    symbol: str,
    sector_id: str,
    technical: Any,
    flow: Any,
    consensus: Any,
) -> tuple[list[str], list[str], str, list[str]]:
    """관찰 기준(entry), 리스크 기준(exit), 기대 보상 구간, 확인 날짜."""
    entry: list[str] = []
    exit_: list[str] = []
    dates: list[str] = []

    # entry 조건
    if technical.above_ma20 is False:
        entry.append("MA20 회복 후 재진입 확인")
    elif technical.above_ma20 is True and technical.obv_trend == "UP":
        entry.append("OBV 상승 유지 + MA20 지지 확인")

    if technical.rsi_1d is not None:
        if technical.rsi_1d < 45:
            entry.append(f"RSI {technical.rsi_1d:.0f} → 50 회복 시 강도 확인")
        elif 45 <= technical.rsi_1d <= 65:
            entry.append(f"RSI {technical.rsi_1d:.0f} 적정 구간 유지 여부")

    if flow.flow_level == "HIGH":
        entry.append("수급집중 가능성 HIGH 유지 여부 재확인")

    if not entry:
        entry.append("MA20 지지 + 거래량 회복 확인")

    # exit 조건
    exit_.append("MA60 하향 이탈 시 관찰 중단")
    if technical.rsi_1d is not None and technical.rsi_1d > 65:
        exit_.append(f"RSI {technical.rsi_1d:.0f} 이상 유지 시 과열 추격주의")
    exit_.append("공시/뉴스 부재 3거래일 이상 지속 시 재검토")

    # 기대 보상 구간 (DCF/컨센서스 기반 — 확정 아님)
    reward_range = "확인 제한"
    if consensus.target_mean and consensus.current_price and consensus.current_price > 0:
        upside = (consensus.target_mean - consensus.current_price) / consensus.current_price * 100
        if upside > 0:
            reward_range = f"컨센서스 목표가 기준 +{upside:.0f}% 상승여력 추정 (확정 아님)"
        else:
            reward_range = f"컨센서스 기준 하방 리스크 {upside:.0f}% 존재"

    return entry, exit_, reward_range, dates


# ── 모순·누락 감지 ────────────────────────────────────────────────────────────


def detect_contradictions(
    technical: Any,
    flow: Any,
    evidence: list[Any],
) -> list[str]:
    """기술/수급/증거 간 모순 감지."""
    contradictions: list[str] = []
    if technical.overheat and flow.flow_level == "HIGH":
        contradictions.append("과열 신호 + 수급집중 HIGH 동시 — 추격 진입 주의")
    if technical.obv_trend == "DOWN" and flow.price_obv_divergence:
        contradictions.append("OBV 하향 + divergence 신호 혼재 — 신뢰도 낮음")
    neg_ev = [e for e in evidence if getattr(e, "confidence", "") == "HIGH" and "부정" in getattr(e, "title", "")]
    if neg_ev and technical.above_ma20 is True:
        contradictions.append("MA20 위이지만 고신뢰 부정 뉴스 존재")
    return contradictions


def detect_missing_data(
    technical: Any,
    flow: Any,
    consensus: Any,
) -> list[str]:
    """누락 데이터 목록."""
    missing: list[str] = []
    if technical.rsi_1d is None:
        missing.append("RSI 데이터 확인 제한")
    if flow.inst_net_5d is None and flow.data_source == "proxy":
        missing.append("KRX 기관/외국인 데이터 직접 확인 필요")
    if consensus.target_mean is None:
        missing.append("애널리스트 목표가 확인 제한")
    if technical.obv_trend == "FLAT" and technical.vol_ratio_20d is None:
        missing.append("거래량 데이터 부족")
    return missing


# ── 점수화 ────────────────────────────────────────────────────────────────────


def score_swing_report(
    evidence: list[Any],
    sector_sa: Any,
    technical: Any,
    flow: Any,
    chain_beneficiaries: list[Any],
    contradictions: list[str],
    missing: list[str],
) -> SwingReportScore:  # type: ignore[name-defined]
    """SwingReportScore 계산."""
    from tele_quant.analysis.report_models import SwingReportScore

    sc = SwingReportScore()

    # 1. Evidence/News/Catalyst quality (0~15)
    high_ev = sum(1 for e in evidence if getattr(e, "confidence", "") == "HIGH")
    fresh_ev = sum(1 for e in evidence if (e.freshness_days or 99) < 7)
    sc.evidence_quality = min(15.0, 3.0 + high_ev * 3.0 + fresh_ev * 1.5)

    # 2. Sector valuation fit (0~15)
    sc.sector_valuation_fit = min(15.0, sector_sa.sector_valuation_score * 0.15)

    # 3. Technical setup (0~20)
    sc.technical_setup = min(20.0, technical.score * 0.20)

    # 4. Institutional flow (0~15)
    sc.institutional_flow = min(15.0, flow.flow_score * 0.15)

    # 5. Chain read-through (0~15)
    high_chain = sum(1 for c in chain_beneficiaries if c.chain_score >= 60)
    sc.chain_read_through = min(15.0, 3.0 + high_chain * 4.0)

    # 6. Timing/risk-reward (0~10)
    if technical.w52_position_pct is not None:
        pos = technical.w52_position_pct
        if 30 <= pos <= 70:
            sc.timing_risk_reward = 8.0
        elif pos < 30:
            sc.timing_risk_reward = 6.0
        else:
            sc.timing_risk_reward = 4.0
    else:
        sc.timing_risk_reward = 5.0

    # 7. Risk/contradiction penalty (최대 -10)
    penalty = len(contradictions) * 3.0 + len(missing) * 1.0
    sc.risk_penalty = min(10.0, penalty)
    if technical.overheat:
        sc.risk_penalty = min(10.0, sc.risk_penalty + 5.0)

    sc.contradictions = contradictions
    sc.missing_data = missing

    total = (
        sc.evidence_quality
        + sc.sector_valuation_fit
        + sc.technical_setup
        + sc.institutional_flow
        + sc.chain_read_through
        + sc.timing_risk_reward
        - sc.risk_penalty
    )
    sc.total = min(max(total, 0.0), 100.0)

    if sc.total >= 80:
        sc.grade = "우선관찰 A"
        sc.grade_en = "A"
    elif sc.total >= 68:
        sc.grade = "관찰 B"
        sc.grade_en = "B"
    elif sc.total >= 55:
        sc.grade = "조건부 관찰 C"
        sc.grade_en = "C"
    else:
        sc.grade = "보류"
        sc.grade_en = "D"

    return sc


# ── 한 줄 결론 생성 ──────────────────────────────────────────────────────────


def _one_line_conclusion(
    symbol: str,
    name: str,
    grade: str,
    technical: Any,
    flow: Any,
    evidence: list[Any],
) -> str:
    parts: list[str] = []
    if technical.obv_divergence:
        parts.append("OBV 매집 proxy 감지")
    if flow.flow_level == "HIGH":
        parts.append("수급집중 가능성 HIGH")
    if technical.overheat:
        parts.append("과열 추격주의")
    if evidence:
        parts.append(f"최근 이슈 {len(evidence)}건")
    if not parts:
        parts.append("공개 데이터 기준 중립")
    return f"{name}({symbol}) — {grade}: {', '.join(parts)}"


# ── 리스크 요인 ───────────────────────────────────────────────────────────────


def _build_risk_factors(
    technical: Any,
    flow: Any,
    sector_id: str,
    contradictions: list[str],
) -> list[str]:
    risks: list[str] = []
    if technical.overheat:
        risks.append("단기 과열 상태 — 추격 진입 시 되돌림 가능성")
    if technical.above_ma60 is False:
        risks.append("MA60 하단 위치 — 중기 추세 약화")
    if flow.flow_level == "LOW":
        risks.append("수급집중 가능성 LOW — 이탈 리스크 상존")
    if contradictions:
        risks.extend(contradictions[:2])
    risks.append("이 리포트는 공개 정보 기반이며 미공개 내부 정보 없음")
    risks.append("모든 지표는 후행 신호 — 실제 시장 반응과 다를 수 있음")
    return risks[:5]


# ── 메인 엔진 ─────────────────────────────────────────────────────────────────


def build_institutional_report(
    symbol: str,
    market: str,
    store: Store | None,
    settings: Settings | None = None,
    deep: bool = False,
) -> InstitutionalInvestmentReport:  # type: ignore[name-defined]
    """기관식 스윙 리포트 빌드.

    실패해도 error 필드에 기록 후 부분 결과 반환.
    """
    from tele_quant.analysis.analyst_consensus import build_analyst_consensus
    from tele_quant.analysis.chain_recommendation_engine import build_chain_candidates
    from tele_quant.analysis.institutional_flow import compute_institutional_flow
    from tele_quant.analysis.report_models import InstitutionalInvestmentReport
    from tele_quant.analysis.sector_specific import build_sector_specific_analysis, detect_sector_id
    from tele_quant.analysis.technical_signal_engine import compute_technical_accumulation_signal
    from tele_quant.relation_feed import _NAME_MAP

    report = InstitutionalInvestmentReport(symbol=symbol, market=market)
    report.name = _NAME_MAP.get(symbol, symbol)
    report.deep_mode = deep
    report.generated_at = datetime.now(UTC).isoformat()

    errors: list[str] = []

    # 1. 증거 수집
    try:
        report.evidence_items = collect_report_evidence(symbol, market, store, deep)
    except Exception as exc:
        errors.append(f"evidence: {exc}")
        log.warning("[report_builder] evidence failed %s: %s", symbol, exc)

    # 2. 기술 분석
    try:
        report.technical_signal = compute_technical_accumulation_signal(symbol)
    except Exception as exc:
        errors.append(f"technical: {exc}")
        log.warning("[report_builder] technical failed %s: %s", symbol, exc)

    # 3. 기관/외국인 수급
    try:
        report.flow_signal = compute_institutional_flow(
            symbol,
            rsi=report.technical_signal.rsi_1d,
            ret_20d=report.technical_signal.ret_20d,
            vol_ratio=report.technical_signal.vol_ratio_20d,
            bb_pct=report.technical_signal.bb_pct,
        )
    except Exception as exc:
        errors.append(f"flow: {exc}")
        log.warning("[report_builder] flow failed %s: %s", symbol, exc)

    # 4. 애널리스트 컨센서스
    try:
        report.consensus = build_analyst_consensus(symbol, store)
    except Exception as exc:
        errors.append(f"consensus: {exc}")
        log.warning("[report_builder] consensus failed %s: %s", symbol, exc)

    # 5. 섹터별 분석
    sector_id = detect_sector_id(symbol, store)
    try:
        report.sector_analysis = build_sector_specific_analysis(symbol, sector_id)
    except Exception as exc:
        errors.append(f"sector: {exc}")
        log.warning("[report_builder] sector failed %s: %s", symbol, exc)

    # 6. 체인 후보
    source_polarity = "POSITIVE"
    try:
        bens, burdens, peers = build_chain_candidates(
            symbol=symbol,
            market=market,
            store=store,
            evidence_items=report.evidence_items,
            source_return=report.technical_signal.ret_1d,
            source_polarity=source_polarity,
            source_confidence="MEDIUM",
            sector_id=sector_id,
        )
        report.chain_beneficiaries = bens
        report.chain_burdens = burdens
        report.chain_peers = peers
    except Exception as exc:
        errors.append(f"chain: {exc}")
        log.warning("[report_builder] chain failed %s: %s", symbol, exc)

    # 7. 모순/누락 감지
    contradictions = detect_contradictions(report.technical_signal, report.flow_signal, report.evidence_items)
    missing = detect_missing_data(report.technical_signal, report.flow_signal, report.consensus)

    # 8. 점수화
    try:
        report.score = score_swing_report(
            report.evidence_items,
            report.sector_analysis,
            report.technical_signal,
            report.flow_signal,
            report.chain_beneficiaries,
            contradictions,
            missing,
        )
    except Exception as exc:
        errors.append(f"scoring: {exc}")
        log.warning("[report_builder] scoring failed %s: %s", symbol, exc)

    # 9. 리스크
    report.risk_factors = _build_risk_factors(
        report.technical_signal, report.flow_signal, sector_id, contradictions
    )
    report.missing_checks = missing

    # 10. 관찰 기준
    try:
        entry, exit_, reward, dates = _build_entry_exit(
            symbol, sector_id,
            report.technical_signal, report.flow_signal, report.consensus,
        )
        report.entry_conditions = entry
        report.exit_conditions = exit_
        report.reward_range = reward
        report.key_dates = dates
    except Exception as exc:
        errors.append(f"entry_exit: {exc}")

    # 11. 한 줄 결론
    report.one_line_conclusion = _one_line_conclusion(
        symbol, report.name, report.score.grade,
        report.technical_signal, report.flow_signal, report.evidence_items,
    )

    if errors:
        report.error = "; ".join(errors[:3])

    return report


def build_report_pack(
    symbol: str,
    market: str,
    store: Store | None,
    settings: Settings | None = None,
) -> InstitutionalInvestmentReport:  # type: ignore[name-defined]
    """build_institutional_report alias (외부 호출용)."""
    return build_institutional_report(symbol, market, store, settings, deep=False)
