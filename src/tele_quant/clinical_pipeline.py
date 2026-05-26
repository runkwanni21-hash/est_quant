"""Clinical pipeline — 바이오/제약 임상 단계 조회.

ClinicalTrials.gov API v2 → DB 공시 → RSS/Finnhub 순으로 시도.
임상 정보를 찾지 못하면 절대 지어내지 않고 '공개자료 기준 확인 제한'으로 표시.
"성공 가능성 높음" 같은 단정 금지.

공개 정보 기반 리서치 보조. 투자 판단 책임은 사용자에게 있음.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tele_quant.db import Store

log = logging.getLogger(__name__)

__all__ = [
    "ClinicalPipelineResult",
    "ClinicalTrial",
    "fetch_clinical_pipeline",
    "format_clinical_pipeline",
]

_CT_BASE = "https://clinicaltrials.gov/api/v2/studies"

_PHASE_DISPLAY = {
    "PHASE1": "Phase 1",
    "PHASE2": "Phase 2",
    "PHASE3": "Phase 3",
    "PHASE4": "Phase 4",
    "NA": "N/A",
    "EARLY_PHASE1": "Phase 1 (초기)",
}

_STATUS_DISPLAY = {
    "RECRUITING": "모집 중",
    "ACTIVE_NOT_RECRUITING": "진행 중 (모집 종료)",
    "COMPLETED": "완료",
    "SUSPENDED": "중단",
    "TERMINATED": "종료",
    "WITHDRAWN": "철회",
    "ENROLLING_BY_INVITATION": "초청 모집",
    "NOT_YET_RECRUITING": "모집 예정",
}

_FDA_PAT = re.compile(
    r"(PDUFA|NDA|BLA|FDA|IND|EMA|MFDS|허가|승인|Phase\s*\d|임상\s*\d|단계)",
    re.IGNORECASE,
)


@dataclass
class ClinicalTrial:
    """단일 임상시험 정보."""

    nct_id: str = ""
    title: str = ""
    phase: str = ""               # Phase 1 / Phase 2 / Phase 3 / ...
    status: str = ""              # 모집 중 / 완료 / ...
    condition: str = ""           # 적응증
    sponsor: str = ""             # 후원사
    primary_completion: str = ""  # primary completion date
    completion_date: str = ""
    start_date: str = ""
    source: str = "ClinicalTrials.gov"


@dataclass
class ClinicalPipelineResult:
    """임상 파이프라인 조회 결과."""

    symbol: str
    name: str = ""
    trials: list[ClinicalTrial] = field(default_factory=list)
    headline_signals: list[str] = field(default_factory=list)   # 공시/뉴스 기반 단서
    cash_burn_note: str = ""       # 현금소진/증자 리스크 단서
    partner_note: str = ""         # 파트너/기술이전 단서
    market_note: str = ""          # TAM/시장성 단서
    data_limited: bool = False
    limitation_note: str = ""


def _fetch_clinicaltrials(query: str, max_results: int = 5, timeout: float = 8.0) -> list[ClinicalTrial]:
    """ClinicalTrials.gov API v2에서 임상시험 목록을 조회한다."""
    try:
        import json
        import urllib.parse
        import urllib.request

        params = f"?query.term={urllib.parse.quote(query)}&pageSize={max_results}&format=json"
        url = _CT_BASE + params
        req = urllib.request.Request(url, headers={"User-Agent": "tele-quant/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode())

        studies = data.get("studies") or []
        results: list[ClinicalTrial] = []
        for study in studies[:max_results]:
            proto = study.get("protocolSection") or {}
            id_mod = proto.get("identificationModule") or {}
            status_mod = proto.get("statusModule") or {}
            design_mod = proto.get("designModule") or {}
            cond_mod = proto.get("conditionsModule") or {}
            sponsor_mod = proto.get("sponsorCollaboratorsModule") or {}

            phases_raw = design_mod.get("phases") or []
            phase_str = " / ".join(_PHASE_DISPLAY.get(p, p) for p in phases_raw) or "확인 제한"
            status_raw = status_mod.get("overallStatus") or ""
            status_str = _STATUS_DISPLAY.get(status_raw, status_raw) or "확인 제한"
            conditions = cond_mod.get("conditions") or []
            condition_str = " / ".join(conditions[:3])
            lead = (sponsor_mod.get("leadSponsor") or {}).get("name") or ""

            pc_struct = status_mod.get("primaryCompletionDateStruct") or {}
            pc_date = pc_struct.get("date") or ""
            comp_struct = status_mod.get("completionDateStruct") or {}
            comp_date = comp_struct.get("date") or ""
            start_struct = status_mod.get("startDateStruct") or {}
            start_date = start_struct.get("date") or ""

            results.append(ClinicalTrial(
                nct_id=id_mod.get("nctId") or "",
                title=(id_mod.get("briefTitle") or "")[:120],
                phase=phase_str,
                status=status_str,
                condition=condition_str[:80],
                sponsor=lead[:60],
                primary_completion=pc_date,
                completion_date=comp_date,
                start_date=start_date,
            ))
        return results
    except Exception as exc:
        log.debug("[clinical] ClinicalTrials.gov 조회 실패 (%s): %s", query, exc)
        return []



def _extract_from_db(symbol: str, name: str, store: Store) -> tuple[list[str], str, str, str]:
    """DB raw_items / sentiment_history에서 임상 관련 headline 추출."""
    signals: list[str] = []
    cash_note = ""
    partner_note = ""
    market_note = ""
    try:
        with store.connect() as conn:
            rows = conn.execute(
                "SELECT title, source_name FROM raw_items ORDER BY published_at DESC LIMIT 200"
            ).fetchall()
        search_terms = [symbol.upper(), name.upper()[:10]] if name else [symbol.upper()]
        for row in rows:
            title = (row[0] or "").strip()
            if not title:
                continue
            upper_title = title.upper()
            if not any(t in upper_title for t in search_terms if t):
                continue
            if _FDA_PAT.search(title):
                signals.append(title[:120])
            if re.search(r"현금|유상증자|CB|전환사채|BW|차입|증자|burn|cash", title, re.I):
                cash_note = title[:80] + " (공시 기반)"
            if re.search(r"기술이전|파트너|라이선스|MOU|LOI|협약|partner|license|deal", title, re.I):
                partner_note = title[:80] + " (공시 기반)"
            if re.search(r"시장|TAM|GLP|비만|항암|ADC|면역|표적|market|billion", title, re.I):
                market_note = title[:80] + " (공시 기반)"
    except Exception as exc:
        log.debug("[clinical] DB 추출 실패 %s: %s", symbol, exc)
    return signals[:5], cash_note, partner_note, market_note


def _load_clinical_aliases(symbol: str) -> dict:
    """config/clinical_aliases.yml에서 해당 symbol의 alias 로드."""
    try:
        from pathlib import Path

        import yaml  # type: ignore[import]
        alias_path = Path(__file__).parent.parent.parent / "config" / "clinical_aliases.yml"
        if not alias_path.exists():
            return {}
        with alias_path.open(encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return data.get(symbol) or data.get(symbol.upper()) or {}
    except Exception as exc:
        log.debug("[clinical] alias load failed: %s", exc)
        return {}


def fetch_clinical_pipeline(
    symbol: str,
    name: str = "",
    market: str = "",
    store: Store | None = None,
    deep: bool = False,
    timeout: float = 8.0,
) -> ClinicalPipelineResult:
    """임상 파이프라인 조회 — ClinicalTrials.gov + DB alias."""
    result = ClinicalPipelineResult(symbol=symbol, name=name)

    # ── alias 로드 ────────────────────────────────────────────────────────────
    aliases = _load_clinical_aliases(symbol)
    company_names: list[str] = aliases.get("company_names") or []
    pipeline_terms: list[str] = aliases.get("pipeline_terms") or []

    # ── ClinicalTrials.gov 조회 ───────────────────────────────────────────────
    queries: list[str] = []
    # 1순위: alias company_names (영문명 정확도 높음)
    for cname in company_names[:2]:
        queries.append(cname)
    # 2순위: 전달된 name (KR 한글명 → 영문 검색 힘드니 낮은 우선순위)
    if name and name not in queries:
        queries.append(name[:40])
    # 3순위: pipeline_terms (약물명/타겟)
    for term in pipeline_terms[:3]:
        queries.append(term)
    # 4순위: symbol fallback
    if symbol not in queries:
        queries.append(symbol)

    seen_ncts: set[str] = set()
    for q in queries:
        trials = _fetch_clinicaltrials(q, max_results=5, timeout=timeout)
        for t in trials:
            if t.nct_id not in seen_ncts:
                seen_ncts.add(t.nct_id)
                result.trials.append(t)
        if result.trials:
            break  # 첫 번째로 결과가 나온 query에서 멈춤

    if not result.trials and not deep:
        result.data_limited = True
        result.limitation_note = "ClinicalTrials.gov 공개자료 기준 확인 제한"

    # ── DB 공시/뉴스 기반 단서 ────────────────────────────────────────────────
    if store is not None:
        signals, cash_note, partner_note, market_note = _extract_from_db(symbol, name, store)
        result.headline_signals = signals
        if cash_note:
            result.cash_burn_note = cash_note
        if partner_note:
            result.partner_note = partner_note
        if market_note:
            result.market_note = market_note

    if not result.trials and not result.headline_signals:
        result.data_limited = True
        result.limitation_note = "공개자료 기준 임상 정보 확인 제한 — ClinicalTrials.gov 직접 확인 권장"

    return result


def format_clinical_pipeline(result: ClinicalPipelineResult) -> str:
    """ClinicalPipelineResult → Telegram 출력."""
    lines = ["🧬 바이오/임상 체크:"]

    if result.trials:
        for trial in result.trials[:3]:
            lines.append(f"  • {trial.title[:80]}")
            lines.append(f"    단계: {trial.phase} | 상태: {trial.status}")
            if trial.condition:
                lines.append(f"    적응증: {trial.condition}")
            if trial.primary_completion:
                lines.append(f"    Primary Completion: {trial.primary_completion}")
            elif trial.completion_date:
                lines.append(f"    Completion: {trial.completion_date}")
            else:
                lines.append("    일정: 공개자료 기준 확인 제한")
    else:
        lines.append("  • 파이프라인: 공개자료 기준 확인 제한")

    if result.headline_signals:
        lines.append("  ─ 공시/뉴스 단서:")
        for sig in result.headline_signals[:3]:
            lines.append(f"    > {sig[:100]}")

    if result.partner_note:
        lines.append(f"  • 파트너/기술이전: {result.partner_note[:80]}")
    else:
        lines.append("  • 파트너/기술이전: 공개자료 기준 확인 제한")

    if result.market_note:
        lines.append(f"  • 시장성: {result.market_note[:80]}")

    if result.cash_burn_note:
        lines.append(f"  ⚠ 현금소진/증자 단서: {result.cash_burn_note[:80]}")
    else:
        lines.append("  ⚠ 현금소진/증자 리스크: 공시 기준 확인 필요")

    lines.append("  ※ 임상 단계상 변동성 큼 — 결과 발표 전후 가격 변동성 확대 가능")
    lines.append("  ※ FDA/MFDS 일정은 출처가 없으면 '예정일 확인 제한'")

    if result.limitation_note:
        lines.append(f"  ※ {result.limitation_note}")

    return "\n".join(lines)
