"""Sector Intelligence — 섹터별 심층 분석 엔진.

sector_playbooks.yml을 로드해 섹터마다 다른 분석 관점과 특화 모듈
(clinical_pipeline, order_backlog 등)을 호출한다.

공개 정보 기반 리서치 보조. 투자 판단 책임은 사용자에게 있음.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from tele_quant.db import Store

log = logging.getLogger(__name__)

__all__ = [
    "SectorIntelligence",
    "build_sector_intelligence",
    "format_sector_intelligence",
    "load_playbook",
]

_PLAYBOOK_PATH = Path(__file__).parent.parent.parent / "config" / "sector_playbooks.yml"
_playbook_cache: dict[str, Any] | None = None


def load_playbook(sector_id: str) -> dict[str, Any] | None:
    """sector_playbooks.yml에서 sector_id에 해당하는 플레이북 로드."""
    global _playbook_cache
    if _playbook_cache is None:
        try:
            import yaml

            with open(_PLAYBOOK_PATH, encoding="utf-8") as f:
                _playbook_cache = yaml.safe_load(f) or {}
        except Exception as exc:
            log.debug("[sector_intel] playbook 로드 실패: %s", exc)
            _playbook_cache = {}
    return _playbook_cache.get(sector_id)


@dataclass
class SectorIntelligence:
    """섹터별 심층 분석 결과."""

    sector_id: str
    title: str = ""
    summary_lines: list[str] = field(default_factory=list)
    key_metrics: list[str] = field(default_factory=list)
    catalysts: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    next_milestones: list[str] = field(default_factory=list)
    related_companies: list[str] = field(default_factory=list)
    swing_checkpoints: list[str] = field(default_factory=list)
    exit_checkpoints: list[str] = field(default_factory=list)
    valuation_note: str = ""
    special_section: str = ""     # 바이오 임상/조선 수주잔고 등 특화 텍스트
    confidence: str = "LOW"
    data_limitations: list[str] = field(default_factory=list)
    policy_note: str = ""         # 월요일/금요일 정책 노트


def _build_from_playbook(
    playbook: dict[str, Any],
    sector_id: str,
    price_snapshot: dict,
    fundamental_snapshot: dict,
    recent_issues: list[str],
) -> SectorIntelligence:
    """플레이북 데이터 기반으로 기본 SectorIntelligence를 생성."""
    intel = SectorIntelligence(sector_id=sector_id)
    intel.title = playbook.get("display_name", sector_id)
    intel.key_metrics = (playbook.get("key_metrics") or [])[:4]
    intel.catalysts = (playbook.get("catalysts") or [])[:3]
    intel.risks = (playbook.get("risks") or [])[:3]
    intel.swing_checkpoints = (playbook.get("swing_checkpoints") or [])[:3]
    intel.exit_checkpoints = (playbook.get("exit_checkpoints") or [])[:2]
    intel.valuation_note = playbook.get("valuation_note") or ""

    # ── 가격/펀더멘탈 요약 라인 ───────────────────────────────────────────────
    summary: list[str] = []
    price_1w = price_snapshot.get("1w")
    price_1m = price_snapshot.get("1m")
    if price_1w is not None:
        summary.append(f"1주 변동: {price_1w:+.1f}%")
    if price_1m is not None:
        summary.append(f"1개월: {price_1m:+.1f}%")
    pe_f = fundamental_snapshot.get("pe_forward")
    roe = fundamental_snapshot.get("roe")
    if pe_f is not None:
        summary.append(f"PER(F): {pe_f:.1f}배")
    if roe is not None:
        summary.append(f"ROE: {roe:.1f}%")
    if recent_issues:
        summary.append(f"최근 이슈: {recent_issues[0][:60]}")
    intel.summary_lines = summary[:5]
    intel.confidence = "MEDIUM" if (price_1w is not None or pe_f is not None) else "LOW"
    return intel


def _append_special_section(
    intel: SectorIntelligence,
    playbook: dict[str, Any],
    symbol: str,
    name: str,
    market: str,
    store: Store | None,
    deep: bool,
) -> None:
    """섹터별 특화 모듈(임상/수주잔고 등) 호출."""
    special = playbook.get("special_module") or ""

    if special == "clinical_pipeline":
        try:
            from tele_quant.clinical_pipeline import (
                fetch_clinical_pipeline,
                format_clinical_pipeline,
            )
            result = fetch_clinical_pipeline(symbol, name, market, store, deep=deep)
            intel.special_section = format_clinical_pipeline(result)
        except Exception as exc:
            log.debug("[sector_intel] clinical_pipeline 실패 %s: %s", symbol, exc)
            intel.special_section = "🧬 바이오/임상 체크: 조회 실패 — 공개자료 기준 확인 권장"
            intel.data_limitations.append("임상 파이프라인 데이터 조회 실패")

    elif special == "order_backlog":
        try:
            from tele_quant.order_backlog import format_backlog_summary, get_backlog_for_symbol
            backlog = get_backlog_for_symbol(symbol, store=store)
            if backlog:
                intel.special_section = format_backlog_summary(backlog, sector_id=intel.sector_id)
            else:
                intel.special_section = _default_backlog_note(intel.sector_id)
        except Exception as exc:
            log.debug("[sector_intel] order_backlog 실패 %s: %s", symbol, exc)
            intel.special_section = _default_backlog_note(intel.sector_id)


def _default_backlog_note(sector_id: str) -> str:
    """수주잔고 데이터가 없을 때 섹터별 기본 메시지."""
    if "shipbuilding" in sector_id:
        return (
            "🚢 조선/수주잔고 체크:\n"
            "  • 수주잔고: 공개자료 기준 확인 필요 (DART 공시/Clarkson 참조)\n"
            "  • 최근 수주: 공시 미확인\n"
            "  • 원가 리스크: 후판 가격, 달러/원 환율, 인건비\n"
            "  • 체크포인트: Clarkson 선가 + 신규 수주 공시"
        )
    if "defense" in sector_id:
        return (
            "🛡 방산/수주잔고 체크:\n"
            "  • 수주잔고: 공개자료 기준 확인 필요\n"
            "  • 수출 허가: 공시 미확인\n"
            "  • 리스크: 납품 지연, 국방예산 변동"
        )
    if "construction" in sector_id:
        return (
            "🏗 건설/수주잔고 체크:\n"
            "  • 수주잔고: 공개자료 기준 확인 필요\n"
            "  • PF/미분양 리스크: DART 공시 확인 권장"
        )
    return (
        "📋 수주잔고 체크:\n"
        "  • 수주잔고: 공개자료 기준 확인 필요"
    )


_SAAS_ID = "ai_software_cloud_cybersecurity"
_R40_STRONG = 40  # Rule of 40 충족 기준
_R40_WARN = 30    # Rule of 40 경계 기준


def _compute_saas_intel(
    intel: SectorIntelligence,
    fundamental_snapshot: dict[str, Any],
) -> None:
    """SaaS 전용 Rule of 40 계산 — special_section에 기록."""
    rev_g = fundamental_snapshot.get("revenue_growth")
    op_m = fundamental_snapshot.get("op_margin")

    lines: list[str] = ["☁ SaaS 밸류에이션 체크:"]

    if rev_g is not None and op_m is not None:
        r40 = rev_g + op_m
        if r40 >= _R40_STRONG:
            status = "충족 ✅"
            verdict = "고PER 멀티플 유지 근거 확인됨 (관찰 기준)"
        elif r40 >= _R40_WARN:
            status = "경계 ⚠"
            verdict = "Rule of 40 경계구간 — 성장 지속 여부 모니터링"
        else:
            status = "미충족 ⚠"
            verdict = "Rule of 40 미달 — 성장률 회복 또는 멀티플 압박 가능"
        lines.append(
            f"  Rule of 40 {status}: "
            f"매출성장 {rev_g:.1f}% + 영업이익률 {op_m:.1f}% = {r40:.1f}"
        )
        lines.append(f"  → {verdict}")
    elif rev_g is not None:
        lines.append(f"  매출성장: {rev_g:.1f}% (영업이익률 데이터 없음 — Rule of 40 계산 불가)")
    else:
        lines.append("  Rule of 40: yfinance 기준 계산 불가")

    lines.append("  ※ ARR·NRR은 공개 API 미제공 — 실적 공시(IR) 확인 권장")
    intel.special_section = "\n".join(lines)


# ── 섹터별 특화 분석 헬퍼 ────────────────────────────────────────────────────


def _per_tier(pe: float, lo: float, hi: float) -> str:
    if pe < lo:
        return f"저평가 (< {lo:.0f}배)"
    if pe <= hi:
        return f"적정 ({lo:.0f}~{hi:.0f}배)"
    return f"고밸류 경계 (> {hi:.0f}배)"


def _growth_tier(g: float) -> str:
    if g >= 30:
        return "고성장"
    if g >= 15:
        return "성장"
    if g >= 5:
        return "안정성장"
    if g >= 0:
        return "보합"
    return "역성장 ⚠"


def _margin_ok(m: float, threshold: float) -> str:
    return "건전 ✅" if m >= threshold else "주의 ⚠"


# ── 반도체 HBM/파운드리 ──────────────────────────────────────────────────────

def _compute_semiconductor_intel(
    intel: SectorIntelligence,
    fs: dict[str, Any],
) -> None:
    lines = ["💡 반도체 사이클 체크:"]
    pe = fs.get("pe_forward")
    rev_g = fs.get("revenue_growth")
    eps_g = fs.get("eps_growth")
    if pe is not None:
        lines.append(f"  PER(F): {pe:.1f}배 — {_per_tier(pe, 15, 35)} (반도체 표준)")
    if rev_g is not None and eps_g is not None:
        gap = eps_g - rev_g
        if gap >= 15:
            lines.append(
                f"  EPS성장 {eps_g:+.1f}% vs 매출성장 {rev_g:+.1f}% → "
                f"+{gap:.0f}%p 마진 확장 구간"
            )
        elif gap <= -10:
            lines.append(
                f"  EPS성장 {eps_g:+.1f}% vs 매출성장 {rev_g:+.1f}% → "
                f"마진 압박 {gap:.0f}%p ⚠"
            )
        else:
            lines.append(
                f"  매출성장 {rev_g:+.1f}% / EPS성장 {eps_g:+.1f}% — 일관된 성장"
            )
    elif rev_g is not None:
        lines.append(f"  매출성장: {rev_g:+.1f}% ({_growth_tier(rev_g)})")
    lines.append("  ※ HBM ASP·AI CAPEX·파운드리 가동률은 실적 공시 확인 필요")
    intel.special_section = "\n".join(lines)


# ── 반도체 장비/소재/OSAT ────────────────────────────────────────────────────

def _compute_semicap_intel(
    intel: SectorIntelligence,
    fs: dict[str, Any],
) -> None:
    lines = ["🔧 장비/소재/OSAT 체크:"]
    pe = fs.get("pe_forward")
    rev_g = fs.get("revenue_growth")
    op_m = fs.get("op_margin")
    if pe is not None:
        lines.append(f"  PER(F): {pe:.1f}배 — {_per_tier(pe, 20, 35)} (장비 표준)")
    if rev_g is not None:
        lines.append(f"  매출성장: {rev_g:+.1f}% ({_growth_tier(rev_g)})")
    if op_m is not None:
        lines.append(f"  영업이익률: {op_m:.1f}% — {_margin_ok(op_m, 20)} (장비 20%+ 기준)")
    lines.append("  ※ 수주잔고·book-to-bill·고객사 CAPEX는 실적 공시 확인 필요")
    intel.special_section = "\n".join(lines)


# ── AI 전력그리드/구리/원전 ─────────────────────────────────────────────────

def _compute_ai_power_intel(
    intel: SectorIntelligence,
    fs: dict[str, Any],
) -> None:
    lines = ["⚡ AI 전력/인프라 체크:"]
    pe = fs.get("pe_forward")
    rev_g = fs.get("revenue_growth")
    op_m = fs.get("op_margin")
    if pe is not None:
        lines.append(f"  PER(F): {pe:.1f}배 — {_per_tier(pe, 18, 35)} (AI 인프라 성장 프리미엄)")
    if rev_g is not None:
        lines.append(f"  매출성장: {rev_g:+.1f}% ({_growth_tier(rev_g)})")
    if op_m is not None:
        lines.append(f"  영업이익률: {op_m:.1f}% — {_margin_ok(op_m, 15)}")
    lines.append("  ※ 전력 계약용량·구리 가격·원전 허가는 실적/공시 확인 필요")
    intel.special_section = "\n".join(lines)


# ── EV/배터리/자율주행 ──────────────────────────────────────────────────────

def _compute_ev_intel(
    intel: SectorIntelligence,
    fs: dict[str, Any],
) -> None:
    lines = ["🔋 EV/배터리 성장 체크:"]
    rev_g = fs.get("revenue_growth")
    op_m = fs.get("op_margin")
    pe = fs.get("pe_forward")
    if rev_g is not None:
        tier = _growth_tier(rev_g)
        lines.append(f"  매출성장: {rev_g:+.1f}% — {tier} (EV 침투 단계 반영)")
    if op_m is not None:
        if op_m >= 10:
            verdict = "성숙 단계 마진 확보"
        elif op_m >= 0:
            verdict = "흑자 전환 — 배터리 단가 하락 효과 반영 중"
        else:
            verdict = "적자 ⚠ — 스케일업 단계 or 구조적 문제 확인 필요"
        lines.append(f"  영업이익률: {op_m:.1f}% — {verdict}")
    if pe is not None:
        lines.append(f"  PER(F): {pe:.1f}배 — {_per_tier(pe, 20, 60)} (EV 성장 프리미엄)")
    lines.append("  ※ EV 침투율·배터리 단가·ASP는 공시 기준 확인 필요")
    intel.special_section = "\n".join(lines)


# ── 배터리소재/리튬 ─────────────────────────────────────────────────────────

def _compute_battery_materials_intel(
    intel: SectorIntelligence,
    fs: dict[str, Any],
) -> None:
    lines = ["🔋 배터리소재 사이클 체크:"]
    rev_g = fs.get("revenue_growth")
    op_m = fs.get("op_margin")
    pe = fs.get("pe_forward")
    if rev_g is not None:
        if rev_g < 0:
            lines.append(f"  매출성장: {rev_g:+.1f}% — 리튬/코발트 가격 하락 사이클 반영 가능")
        else:
            lines.append(f"  매출성장: {rev_g:+.1f}% ({_growth_tier(rev_g)})")
    if op_m is not None:
        lines.append(f"  영업이익률: {op_m:.1f}% — {_margin_ok(op_m, 10)} (소재 10%+ 기준)")
    if pe is not None:
        lines.append(f"  PER(F): {pe:.1f}배 — {_per_tier(pe, 8, 20)} (소재 사이클 표준)")
    lines.append("  ※ 리튬·코발트 스팟가격은 실시간 데이터 별도 확인 필요")
    intel.special_section = "\n".join(lines)


# ── 금융/은행/보험/증권 ─────────────────────────────────────────────────────

def _compute_financial_intel(
    intel: SectorIntelligence,
    fs: dict[str, Any],
) -> None:
    lines = ["💰 금융 밸류에이션 체크:"]
    pb = fs.get("pb")
    roe = fs.get("roe")
    div = fs.get("dividend_yield")
    if pb is not None:
        if pb < 0.5:
            pb_note = "극단적 저평가 (구조적 문제 가능성 확인)"
        elif pb < 0.8:
            pb_note = "저평가 구간 (금리 하강 사이클 수혜 기대)"
        elif pb <= 1.2:
            pb_note = "적정 구간"
        elif pb <= 1.8:
            pb_note = "프리미엄 (ROE 우수 근거 확인 필요)"
        else:
            pb_note = "고밸류 경계 ⚠"
        lines.append(f"  PBR: {pb:.2f}배 — {pb_note}")
    if roe is not None:
        coe_ok = "자기자본비용 상회 ✅" if roe >= 8 else "자기자본비용 미충족 ⚠"
        lines.append(f"  ROE: {roe:.1f}% — {coe_ok} (8% 기준)")
    if div is not None and div > 0:
        div_note = "배당 매력 ✅" if div >= 3 else "배당 보조"
        lines.append(f"  배당수익률: {div:.1f}% — {div_note} (3%+ 기준)")
    lines.append("  ※ NIM·NPL·대손충당금은 실적 공시 확인 필요")
    intel.special_section = "\n".join(lines)


# ── 에너지/오일/LNG ──────────────────────────────────────────────────────────

def _compute_energy_intel(
    intel: SectorIntelligence,
    fs: dict[str, Any],
) -> None:
    lines = ["⚡ 에너지 밸류에이션 체크:"]
    pe = fs.get("pe_forward")
    op_m = fs.get("op_margin")
    div = fs.get("dividend_yield")
    if pe is not None:
        lines.append(f"  PER(F): {pe:.1f}배 — {_per_tier(pe, 8, 15)} (에너지 표준)")
    if op_m is not None:
        if op_m >= 25:
            tier = "통합 메이저 수준"
        elif op_m >= 15:
            tier = "E&P 건전 마진"
        elif op_m >= 0:
            tier = "수익성 확보"
        else:
            tier = "적자 ⚠"
        lines.append(f"  영업이익률: {op_m:.1f}% — {tier}")
    if div is not None and div > 0:
        lines.append(f"  배당수익률: {div:.1f}%")
    lines.append("  ※ 유가·LNG 스팟가격·정제마진은 실시간 데이터 별도 확인 필요")
    intel.special_section = "\n".join(lines)


# ── 소재/화학/철강/희토류 ────────────────────────────────────────────────────

def _compute_materials_intel(
    intel: SectorIntelligence,
    fs: dict[str, Any],
) -> None:
    lines = ["🏗 소재/화학/철강 체크:"]
    pe = fs.get("pe_forward")
    op_m = fs.get("op_margin")
    rev_g = fs.get("revenue_growth")
    if pe is not None:
        lines.append(f"  PER(F): {pe:.1f}배 — {_per_tier(pe, 8, 18)} (소재 표준)")
    if op_m is not None:
        lines.append(f"  영업이익률: {op_m:.1f}% — {_margin_ok(op_m, 10)} (소재 10%+ 기준)")
    if rev_g is not None:
        lines.append(f"  매출성장: {rev_g:+.1f}% ({_growth_tier(rev_g)})")
    lines.append("  ※ 원자재 가격·스프레드·관세 리스크는 실시간 데이터 별도 확인 필요")
    intel.special_section = "\n".join(lines)


# ── K뷰티/화장품/ODM ─────────────────────────────────────────────────────────

def _compute_kbeauty_intel(
    intel: SectorIntelligence,
    fs: dict[str, Any],
) -> None:
    lines = ["💄 K뷰티 수익성 체크:"]
    rev_g = fs.get("revenue_growth")
    op_m = fs.get("op_margin")
    pe = fs.get("pe_forward")
    if rev_g is not None:
        lines.append(f"  매출성장: {rev_g:+.1f}% — {_growth_tier(rev_g)} (수출채널 확인)")
    if op_m is not None:
        if op_m >= 15:
            tier = "브랜드 프리미엄 ✅"
        elif op_m >= 10:
            tier = "ODM 건전 마진"
        else:
            tier = "ODM 마진 압박 ⚠"
        lines.append(f"  영업이익률: {op_m:.1f}% — {tier}")
    if pe is not None:
        lines.append(f"  PER(F): {pe:.1f}배 — {_per_tier(pe, 12, 30)}")
    lines.append("  ※ 채널별 매출 비중(중국·US·유럽)은 공시 기준 확인 필요")
    intel.special_section = "\n".join(lines)


# ── 리테일/이커머스/여행/항공 ────────────────────────────────────────────────

def _compute_retail_intel(
    intel: SectorIntelligence,
    fs: dict[str, Any],
) -> None:
    lines = ["🛒 리테일/이커머스 체크:"]
    rev_g = fs.get("revenue_growth")
    op_m = fs.get("op_margin")
    pe = fs.get("pe_forward")
    if rev_g is not None:
        lines.append(f"  매출성장: {rev_g:+.1f}% ({_growth_tier(rev_g)})")
    if op_m is not None:
        if op_m >= 15:
            tier = "고마진 (플랫폼/광고 믹스 효과)"
        elif op_m >= 3:
            tier = "리테일 표준 마진"
        else:
            tier = "저마진 ⚠ (물류비·가격경쟁 확인)"
        lines.append(f"  영업이익률: {op_m:.1f}% — {tier}")
    if pe is not None:
        lines.append(f"  PER(F): {pe:.1f}배 — {_per_tier(pe, 12, 30)}")
    lines.append("  ※ GMV·하중률(항공)·RevPAR(호텔)은 공시 기준 확인 필요")
    intel.special_section = "\n".join(lines)


# ── 미디어/콘텐츠/게임 ──────────────────────────────────────────────────────

def _compute_media_intel(
    intel: SectorIntelligence,
    fs: dict[str, Any],
) -> None:
    lines = ["🎮 미디어/게임/광고 체크:"]
    rev_g = fs.get("revenue_growth")
    op_m = fs.get("op_margin")
    pe = fs.get("pe_forward")
    if rev_g is not None:
        lines.append(f"  매출성장: {rev_g:+.1f}% ({_growth_tier(rev_g)})")
    if op_m is not None:
        if op_m >= 20:
            tier = "플랫폼 고마진 ✅"
        elif op_m >= 10:
            tier = "콘텐츠 표준 마진"
        else:
            tier = "콘텐츠 투자 단계 ⚠"
        lines.append(f"  영업이익률: {op_m:.1f}% — {tier}")
    if pe is not None:
        lines.append(f"  PER(F): {pe:.1f}배 — {_per_tier(pe, 12, 35)}")
    lines.append("  ※ DAU/MAU·ARPU·광고단가는 공시 기준 확인 필요")
    intel.special_section = "\n".join(lines)


# ── 통신/5G/스마트폰 ─────────────────────────────────────────────────────────

def _compute_telecom_intel(
    intel: SectorIntelligence,
    fs: dict[str, Any],
) -> None:
    lines = ["📡 통신 밸류에이션 체크:"]
    div = fs.get("dividend_yield")
    pe = fs.get("pe_forward")
    op_m = fs.get("op_margin")
    if div is not None and div > 0:
        div_note = "배당 인컴 매력 ✅" if div >= 3 else "배당 보조"
        lines.append(f"  배당수익률: {div:.1f}% — {div_note} (통신 3%+ 기준)")
    if pe is not None:
        lines.append(f"  PER(F): {pe:.1f}배 — {_per_tier(pe, 10, 18)} (통신 표준)")
    if op_m is not None:
        lines.append(f"  영업이익률: {op_m:.1f}% — {_margin_ok(op_m, 15)} (통신 15%+ 기준)")
    lines.append("  ※ ARPU·가입자 성장·5G 침투율은 공시 기준 확인 필요")
    intel.special_section = "\n".join(lines)


# ── 식품/농업/비료 ───────────────────────────────────────────────────────────

def _compute_food_intel(
    intel: SectorIntelligence,
    fs: dict[str, Any],
) -> None:
    lines = ["🌾 식품/농업/소비재 체크:"]
    op_m = fs.get("op_margin")
    rev_g = fs.get("revenue_growth")
    div = fs.get("dividend_yield")
    if op_m is not None:
        if op_m >= 12:
            tier = "브랜드 프리미엄 ✅"
        elif op_m >= 6:
            tier = "식품 표준 마진"
        else:
            tier = "원가 압박 ⚠"
        lines.append(f"  영업이익률: {op_m:.1f}% — {tier}")
    if rev_g is not None:
        lines.append(f"  매출성장: {rev_g:+.1f}% (방어주 — 경기 방어적 성격)")
    if div is not None and div > 0:
        lines.append(f"  배당수익률: {div:.1f}%")
    lines.append("  ※ 곡물 가격·비료 원가·공급망 리스크는 실시간 확인 필요")
    intel.special_section = "\n".join(lines)


# ── 헬스케어 서비스/병원/진단 ────────────────────────────────────────────────

def _compute_healthcare_intel(
    intel: SectorIntelligence,
    fs: dict[str, Any],
) -> None:
    lines = ["🏥 헬스케어 서비스 체크:"]
    op_m = fs.get("op_margin")
    rev_g = fs.get("revenue_growth")
    pe = fs.get("pe_forward")
    if op_m is not None:
        if op_m >= 15:
            tier = "고마진 헬스케어 서비스"
        elif op_m >= 8:
            tier = "표준 의료 마진"
        else:
            tier = "의료 마진 압박 ⚠"
        lines.append(f"  영업이익률: {op_m:.1f}% — {tier}")
    if rev_g is not None:
        lines.append(f"  매출성장: {rev_g:+.1f}% ({_growth_tier(rev_g)})")
    if pe is not None:
        lines.append(f"  PER(F): {pe:.1f}배 — {_per_tier(pe, 12, 25)}")
    lines.append("  ※ 병상 가동률·보험수가·급여 기준은 공시 기준 확인 필요")
    intel.special_section = "\n".join(lines)


# ── 환경/폐기물/탄소 인프라 ────────────────────────────────────────────────

def _compute_environment_intel(
    intel: SectorIntelligence,
    fs: dict[str, Any],
) -> None:
    lines = ["🌿 환경/탄소 인프라 체크:"]
    rev_g = fs.get("revenue_growth")
    op_m = fs.get("op_margin")
    pe = fs.get("pe_forward")
    if rev_g is not None:
        lines.append(f"  매출성장: {rev_g:+.1f}% ({_growth_tier(rev_g)}, 규제·탄소세 수혜 여부)")
    if op_m is not None:
        lines.append(f"  영업이익률: {op_m:.1f}% — {_margin_ok(op_m, 10)}")
    if pe is not None:
        lines.append(f"  PER(F): {pe:.1f}배 — {_per_tier(pe, 15, 30)}")
    lines.append("  ※ 탄소 크레딧 가격·환경 규제 변화는 공시 기준 확인 필요")
    intel.special_section = "\n".join(lines)


# ── 페이먼츠/핀테크/크립토 ──────────────────────────────────────────────────

def _compute_payments_intel(
    intel: SectorIntelligence,
    fs: dict[str, Any],
) -> None:
    lines = ["💳 페이먼츠/핀테크 체크:"]
    rev_g = fs.get("revenue_growth")
    op_m = fs.get("op_margin")
    pe = fs.get("pe_forward")
    if rev_g is not None:
        lines.append(f"  매출성장: {rev_g:+.1f}% ({_growth_tier(rev_g)})")
    if op_m is not None:
        if op_m >= 30:
            tier = "고마진 결제 플랫폼 ✅"
        elif op_m >= 15:
            tier = "핀테크 건전 마진"
        else:
            tier = "저마진 ⚠ (인프라 투자 단계)"
        lines.append(f"  영업이익률: {op_m:.1f}% — {tier}")
    if pe is not None:
        lines.append(f"  PER(F): {pe:.1f}배 — {_per_tier(pe, 20, 40)}")
    lines.append("  ※ 결제 거래량·take rate·규제 리스크는 공시 기준 확인 필요")
    intel.special_section = "\n".join(lines)


# ── CDMO/바이오프로덕션/ADC ────────────────────────────────────────────────

def _compute_cdmo_intel(
    intel: SectorIntelligence,
    fs: dict[str, Any],
) -> None:
    lines = ["🧬 CDMO/바이오생산 체크:"]
    rev_g = fs.get("revenue_growth")
    op_m = fs.get("op_margin")
    pe = fs.get("pe_forward")
    if rev_g is not None:
        lines.append(f"  매출성장: {rev_g:+.1f}% ({_growth_tier(rev_g)}, ADC/GLP-1 수혜 여부)")
    if op_m is not None:
        if op_m >= 20:
            tier = "CDMO 프리미엄 마진 ✅"
        elif op_m >= 12:
            tier = "CDMO 건전 마진"
        else:
            tier = "CDMO 마진 압박 ⚠"
        lines.append(f"  영업이익률: {op_m:.1f}% — {tier}")
    if pe is not None:
        lines.append(f"  PER(F): {pe:.1f}배 — {_per_tier(pe, 15, 35)}")
    lines.append("  ※ 수주잔고·고객사 파이프라인은 공시 기준 확인 필요")
    intel.special_section = "\n".join(lines)


# ── 매크로 민감 섹터 ────────────────────────────────────────────────────────

def _compute_macro_intel(
    intel: SectorIntelligence,
    fs: dict[str, Any],
) -> None:
    lines = [
        "📊 매크로 민감 섹터:",
        "  이 섹터는 10Y 금리·달러·원자재 방향이 주가 핵심 드라이버.",
        "  yfinance 기업 지표보다 섹터 매크로 지표(위 섹션) 우선 참고 권장.",
    ]
    pe = fs.get("pe_forward")
    if pe is not None:
        lines.append(f"  PER(F): {pe:.1f}배 — 매크로 사이클 위치 확인 후 해석 필요")
    intel.special_section = "\n".join(lines)


# ── 섹터 핸들러 디스패치 테이블 ─────────────────────────────────────────────

_SECTOR_HANDLERS: dict[str, Any] = {
    "ai_semiconductor_hbm_foundry":               _compute_semiconductor_intel,
    "semicap_equipment_materials_osat":            _compute_semicap_intel,
    _SAAS_ID:                                      _compute_saas_intel,
    "ai_power_grid_copper_nuclear":                _compute_ai_power_intel,
    "auto_ev_autonomous_robotaxi":                 _compute_ev_intel,
    "auto_ev_battery_robotaxi":                    _compute_ev_intel,    # legacy alias
    "battery_materials_lithium_recycling":         _compute_battery_materials_intel,
    "financials_banks_insurance_brokers":          _compute_financial_intel,
    "energy_oil_lng_renewables":                   _compute_energy_intel,
    "materials_chem_steel_metals_rareearth":       _compute_materials_intel,
    "kbeauty_cosmetics_odm_consumer":              _compute_kbeauty_intel,
    "retail_ecommerce_logistics_travel_airline_casino": _compute_retail_intel,
    "media_content_gaming_entertainment_ads":      _compute_media_intel,
    "telecom_network_smartphone_equipment":        _compute_telecom_intel,
    "food_agriculture_fertilizer_staples":         _compute_food_intel,
    "healthcare_services_hospitals_diagnostics":   _compute_healthcare_intel,
    "environment_waste_water_carbon_infra":        _compute_environment_intel,
    "payments_crypto_exchange_brokerage":          _compute_payments_intel,
    "cdmo_bioproduction_adc":                      _compute_cdmo_intel,
    "macro_sensitive_rates_fx_commodities":        _compute_macro_intel,
}


def build_sector_intelligence(
    symbol: str,
    name: str = "",
    market: str = "",
    sector_id: str = "",
    store: Store | None = None,
    price_snapshot: dict | None = None,
    fundamental_snapshot: dict | None = None,
    recent_issues: list[str] | None = None,
    deep: bool = False,
) -> SectorIntelligence | None:
    """섹터 ID에 맞는 심층 분석 결과 생성.

    Returns None이면 섹터 불명확 또는 플레이북 없음.
    """
    if not sector_id:
        return None
    playbook = load_playbook(sector_id)
    if playbook is None:
        log.debug("[sector_intel] 플레이북 없음: %s", sector_id)
        return None

    intel = _build_from_playbook(
        playbook=playbook,
        sector_id=sector_id,
        price_snapshot=price_snapshot or {},
        fundamental_snapshot=fundamental_snapshot or {},
        recent_issues=recent_issues or [],
    )

    _append_special_section(intel, playbook, symbol, name, market, store, deep)

    # ── 섹터별 특화 분석 (special_module 없는 섹터에 적용) ─────────────────────
    if not intel.special_section:
        handler = _SECTOR_HANDLERS.get(sector_id)
        if handler is not None:
            try:
                handler(intel, fundamental_snapshot or {})
            except Exception as exc:
                log.debug("[sector_intel] sector handler 실패 %s: %s", sector_id, exc)

    # ── valuation_playbooks.yml 보강 ─────────────────────────────────────────
    try:
        from tele_quant.sector_analysis_engine import enrich_sector_intelligence
        enrich_sector_intelligence(intel, sector_id)
    except Exception as exc:
        log.debug("[sector_intel] enrich_sector_intelligence 실패: %s", exc)

    # ── 월요일/금요일 정책 노트 ────────────────────────────────────────────────
    try:
        from tele_quant.calendar_score_policy import format_policy_note
        intel.policy_note = format_policy_note()
    except Exception:
        pass

    return intel


def format_sector_intelligence(intel: SectorIntelligence) -> str:
    """SectorIntelligence → Telegram 출력 문자열."""
    lines: list[str] = []

    lines.append(f"🔍 {intel.title} 분석:")

    if intel.summary_lines:
        for line in intel.summary_lines:
            lines.append(f"  {line}")

    if intel.key_metrics:
        lines.append(f"  핵심지표: {' | '.join(intel.key_metrics[:3])}")

    if intel.catalysts:
        lines.append(f"  ✅ 촉매: {' / '.join(intel.catalysts[:2])}")

    if intel.risks:
        lines.append(f"  ⚠ 리스크: {' / '.join(intel.risks[:2])}")

    if intel.swing_checkpoints:
        lines.append(f"  📈 스윙체크: {intel.swing_checkpoints[0]}")

    if intel.valuation_note:
        lines.append(f"  💡 가치: {intel.valuation_note}")

    if intel.special_section:
        lines.append("")
        lines.append(intel.special_section)

    if intel.exit_checkpoints:
        lines.append(f"  🚪 EXIT 관찰: {intel.exit_checkpoints[0]}")

    if intel.policy_note:
        lines.append("")
        lines.append(intel.policy_note)

    if intel.data_limitations:
        for lim in intel.data_limitations:
            lines.append(f"  ※ {lim}")

    return "\n".join(lines)
