"""Sector Valuation — 섹터별 가치분석 엔진.

섹터 키 자동 감지 후 섹터별 특화 분석을 수행하고 SectorAnalysis 객체를 반환한다.

주의: 공개 정보 기반 리서치 보조. 투자 판단 책임은 사용자에게 있음.
      "매수 권장" / "매도 권장" / "확정 수익" 표현 금지.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from tele_quant.db import Store

log = logging.getLogger(__name__)

__all__ = ["SectorAnalysis", "analyze_sector_value", "detect_sector_key"]


# ── 데이터 모델 ───────────────────────────────────────────────────────────────


@dataclass
class SectorAnalysis:
    """섹터별 가치분석 결과 컨테이너."""

    sector: str                             # 원본 섹터 문자열
    key: str = ""                           # 내부 분류 키
    title: str = ""                         # 섹터 표시 제목
    score: float = 50.0                     # 섹터 매력도 점수 (0~100)
    lines: list[str] = field(default_factory=list)          # 주요 관찰 라인
    risks: list[str] = field(default_factory=list)          # 리스크 항목
    catalysts: list[str] = field(default_factory=list)      # 촉매 항목
    peer_symbols: list[str] = field(default_factory=list)   # 동종업계 심볼
    victim_symbols: list[str] = field(default_factory=list) # 피해 우려 심볼
    next_checkpoints: list[str] = field(default_factory=list)  # 다음 확인 포인트


# ── 섹터 키 매핑 ──────────────────────────────────────────────────────────────

_SECTOR_MAP: dict[str, str] = {
    # ── sector_id 직접 매핑 (ticker_universe / sector_macro override 값) ──────
    "ai_semiconductor_hbm_foundry": "semiconductor",
    "semiconductor_equipment_materials_osat": "semiconductor",
    "biotech_pharma_clinical_medtech": "bio",
    "cdmo_bioproduction_adc": "bio",
    "healthcare_services_hospitals_diagnostics": "bio",
    "shipbuilding_shipping_lng_equipment": "shipbuilding",
    "defense_space_aerospace_drone": "defense",
    "construction_realestate_reit": "construction",
    "ai_power_grid_cable_nuclear": "ai_power",
    "auto_ev_autonomous_robotaxi": "ev",
    "battery_materials_cathode_anode": "ev",
    "financials_banks_insurance_brokers": "finance",
    "k_beauty_cosmetics_personal_care": "beauty",
    "ai_software_cloud_cybersecurity": "software",
    "auto_robotics_industrials": "auto",
    # ── yfinance / 한국어 원본 섹터 문자열 ────────────────────────────────────
    "제약": "bio",
    "바이오": "bio",
    "의약품": "bio",
    "Healthcare": "bio",
    "Biotechnology": "bio",
    "Pharmaceuticals": "bio",
    "CDMO": "bio",
    "CRO": "bio",
    "반도체": "semiconductor",
    "Semiconductors": "semiconductor",
    "조선": "shipbuilding",
    "방산": "defense",
    "Aerospace": "defense",
    "건설": "construction",
    "전기장비": "ai_power",
    "Utilities": "ai_power",
    "전력": "ai_power",
    "이차전지": "ev",
    "자동차": "ev",
    "금융": "finance",
    "은행": "finance",
    "보험": "finance",
    "증권": "finance",
    "Financials": "finance",
    "화장품": "beauty",
    "소프트웨어": "software",
    "Communication Services": "software",
    "로봇": "auto",
    "산업재": "auto",
    "Industrials": "industrials",
    "Technology": "technology",
}

_SEMI_SYMS: frozenset[str] = frozenset(
    {
        "NVDA",
        "AMD",
        "INTC",
        "TSM",
        "ASML",
        "AMAT",
        "LRCX",
        "KLAC",
        "MU",
        "SNPS",
        "CDNS",
        "QCOM",
        "AVGO",
        "ARM",
        "SMCI",
    }
)

_BIO_SYMS: frozenset[str] = frozenset(
    {
        "MRNA",
        "BNTX",
        "REGN",
        "VRTX",
        "GILD",
        "AMGN",
        "ABBV",
        "PFE",
        "LLY",
        "NVO",
        "ISRG",
        "DXCM",
    }
)


# ── 섹터 키 감지 ──────────────────────────────────────────────────────────────


def detect_sector_key(sector: str, symbol: str = "") -> str:
    """섹터 문자열과 심볼로 내부 분류 키를 반환한다.

    우선순위:
    1. symbol 레벨 override (bio/semi)
    2. _SECTOR_MAP 직접 매핑
    3. 섹터 문자열 부분 포함 검사
    4. "technology" 키 → _SEMI_SYMS 포함 여부로 분기
    5. 미분류 → "general"
    """
    sym_upper = symbol.upper().split(".")[0]  # "005930.KS" → "005930"

    # symbol 레벨 override
    if sym_upper in _BIO_SYMS:
        return "bio"
    if sym_upper in _SEMI_SYMS:
        return "semiconductor"

    # 직접 매핑
    key = _SECTOR_MAP.get(sector, "")
    if not key:
        # 부분 문자열 포함 검사 (대소문자 무시)
        sector_lower = sector.lower()
        for map_key, map_val in _SECTOR_MAP.items():
            if map_key.lower() in sector_lower:
                key = map_val
                break

    if key == "technology":
        return "semiconductor" if sym_upper in _SEMI_SYMS else "software"

    return key or "general"


# ── 이슈 키워드 필터 헬퍼 ────────────────────────────────────────────────────


def _filter_issues(
    issues: list[str] | None,
    keywords: list[str],
    max_items: int = 3,
) -> list[str]:
    """issues 리스트에서 키워드 포함 항목을 최대 max_items 개 반환."""
    if not issues:
        return []
    matched: list[str] = []
    for issue in issues:
        if any(kw.lower() in issue.lower() for kw in keywords):
            matched.append(issue)
            if len(matched) >= max_items:
                break
    return matched


# ── 섹터별 분석 함수 ──────────────────────────────────────────────────────────


def _analyze_bio(
    symbol: str,
    market: str,
    sector: str,
    fund_snapshot: dict[str, Any] | None,
    issues: list[str] | None,
) -> SectorAnalysis:
    """바이오/제약/CDMO 섹터 분석."""
    bio_keywords = [
        "임상",
        "FDA",
        "EMA",
        "식약처",
        "NDA",
        "BLA",
        "Phase",
        "PDUFA",
        "승인",
        "허가",
        "파이프라인",
        "기술이전",
        "CDMO",
    ]
    matched_issues = _filter_issues(issues, bio_keywords, max_items=3)

    lines: list[str] = [
        "바이오는 PER보다 임상 단계·시장규모·현금소진 리스크가 더 중요합니다.",
    ]
    lines.extend(matched_issues)

    return SectorAnalysis(
        sector=sector,
        key="bio",
        title="바이오/제약/CDMO",
        score=50.0,
        lines=lines,
        risks=[
            "임상 실패/중단 리스크 (Phase 2/3 성공률 ~20%)",
            "현금 소진·증자 리스크",
            "규제기관 심사 지연",
        ],
        catalysts=[
            "Phase 3 긍정 결과 / FDA 허가",
            "기술이전·파트너십 체결",
            "CDMO 대형 계약",
        ],
        next_checkpoints=[
            "임상 결과 발표일 / PDUFA 날짜 확인",
            "현금성 자산·증자 공시 모니터링",
        ],
    )


def _analyze_semiconductor(
    symbol: str,
    market: str,
    sector: str,
    fund_snapshot: dict[str, Any] | None,
    issues: list[str] | None,
) -> SectorAnalysis:
    """반도체 섹터 분석."""
    semi_keywords = [
        "HBM",
        "DRAM",
        "NAND",
        "AI",
        "capex",
        "수주",
        "TSM",
        "NVDA",
        "AMD",
        "삼성",
        "하이닉스",
        "ASML",
        "AMAT",
        "재고",
        "ASP",
    ]
    matched_issues = _filter_issues(issues, semi_keywords, max_items=3)

    lines: list[str] = [
        "AI Capex 사이클 수혜 — HBM3e/DRAM 가격 추세 중요.",
        "장비주는 선행 발주 후 6~12개월 매출 인식 래그 존재.",
    ]
    lines.extend(matched_issues)

    peer_us = ["MU", "AMAT", "LRCX", "KLAC", "ASML"]
    peer_kr = ["000660.KS", "042700.KS", "357780.KS"]
    peer_symbols = peer_kr if market.upper() == "KR" else peer_us

    return SectorAnalysis(
        sector=sector,
        key="semiconductor",
        title="반도체/장비",
        score=65.0,
        lines=lines,
        risks=[
            "메모리 재고 재축적 속도",
            "중국 반도체 규제/수출 제한",
            "AI Capex 조정 시 수요 급감",
        ],
        catalysts=[
            "HBM4/DRAM 가격 상승",
            "NVDA/AMD 수주 공시",
            "신규 팹 장비 발주",
        ],
        peer_symbols=peer_symbols,
        next_checkpoints=[
            "NVDA 실적·가이던스",
            "삼성·SK하이닉스 메모리 가격",
            "AMAT/LRCX 수주잔고",
        ],
    )


def _analyze_shipbuilding(
    symbol: str,
    market: str,
    sector: str,
    fund_snapshot: dict[str, Any] | None,
    issues: list[str] | None,
) -> SectorAnalysis:
    """조선 섹터 분석."""
    lines: list[str] = [
        "조선은 PER보다 수주잔고·선가·납기·마진 개선이 중요합니다.",
    ]
    shipbuilding_keywords = ["수주", "선가", "LNG", "탱커", "납기", "Clarkson", "철강"]
    lines.extend(_filter_issues(issues, shipbuilding_keywords, max_items=3))

    return SectorAnalysis(
        sector=sector,
        key="shipbuilding",
        title="조선/해운",
        score=60.0,
        lines=lines,
        risks=[
            "원자재(철강) 가격→마진 압박",
            "환율 변동(USD수주/KRW원가)",
            "납기 지연",
        ],
        catalysts=[
            "LNG선·탱커 대형 수주",
            "선가(Clarkson) 지속 상승",
            "수주잔고 >3년분",
        ],
        next_checkpoints=[
            "DART 수주 공시",
            "Clarkson 선가 지수",
        ],
    )


def _analyze_defense(
    symbol: str,
    market: str,
    sector: str,
    fund_snapshot: dict[str, Any] | None,
    issues: list[str] | None,
) -> SectorAnalysis:
    """방산 섹터 분석."""
    lines: list[str] = [
        "방산은 정부 계약 수주·납기·마진 구조가 핵심 지표입니다.",
    ]
    defense_keywords = [
        "수주",
        "계약",
        "폴란드",
        "루마니아",
        "호주",
        "NATO",
        "방위비",
        "무기",
        "수출",
    ]
    lines.extend(_filter_issues(issues, defense_keywords, max_items=3))

    return SectorAnalysis(
        sector=sector,
        key="defense",
        title="방산/항공우주",
        score=60.0,
        lines=lines,
        risks=[
            "지정학 긴장 완화 시 예산 감소 가능성",
            "원자재·공급망 비용 상승",
            "납기 지연·계약 취소 리스크",
        ],
        catalysts=[
            "폴란드·루마니아·호주 대형 계약",
            "NATO 회원국 국방비 확대",
            "신형 무기체계 수출 허가",
        ],
        next_checkpoints=[
            "DART/SEC 수주 공시",
            "각국 국방예산 편성 일정",
        ],
    )


def _analyze_construction(
    symbol: str,
    market: str,
    sector: str,
    fund_snapshot: dict[str, Any] | None,
    issues: list[str] | None,
) -> SectorAnalysis:
    """건설 섹터 분석."""
    lines: list[str] = [
        "건설은 수주잔고·원가율·미분양·부동산 규제가 핵심 변수입니다.",
    ]
    construction_keywords = ["수주", "PF", "미분양", "원가", "부동산", "분양", "금리"]
    lines.extend(_filter_issues(issues, construction_keywords, max_items=3))

    return SectorAnalysis(
        sector=sector,
        key="construction",
        title="건설/부동산",
        score=50.0,
        lines=lines,
        risks=[
            "PF(프로젝트파이낸싱) 부실 리스크",
            "미분양 증가·수익성 악화",
            "금리 상승 시 수요 위축",
        ],
        catalysts=[
            "정부 부동산 규제 완화",
            "해외 수주(중동·동남아) 확대",
            "금리 인하 사이클 진입",
        ],
        next_checkpoints=[
            "미분양 통계 (국토부 월간)",
            "PF 만기·연장 현황",
        ],
    )


def _analyze_ai_power(
    symbol: str,
    market: str,
    sector: str,
    fund_snapshot: dict[str, Any] | None,
    issues: list[str] | None,
) -> SectorAnalysis:
    """AI전력/전선/변압기/원전 섹터 분석."""
    lines: list[str] = [
        "데이터센터 전력 수요 폭증 → 변압기·전력기기 수혜 구간.",
        "구리·전선·원전 연료까지 수요 체인 전반에 긍정적 흐름.",
    ]
    power_keywords = [
        "데이터센터",
        "전력",
        "변압기",
        "전선",
        "구리",
        "원전",
        "핵연료",
        "AI",
        "Grid",
    ]
    lines.extend(_filter_issues(issues, power_keywords, max_items=3))

    peer_us = ["ETN", "GEV", "HUBB"]
    peer_kr = ["010120.KS", "298040.KS", "267260.KS"]
    peer_symbols = peer_kr if market.upper() == "KR" else peer_us

    return SectorAnalysis(
        sector=sector,
        key="ai_power",
        title="AI전력/전선/원전",
        score=62.0,
        lines=lines,
        risks=[
            "전력망 투자 지연·규제 승인 장기화",
            "구리 가격 변동성",
            "원전 정책 전환 리스크",
        ],
        catalysts=[
            "빅테크 데이터센터 전력계약 공시",
            "전력망 현대화 예산 확대",
            "원전 신규 허가·수출 계약",
        ],
        peer_symbols=peer_symbols,
        next_checkpoints=[
            "EIA 전력 수요 통계",
            "구리 LME 가격 추이",
            "데이터센터 전력 계약 공시",
        ],
    )


def _analyze_ev(
    symbol: str,
    market: str,
    sector: str,
    fund_snapshot: dict[str, Any] | None,
    issues: list[str] | None,
) -> SectorAnalysis:
    """배터리/EV/소재 섹터 분석."""
    lines: list[str] = [
        "리튬·니켈 가격, IRA 세액공제, OEM 수주가 배터리·소재 섹터 핵심 변수.",
    ]
    ev_keywords = [
        "리튬",
        "니켈",
        "IRA",
        "OEM",
        "배터리",
        "전기차",
        "EV",
        "수주",
        "Cell",
        "ESS",
    ]
    lines.extend(_filter_issues(issues, ev_keywords, max_items=3))

    return SectorAnalysis(
        sector=sector,
        key="ev",
        title="EV/배터리/소재",
        score=55.0,
        lines=lines,
        risks=[
            "리튬·니켈 가격 하락 시 소재 업체 마진 압박",
            "IRA 세액공제 정책 변경 리스크",
            "EV 수요 성장 둔화",
        ],
        catalysts=[
            "OEM 배터리 대형 수주 공시",
            "IRA 세액공제 적용 확대",
            "리튬·니켈 가격 반등",
        ],
        next_checkpoints=[
            "리튬·니켈 현물 가격",
            "OEM EV 판매량 월간 통계",
            "IRA 정책 동향",
        ],
    )


def _analyze_finance(
    symbol: str,
    market: str,
    sector: str,
    fund_snapshot: dict[str, Any] | None,
    issues: list[str] | None,
) -> SectorAnalysis:
    """금융/은행/보험/증권 섹터 분석."""
    lines: list[str] = [
        "NIM(순이자마진), NPL(부실여신), PBR, 배당수익률이 금융 섹터 핵심 지표.",
    ]

    # PBR 기반 valuation 판단
    pb: float | None = None
    if fund_snapshot:
        pb_raw = fund_snapshot.get("pb") or fund_snapshot.get("priceToBook")
        if pb_raw is not None:
            try:
                pb = float(pb_raw)
            except (ValueError, TypeError):
                pb = None

    if pb is not None:
        if pb < 0.7:
            lines.append(f"PBR {pb:.2f} — 장부가 대비 저평가 구간 (역사적 반등 선호).")
        elif pb > 1.5:
            lines.append(f"PBR {pb:.2f} — 프리미엄 구간, 성장성 재확인 필요.")
        else:
            lines.append(f"PBR {pb:.2f} — 중립 밸류에이션 구간.")

    finance_keywords = ["NIM", "NPL", "금리", "배당", "자본비율", "BIS", "대손", "이자"]
    lines.extend(_filter_issues(issues, finance_keywords, max_items=2))

    return SectorAnalysis(
        sector=sector,
        key="finance",
        title="금융/은행/보험/증권",
        score=58.0,
        lines=lines,
        risks=[
            "금리 하락 시 NIM 축소",
            "NPL 상승·대손충당금 확대",
            "부동산 PF 부실 전이 리스크",
        ],
        catalysts=[
            "금리 안정화·NIM 개선",
            "주주환원(자사주·배당) 확대 발표",
            "자산 건전성 개선 공시",
        ],
        next_checkpoints=[
            "기준금리 결정 일정 (한은/Fed)",
            "분기별 NPL·NIM 공시",
        ],
    )


def _analyze_beauty(
    symbol: str,
    market: str,
    sector: str,
    fund_snapshot: dict[str, Any] | None,
    issues: list[str] | None,
) -> SectorAnalysis:
    """K뷰티/화장품 섹터 분석."""
    lines: list[str] = [
        "K뷰티 미국·일본 수출 성장세, ODM 구조 다변화가 핵심 성장 동력.",
    ]
    beauty_keywords = ["수출", "ODM", "미국", "일본", "ELF", "ULTA", "아모레", "화장품"]
    lines.extend(_filter_issues(issues, beauty_keywords, max_items=3))

    peer_us = ["ELF", "ULTA"]
    peer_kr = ["090430.KS", "161890.KS"]
    peer_symbols = peer_kr if market.upper() == "KR" else peer_us

    return SectorAnalysis(
        sector=sector,
        key="beauty",
        title="K뷰티/화장품",
        score=60.0,
        lines=lines,
        risks=[
            "중국 수요 회복 지연",
            "원/달러 환율 급락 시 수출 채산성 악화",
            "경쟁 심화(글로벌 브랜드)",
        ],
        catalysts=[
            "미국·일본 수출 호조 공시",
            "ELF/ULTA 입점·협업 발표",
            "ODM 신규 고객사 계약",
        ],
        peer_symbols=peer_symbols,
        next_checkpoints=[
            "월간 화장품 수출 통계 (산업부)",
            "미국 ELF/ULTA 실적 가이던스",
        ],
    )


def _analyze_software(
    symbol: str,
    market: str,
    sector: str,
    fund_snapshot: dict[str, Any] | None,
    issues: list[str] | None,
) -> SectorAnalysis:
    """SaaS/AI 소프트웨어 섹터 분석."""
    lines: list[str] = [
        "Rule of 40 (매출성장률 + 영업이익률 >= 40)이 SaaS 밸류에이션 기준.",
    ]

    # Rule of 40 계산
    if fund_snapshot:
        rev_growth = fund_snapshot.get("revenueGrowth") or fund_snapshot.get(
            "rev_growth"
        )
        op_margin = fund_snapshot.get("operatingMargins") or fund_snapshot.get(
            "op_margin"
        )
        if rev_growth is not None and op_margin is not None:
            try:
                rg = float(rev_growth) * 100  # 소수 → %
                om = float(op_margin) * 100
                rule40 = rg + om
                if rule40 >= 40:
                    lines.append(
                        f"Rule of 40 충족: 매출성장 {rg:.1f}% + 영업이익률 {om:.1f}% = {rule40:.1f}"
                    )
                else:
                    lines.append(
                        f"Rule of 40 미충족: 매출성장 {rg:.1f}% + 영업이익률 {om:.1f}% = {rule40:.1f}"
                    )
            except (ValueError, TypeError):
                pass

    software_keywords = ["SaaS", "ARR", "NRR", "AI", "구독", "클라우드", "churn", "계약"]
    lines.extend(_filter_issues(issues, software_keywords, max_items=3))

    return SectorAnalysis(
        sector=sector,
        key="software",
        title="소프트웨어/SaaS/AI",
        score=55.0,
        lines=lines,
        risks=[
            "AI 경쟁 심화로 가격 인하 압력",
            "고객 이탈률(Churn) 상승",
            "성장 둔화 시 멀티플 급락",
        ],
        catalysts=[
            "ARR 가속 성장 + NRR 110% 이상",
            "AI 기능 탑재로 ARPU 상승",
            "신규 대형 엔터프라이즈 계약",
        ],
        next_checkpoints=[
            "분기 ARR·NRR 실적",
            "AI 제품 출시·채택률 공시",
        ],
    )


def _analyze_auto(
    symbol: str,
    market: str,
    sector: str,
    fund_snapshot: dict[str, Any] | None,
    issues: list[str] | None,
) -> SectorAnalysis:
    """자동차/로봇/산업재 섹터 분석."""
    lines: list[str] = [
        "자동차·로봇은 출하량·ASP·환율 영향이 크고, 공급망 정상화 여부가 중요.",
    ]
    auto_keywords = ["출하", "ASP", "환율", "로봇", "자율주행", "부품", "수주", "공급망"]
    lines.extend(_filter_issues(issues, auto_keywords, max_items=3))

    return SectorAnalysis(
        sector=sector,
        key="auto",
        title="자동차/로봇/산업재",
        score=58.0,
        lines=lines,
        risks=[
            "원/달러 환율 변동성 → 수출 채산성",
            "공급망(반도체·소재) 차질",
            "EV 전환 속도 대비 내연기관 재고 부담",
        ],
        catalysts=[
            "신차 출시·글로벌 판매량 호조",
            "로봇 신규 수주 및 상용화 확대",
            "공급망 정상화·원가 절감",
        ],
        next_checkpoints=[
            "월간 자동차 판매 통계",
            "로봇 수주잔고 공시",
        ],
    )


def _analyze_general(
    symbol: str,
    market: str,
    sector: str,
    fund_snapshot: dict[str, Any] | None,
    issues: list[str] | None,
) -> SectorAnalysis:
    """분류 불가 일반 섹터 분석."""
    lines: list[str] = [
        f"{sector} 섹터 — 범용 분석. 종목별 펀더멘탈 개별 검토 필요.",
    ]
    return SectorAnalysis(
        sector=sector,
        key="general",
        title=sector or "기타",
        score=50.0,
        lines=lines,
        risks=["섹터 특성 불명확 — 개별 리스크 직접 점검 권장"],
        catalysts=["섹터 특성 불명확 — 개별 촉매 직접 점검 권장"],
        next_checkpoints=["종목 개별 공시·실적 일정 확인"],
    )


# ── 섹터 분석 디스패처 ────────────────────────────────────────────────────────

_ANALYZERS = {
    "bio": _analyze_bio,
    "semiconductor": _analyze_semiconductor,
    "shipbuilding": _analyze_shipbuilding,
    "defense": _analyze_defense,
    "construction": _analyze_construction,
    "ai_power": _analyze_ai_power,
    "ev": _analyze_ev,
    "finance": _analyze_finance,
    "beauty": _analyze_beauty,
    "software": _analyze_software,
    "auto": _analyze_auto,
    "industrials": _analyze_auto,   # industrials → auto 분석 공유
}


def analyze_sector_value(
    symbol: str,
    market: str,
    sector: str,
    fund_snapshot: dict[str, Any] | None = None,
    issues: list[str] | None = None,
    store: Store | None = None,  # 향후 DB 연동 확장 예약
) -> SectorAnalysis:
    """섹터별 가치분석을 수행하고 SectorAnalysis 객체를 반환한다.

    Args:
        symbol:        종목 티커.
        market:        "KR" 또는 "US".
        sector:        yfinance/DART 등에서 가져온 원본 섹터 문자열.
        fund_snapshot: 펀더멘탈 딕셔너리 (pb, revenueGrowth, operatingMargins 등).
        issues:        최근 이슈/뉴스 문자열 리스트.
        store:         DB Store (현재 미사용, 향후 확장).

    Returns:
        SectorAnalysis 인스턴스.

    Note:
        매수·매도 권장 표현은 출력하지 않습니다.
        공개 정보 기반 리서치 보조 — 투자 판단 책임은 사용자에게 있음.
    """
    key = detect_sector_key(sector, symbol)
    analyzer = _ANALYZERS.get(key, _analyze_general)

    try:
        result = analyzer(
            symbol=symbol,
            market=market,
            sector=sector,
            fund_snapshot=fund_snapshot,
            issues=issues,
        )
    except Exception:
        log.warning(
            "섹터 분석 실패 — symbol=%s sector=%s key=%s",
            symbol,
            sector,
            key,
            exc_info=True,
        )
        result = _analyze_general(
            symbol=symbol,
            market=market,
            sector=sector,
            fund_snapshot=fund_snapshot,
            issues=issues,
        )

    log.debug(
        "sector_valuation: symbol=%s sector=%s key=%s score=%.1f",
        symbol,
        sector,
        result.key,
        result.score,
    )
    return result
