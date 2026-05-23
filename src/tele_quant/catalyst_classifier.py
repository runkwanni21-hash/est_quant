"""Catalyst classifier — 급등락 이유가 이벤트성인지 단순 수급인지 구분.

CatalystType / CatalystConfidence 분류.
FLOW_ONLY / UNKNOWN이면 relation target 추천 금지.
LOW confidence이면 WATCH_ONLY.

공개 정보 기반 리서치 보조. 투자 판단 책임은 사용자에게 있음.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum


class CatalystType(StrEnum):
    DART_CONTRACT = "DART_CONTRACT"
    SEC_8K = "SEC_8K"
    EARNINGS = "EARNINGS"
    GUIDANCE = "GUIDANCE"
    CLINICAL = "CLINICAL"
    FDA_MFDS = "FDA_MFDS"
    POLICY = "POLICY"
    REGULATION = "REGULATION"
    ORDER_BACKLOG = "ORDER_BACKLOG"
    MACRO = "MACRO"
    RELATION_READTHROUGH = "RELATION_READTHROUGH"
    FLOW_ONLY = "FLOW_ONLY"
    UNKNOWN = "UNKNOWN"


class CatalystConfidence(StrEnum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


@dataclass
class CatalystResult:
    catalyst_type: CatalystType
    confidence: CatalystConfidence
    reason: str = ""
    source_tags: list[str] = field(default_factory=list)

    @property
    def is_actionable(self) -> bool:
        """FLOW_ONLY / UNKNOWN은 relation 추천 금지."""
        return self.catalyst_type not in (CatalystType.FLOW_ONLY, CatalystType.UNKNOWN)

    @property
    def relation_eligible(self) -> bool:
        """MEDIUM 이상 + actionable이면 relation seed 확장 허용."""
        return self.is_actionable and self.confidence in (
            CatalystConfidence.HIGH,
            CatalystConfidence.MEDIUM,
        )

    @property
    def recommendation_side(self) -> str:
        """LOW confidence이면 WATCH_ONLY."""
        if not self.is_actionable:
            return "WATCH_ONLY"
        if self.confidence == CatalystConfidence.LOW:
            return "WATCH_ONLY"
        return "ACTIVE"


# ── 소스 타입 신뢰도 기본값 ────────────────────────────────────────────────────

_HIGH_CONFIDENCE_SOURCES = frozenset({
    "dart",
    "sec",
    "sec_8k",
    "opendart",
    "edgar",
    "ir",
    "press_release",
    "official",
    "reuters",
    "bloomberg",
    "ap",
    "wsj",
    "marketwatch",
    "barrons",
    "cnbc",
    "ft",
    "nikkei",
    "yonhap",
})

_MEDIUM_CONFIDENCE_SOURCES = frozenset({
    "rss",
    "finnhub",
    "google_news",
    "pr_newswire",
    "globe_newswire",
    "business_wire",
    "seeking_alpha",
    "yahoo_finance",
    "naver_news",
    "infomax",
    "ecos",
    "eia",
    "ecb",
})

_LOW_CONFIDENCE_SOURCES = frozenset({
    "telegram",
    "twitter",
    "reddit",
    "community",
    "unknown",
    "price_only",
    "volume_only",
})

# ── 텍스트 패턴 분류 ─────────────────────────────────────────────────────────

_DART_PATTERNS = re.compile(
    r"(수주|계약|공시|DART|공급계약|납품|수출|자사주|유상증자|전환사채|CB|BW|CB신주|CB전환|"
    r"합병|인수|분할|지분취득|주주총회|배당)",
    re.IGNORECASE,
)
_SEC_PATTERNS = re.compile(
    r"(SEC|8-K|10-Q|10-K|proxy|merger|acquisition|spinoff|buyback|dividend|"
    r"secondary offering|rights offering)",
    re.IGNORECASE,
)
_EARNINGS_PATTERNS = re.compile(
    r"(earnings|EPS|revenue|실적|분기|연간|어닝|매출|영업이익|순이익|가이던스|"
    r"guidance|beat|miss|outlook|FY|Q[1-4])",
    re.IGNORECASE,
)
_CLINICAL_PATTERNS = re.compile(
    r"(임상|clinical trial|Phase [1-3]|FDA|MFDS|식약처|IND|NDA|BLA|"
    r"approval|승인|허가|PDUFA|EMA|임상시험|치료제|신약|바이오시밀러)",
    re.IGNORECASE,
)
_POLICY_PATTERNS = re.compile(
    r"(정책|규제|완화|강화|금리|기준금리|연준|Fed|FOMC|국방|방위|예산|법안|법률|"
    r"tariff|관세|제재|sanctions|subsidy|보조금|인프라|반도체법|IRA|CHIPs)",
    re.IGNORECASE,
)
_ORDER_BACKLOG_PATTERNS = re.compile(
    r"(수주잔고|backlog|선박|LNG선|컨테이너선|방산|K2전차|K9자주포|전력기기|"
    r"변압기|CDMO|CMO|위탁생산|인도|납기|order book)",
    re.IGNORECASE,
)
_MACRO_PATTERNS = re.compile(
    r"(CPI|PCE|GDP|실업률|고용|인플레|deflation|연준|Fed|FOMC|금리|국채|VIX|"
    r"경기침체|recession|PMI|ISM|무역수지|경상수지|환율|dollar index)",
    re.IGNORECASE,
)
_RELATION_PATTERNS = re.compile(
    r"(read.?through|밸류체인|value chain|수혜|피해|연동|lead.?lag|선행|후행|"
    r"상관관계|공급망|supply chain|파급효과)",
    re.IGNORECASE,
)
_FLOW_PATTERNS = re.compile(
    r"(거래량 급증|수급|외국인 순매수|기관 순매도|프로그램 매매|테마|시세|모멘텀|"
    r"price action|technical|차트|이동평균|RSI|OBV|volume only|이유 불명|이유없|"
    r"unknown reason|no catalyst|no news)",
    re.IGNORECASE,
)


def classify_catalyst(
    text: str,
    source_type: str = "unknown",
    source_name: str = "",
) -> CatalystResult:
    """텍스트와 소스 타입으로 CatalystResult 분류.

    Args:
        text: 뉴스/공시 제목 + 본문 (500자 이하 권장)
        source_type: dart / sec / rss / telegram / unknown 등
        source_name: 소스 이름 (reuters, finnhub 등)

    Returns:
        CatalystResult
    """
    src_lower = (source_type + " " + source_name).lower()
    text_check = (text or "")[:1000]

    # ── 소스 기반 기본 신뢰도 ───────────────────────────────────────────────────
    base_conf: CatalystConfidence
    if any(s in src_lower for s in _HIGH_CONFIDENCE_SOURCES):
        base_conf = CatalystConfidence.HIGH
    elif any(s in src_lower for s in _MEDIUM_CONFIDENCE_SOURCES):
        base_conf = CatalystConfidence.MEDIUM
    else:
        base_conf = CatalystConfidence.LOW

    source_tags: list[str] = []
    if base_conf == CatalystConfidence.HIGH:
        source_tags.append(source_type or source_name)

    # ── 텍스트 패턴 분류 ────────────────────────────────────────────────────────
    if _DART_PATTERNS.search(text_check) and source_type in ("dart", "opendart"):
        return CatalystResult(
            catalyst_type=CatalystType.DART_CONTRACT,
            confidence=CatalystConfidence.HIGH,
            reason=f"DART 공시 패턴 ({source_type})",
            source_tags=["dart"],
        )

    if _SEC_PATTERNS.search(text_check) and source_type in ("sec", "sec_8k", "edgar"):
        return CatalystResult(
            catalyst_type=CatalystType.SEC_8K,
            confidence=CatalystConfidence.HIGH,
            reason=f"SEC 공시 패턴 ({source_type})",
            source_tags=["sec"],
        )

    if _ORDER_BACKLOG_PATTERNS.search(text_check):
        conf = CatalystConfidence.HIGH if base_conf == CatalystConfidence.HIGH else CatalystConfidence.MEDIUM
        return CatalystResult(
            catalyst_type=CatalystType.ORDER_BACKLOG,
            confidence=conf,
            reason="수주잔고/계약 패턴",
            source_tags=source_tags,
        )

    if _CLINICAL_PATTERNS.search(text_check):
        conf = CatalystConfidence.HIGH if base_conf == CatalystConfidence.HIGH else CatalystConfidence.MEDIUM
        return CatalystResult(
            catalyst_type=CatalystType.CLINICAL,
            confidence=conf,
            reason="임상/FDA 패턴",
            source_tags=source_tags,
        )

    if _EARNINGS_PATTERNS.search(text_check):
        return CatalystResult(
            catalyst_type=CatalystType.EARNINGS,
            confidence=base_conf,
            reason="실적/가이던스 패턴",
            source_tags=source_tags,
        )

    if _POLICY_PATTERNS.search(text_check):
        return CatalystResult(
            catalyst_type=CatalystType.POLICY,
            confidence=base_conf,
            reason="정책/규제 패턴",
            source_tags=source_tags,
        )

    if _MACRO_PATTERNS.search(text_check):
        return CatalystResult(
            catalyst_type=CatalystType.MACRO,
            confidence=base_conf,
            reason="매크로 지표 패턴",
            source_tags=source_tags,
        )

    if _DART_PATTERNS.search(text_check):
        return CatalystResult(
            catalyst_type=CatalystType.DART_CONTRACT,
            confidence=base_conf,
            reason="계약/공시 패턴",
            source_tags=source_tags,
        )

    if _SEC_PATTERNS.search(text_check):
        return CatalystResult(
            catalyst_type=CatalystType.SEC_8K,
            confidence=base_conf,
            reason="SEC 관련 패턴",
            source_tags=source_tags,
        )

    if _RELATION_PATTERNS.search(text_check):
        return CatalystResult(
            catalyst_type=CatalystType.RELATION_READTHROUGH,
            confidence=CatalystConfidence.LOW,
            reason="관계/수혜 패턴 (read-through)",
            source_tags=source_tags,
        )

    if _FLOW_PATTERNS.search(text_check) or base_conf == CatalystConfidence.LOW:
        return CatalystResult(
            catalyst_type=CatalystType.FLOW_ONLY,
            confidence=CatalystConfidence.LOW,
            reason="수급/차트 패턴 또는 저신뢰 소스",
            source_tags=[],
        )

    return CatalystResult(
        catalyst_type=CatalystType.UNKNOWN,
        confidence=CatalystConfidence.LOW,
        reason="분류 불가 — 이유 불명",
        source_tags=[],
    )


def classify_from_raw_item(item: dict) -> CatalystResult:
    """RawItem dict에서 직접 분류."""
    text = (item.get("title") or "") + " " + (item.get("text") or "")
    source_type = item.get("source_type") or "unknown"
    source_name = item.get("source_name") or ""
    return classify_catalyst(text, source_type=source_type, source_name=source_name)


def label_for_display(result: CatalystResult) -> str:
    """브리핑 출력용 짧은 레이블."""
    _LABELS = {
        CatalystType.DART_CONTRACT: "DART공시",
        CatalystType.SEC_8K: "SEC공시",
        CatalystType.EARNINGS: "실적",
        CatalystType.GUIDANCE: "가이던스",
        CatalystType.CLINICAL: "임상",
        CatalystType.FDA_MFDS: "FDA/식약처",
        CatalystType.POLICY: "정책",
        CatalystType.REGULATION: "규제",
        CatalystType.ORDER_BACKLOG: "수주",
        CatalystType.MACRO: "매크로",
        CatalystType.RELATION_READTHROUGH: "관계",
        CatalystType.FLOW_ONLY: "수급만",
        CatalystType.UNKNOWN: "이유불명",
    }
    base = _LABELS.get(result.catalyst_type, str(result.catalyst_type))
    conf_icon = {"HIGH": "🔴", "MEDIUM": "🟡", "LOW": "⚪"}.get(result.confidence.value, "")
    return f"{conf_icon}{base}"
