"""기관식 스윙 리포트 데이터 모델.

공개 정보 기반 리서치 보조. 투자 판단 책임은 사용자에게 있음.
금지 표현: 매수 권장 / 매도 권장 / 확정 수익 / 기관 매집 확정 / 수혜 확정.
허용 표현: 우선관찰 / 관찰 후보 / 보류 / 리스크 기준 / 기대 보상 구간 / 수급집중 가능성.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# ── 증거 / 뉴스 ───────────────────────────────────────────────────────────────


@dataclass
class ReportEvidence:
    """단일 증거 항목 (뉴스, 공시, 리포트, 이슈 등)."""

    title: str
    source: str = ""                 # 출처 (Naver, DART, SEC, RSS, yfinance 등)
    published_at: str = ""           # ISO 8601 KST/UTC
    polarity: str = "NEUTRAL"        # POSITIVE / NEGATIVE / NEUTRAL
    confidence: str = "MEDIUM"       # HIGH / MEDIUM / LOW
    freshness_days: float | None = None   # 현재로부터 경과 일수
    url: str = ""
    summary: str = ""


# ── 애널리스트 컨센서스 ───────────────────────────────────────────────────────


@dataclass
class AnalystConsensus:
    """증권사 리포트·애널리스트 컨센서스 요약."""

    report_count: int = 0
    target_mean: float | None = None       # 평균 목표가
    target_median: float | None = None     # 중앙값 목표가
    target_low: float | None = None
    target_high: float | None = None
    current_price: float | None = None
    upside_pct: float | None = None        # 현재가 대비 % (지어내기 금지)

    # 투자의견 분포 (normalize: BUY/HOLD/SELL)
    buy_count: int = 0
    hold_count: int = 0
    sell_count: int = 0
    opinion_label: str = "확인 제한"       # BUY 우세 / HOLD 우세 / SELL 우세 / 혼재

    bull_theses: list[str] = field(default_factory=list)   # 공통 강세 논리 top 3
    bear_theses: list[str] = field(default_factory=list)   # 공통 약세 논리 top 3

    recent_upgrade: int = 0    # 최근 30일 상향
    recent_downgrade: int = 0  # 최근 30일 하향

    data_source: str = "yfinance"
    note: str = ""             # "확인 제한" 등


# ── 기술적 매집 신호 ──────────────────────────────────────────────────────────


@dataclass
class TechnicalAccumulationSignal:
    """기술적 지표 기반 매집/분산 신호."""

    # 원시 지표
    rsi_1d: float | None = None
    rsi_4h: float | None = None
    bb_pct: float | None = None        # 볼린저밴드 위치 0~1
    bb_width: float | None = None      # 밴드 폭 / 중심선
    bb_squeeze: bool = False
    obv_trend: str = ""                # UP / DOWN / FLAT
    obv_divergence: bool = False       # OBV 상승 + 가격 횡보 = 매집 신호
    ma20: float | None = None
    ma60: float | None = None
    ma120: float | None = None
    close: float | None = None
    above_ma20: bool | None = None
    above_ma60: bool | None = None
    vol_ratio_20d: float | None = None  # 거래량 / 20일 평균
    turnover_change_pct: float | None = None  # 거래대금 증가율 %

    # 수익률
    ret_1d: float | None = None
    ret_3d: float | None = None
    ret_5d: float | None = None
    ret_10d: float | None = None
    ret_20d: float | None = None

    # 52주 위치
    w52_high: float | None = None
    w52_low: float | None = None
    w52_position_pct: float | None = None  # 0~100%

    # 종합 점수 및 레이블
    score: float = 0.0         # 0~100
    label: str = ""            # 눌림 후 재상승 / 과열 추격주의 / 수급집중 가능성 / 기준 미달
    patterns: list[str] = field(default_factory=list)  # 감지된 패턴 목록
    overheat: bool = False     # 과열 추격주의 여부


# ── 기관/외국인 수급 ─────────────────────────────────────────────────────────


@dataclass
class InstitutionalFlowSignal:
    """기관/외국인 수급 신호.

    '기관 매집 확정' 금지. '수급집중 가능성 HIGH/MEDIUM/LOW'로 표현.
    """

    # KRX 기관/외국인 (pykrx, 없으면 proxy)
    inst_net_5d: float | None = None    # 기관 5일 순매수 (억원)
    inst_net_20d: float | None = None
    foreign_net_5d: float | None = None
    foreign_net_20d: float | None = None
    inst_consecutive_buy: int = 0       # 기관 연속 순매수 일수
    inst_consecutive_sell: int = 0
    foreign_consecutive_buy: int = 0

    # proxy 지표 (KRX 없을 때)
    obv_slope: str = ""        # UP / DOWN / FLAT
    price_obv_divergence: bool = False  # 가격 횡보 + OBV 상승
    bb_squeeze_recovery: bool = False   # BB 수축 후 MA20 회복

    # 종합
    flow_level: str = "MEDIUM"   # HIGH / MEDIUM / LOW
    flow_score: float = 0.0      # 0~100
    flow_notes: list[str] = field(default_factory=list)

    data_source: str = "proxy"   # krx / yfinance / proxy


# ── 체인 후보 ─────────────────────────────────────────────────────────────────


@dataclass
class ChainCandidate:
    """관계 체인 후보 종목 (수혜 가능성 / 상대적 부담 / 피어 / 고객사 / 공급사).

    '수혜 확정' / '피해 확정' 금지.
    LOW confidence는 관찰전용 표시.
    """

    symbol: str
    name: str = ""
    relation_type: str = ""    # BENEFICIARY / VICTIM / PEER / CUSTOMER / SUPPLIER
    direction: str = ""        # UP_LEADS_UP / UP_LEADS_DOWN 등
    confidence: str = "MEDIUM"  # HIGH / MEDIUM / LOW
    expected_lag: str = ""     # "1d", "3d", "1w" 등
    connection_reason: str = ""  # 왜 연결되는가

    # 체인 점수 구성 요소
    relation_confidence_score: float = 0.0   # 관계 신뢰도 (0~100)
    evidence_quality_score: float = 0.0      # 증거 품질 (0~100)
    source_event_score: float = 0.0          # 소스 이벤트 질 (0~100)
    target_technical_score: float = 0.0      # 타깃 기술적 준비도 (0~100)
    target_flow_score: float = 0.0           # 타깃 수급 (0~100)
    sector_momentum_score: float = 0.0       # 섹터 모멘텀 (0~100)
    overheat_penalty: float = 0.0            # 과열 패널티

    chain_score: float = 0.0   # 최종 체인 점수 (0~100)

    # 타깃 현재 기술 위치 (간략)
    target_rsi: float | None = None
    target_ma_position: str = ""   # 위 / 아래 / 교차

    watch_only: bool = False   # LOW confidence → 관찰전용


# ── 섹터별 가치분석 ──────────────────────────────────────────────────────────


@dataclass
class SectorSpecificAnalysis:
    """섹터별 특화 가치분석 결과."""

    sector_id: str = ""
    sector_label: str = ""

    primary_metrics: list[dict[str, Any]] = field(default_factory=list)
    # [{"name": "HBM ASP", "value": "확인 제한", "signal": "중립"}]

    secondary_metrics: list[dict[str, Any]] = field(default_factory=list)

    pe_note: str = ""
    normal_pe_range: tuple[float, float] | None = None
    current_pe: float | None = None
    pe_comment: str = ""       # PER이 해당 섹터 기준 내/외

    peer_comparison: list[str] = field(default_factory=list)  # 동종업계 비교 1줄 요약

    sector_valuation_score: float = 50.0   # 0~100
    key_watchpoints: list[str] = field(default_factory=list)


# ── 스윙 리포트 점수 ─────────────────────────────────────────────────────────


@dataclass
class SwingReportScore:
    """1D~1M 스윙 관점 종합 점수 (100점).

    80+: 우선관찰 A  /  68~79: 관찰 B  /  55~67: 조건부 관찰 C  /  <55: 보류
    """

    evidence_quality: float = 0.0          # 뉴스/공시/촉매 품질 15점
    sector_valuation_fit: float = 0.0      # 섹터별 가치분석 적합도 15점
    technical_setup: float = 0.0           # 기술적 셋업 20점
    institutional_flow: float = 0.0        # 기관/외국인 수급 15점
    chain_read_through: float = 0.0        # 체인 파급효과 15점
    timing_risk_reward: float = 0.0        # 타이밍/위험보상 10점
    risk_penalty: float = 0.0             # 리스크/모순 패널티 -10점 한도

    total: float = 0.0
    grade: str = "보류"          # 우선관찰 A / 관찰 B / 조건부 관찰 C / 보류
    grade_en: str = "HOLD"       # A / B / C / D

    contradictions: list[str] = field(default_factory=list)   # 감지된 모순
    missing_data: list[str] = field(default_factory=list)     # 부족한 데이터


# ── 최종 기관식 스윙 리포트 ──────────────────────────────────────────────────


@dataclass
class InstitutionalInvestmentReport:
    """기관식 스윙 리포트 — 1D~1M 보유 관점.

    금지 표현 없음. 확인 불가 데이터는 '확인 제한'으로 표기.
    """

    symbol: str
    market: str
    name: str = ""

    # 핵심 요약
    one_line_conclusion: str = ""
    score: SwingReportScore = field(default_factory=SwingReportScore)

    # 분석 섹션
    evidence_items: list[ReportEvidence] = field(default_factory=list)
    consensus: AnalystConsensus = field(default_factory=AnalystConsensus)
    sector_analysis: SectorSpecificAnalysis = field(default_factory=SectorSpecificAnalysis)
    technical_signal: TechnicalAccumulationSignal = field(
        default_factory=TechnicalAccumulationSignal
    )
    flow_signal: InstitutionalFlowSignal = field(default_factory=InstitutionalFlowSignal)

    # 체인 후보 (분류별)
    chain_beneficiaries: list[ChainCandidate] = field(default_factory=list)
    chain_burdens: list[ChainCandidate] = field(default_factory=list)
    chain_peers: list[ChainCandidate] = field(default_factory=list)

    # 리스크/반론
    risk_factors: list[str] = field(default_factory=list)
    missing_checks: list[str] = field(default_factory=list)

    # 관찰 기준
    entry_conditions: list[str] = field(default_factory=list)  # 좋은 조건
    exit_conditions: list[str] = field(default_factory=list)   # 리스크 기준
    reward_range: str = ""        # 기대 보상 구간 (추정, 확정 아님)
    key_dates: list[str] = field(default_factory=list)         # 확인할 날짜/이벤트

    # 메타
    generated_at: str = ""
    deep_mode: bool = False
    error: str = ""
