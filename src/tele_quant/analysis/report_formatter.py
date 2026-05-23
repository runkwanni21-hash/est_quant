"""Report Formatter — 기관식 스윙 리포트 텔레그램 포맷.

Telegram 4000자 제한 → 섹션별 chunk 가능.
금지 표현 없음. 확인 불가 데이터는 '확인 제한' 표기.
공개 정보 기반 리서치 보조. 투자 판단 책임은 사용자에게 있음.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tele_quant.analysis.report_models import (
        ChainCandidate,
        InstitutionalFlowSignal,
        InstitutionalInvestmentReport,
        TechnicalAccumulationSignal,
    )

_DISCLAIMER = "⚠ 공개 정보 기반 리서치 보조 — 투자 판단 책임은 사용자에게 있음"

_FORBIDDEN = [
    "매수 권장", "매도 권장", "확정 수익", "수익 보장",
    "기관 매집 확정", "세력 매집 확정", "수혜 확정", "피해 확정",
    "자동매매", "반드시 상승",
]


def _check_forbidden(text: str) -> list[str]:
    return [w for w in _FORBIDDEN if w in text]


def _fmt_pct(v: float | None, decimals: int = 1) -> str:
    if v is None:
        return "확인 제한"
    sign = "+" if v >= 0 else ""
    return f"{sign}{v:.{decimals}f}%"


def _fmt_price(v: float | None, is_kr: bool = False) -> str:
    if v is None:
        return "확인 제한"
    if is_kr:
        return f"{v:,.0f}원"
    return f"${v:,.2f}" if v < 1000 else f"${v:,.0f}"


# ── 섹션별 포맷 ───────────────────────────────────────────────────────────────


def _section_header(report: InstitutionalInvestmentReport) -> str:
    is_kr = report.market == "KR"
    price = _fmt_price(report.technical_signal.close, is_kr)
    ret_1d = _fmt_pct(report.technical_signal.ret_1d)
    lines = [
        f"📋 [기관식 스윙 리포트] {report.name}({report.symbol})",
        "━━━━━━━━━━━━━━━━━━━━━━",
        f"▶ {report.one_line_conclusion}",
        f"▶ 등급: {report.score.grade} ({report.score.total:.0f}/100점)",
        f"▶ 현재가: {price}  전일대비: {ret_1d}",
        "",
    ]
    return "\n".join(lines)


def _section_why_now(report: InstitutionalInvestmentReport) -> str:
    """섹션 1: 왜 지금 보는가."""
    lines = ["[1] 왜 지금 보는가"]
    ev = report.evidence_items
    if not ev:
        lines.append("• 최근 30일 내 공개자료 확인 제한")
    else:
        fresh = sorted(ev, key=lambda e: e.freshness_days or 99)
        for e in fresh[:4]:
            days = f"{e.freshness_days:.0f}일 전" if e.freshness_days is not None else ""
            conf_icon = "🔴" if e.confidence == "HIGH" else "🟡"
            lines.append(f"{conf_icon} [{e.source}] {days} {e.title[:80]}")
    lines.append("")
    return "\n".join(lines)


def _section_sector(report: InstitutionalInvestmentReport) -> str:
    """섹션 2: 섹터별 가치분석."""
    sa = report.sector_analysis
    lines = [f"[2] 섹터별 가치분석 — {sa.sector_label}"]
    for m in sa.primary_metrics[:3]:
        lines.append(f"• {m['name']}: {m['value']}")
    lines.append(f"• {sa.pe_comment}")
    for peer in sa.peer_comparison[:2]:
        lines.append(peer)
    if sa.key_watchpoints:
        lines.append(f"• 체크포인트: {sa.key_watchpoints[0]}")
    lines.append("")
    return "\n".join(lines)


def _section_consensus(report: InstitutionalInvestmentReport) -> str:
    """섹션 3: 최근 리포트/컨센서스."""
    c = report.consensus
    is_kr = report.market == "KR"
    lines = [f"[3] 리포트/컨센서스 ({c.report_count}건, {c.data_source})"]

    if c.target_mean is not None:
        lines.append(f"• 목표가 평균: {_fmt_price(c.target_mean, is_kr)}")
        if c.target_low and c.target_high:
            lines.append(f"  범위: {_fmt_price(c.target_low, is_kr)} ~ {_fmt_price(c.target_high, is_kr)}")
        if c.upside_pct is not None:
            lines.append(f"  상승여력: {_fmt_pct(c.upside_pct)} (추정, 확정 아님)")
    else:
        lines.append("• 목표가: 확인 제한")

    lines.append(f"• 의견: {c.opinion_label}")
    if c.recent_upgrade:
        lines.append(f"• 최근 30일 상향: {c.recent_upgrade}건")
    if c.recent_downgrade:
        lines.append(f"• 최근 30일 하향: {c.recent_downgrade}건")

    for t in c.bull_theses[:2]:
        lines.append(f"• Bull: {t[:60]}")
    for t in c.bear_theses[:2]:
        lines.append(f"• Bear: {t[:60]}")

    if c.note:
        lines.append(f"• ※ {c.note}")
    lines.append("")
    return "\n".join(lines)


def _section_technical_flow(report: InstitutionalInvestmentReport) -> str:
    """섹션 4: 기관/외국인 수급 + 기술적 매집."""
    tech = report.technical_signal
    flow = report.flow_signal
    lines = [f"[4] 수급·기술 — 수급집중 가능성 {flow.flow_level}"]

    rsi_str = f"{tech.rsi_1d:.0f}" if tech.rsi_1d is not None else "확인 제한"
    bb_str = f"{tech.bb_pct:.2f}" if tech.bb_pct is not None else "확인 제한"
    lines.append(f"• RSI 1D: {rsi_str}  OBV: {tech.obv_trend}  BB위치: {bb_str}")

    ma20_pos = "MA20 위" if tech.above_ma20 else ("MA20 아래" if tech.above_ma20 is False else "확인 제한")
    ma60_pos = "MA60 위" if tech.above_ma60 else ("MA60 아래" if tech.above_ma60 is False else "확인 제한")
    lines.append(f"• {ma20_pos} / {ma60_pos}")

    if tech.vol_ratio_20d is not None:
        lines.append(f"• 거래량 20일 대비: {tech.vol_ratio_20d:.1f}배")

    if tech.overheat:
        lines.append("• ⚠ 과열 추격주의")

    if flow.inst_net_5d is not None:
        sign = "+" if flow.inst_net_5d >= 0 else ""
        lines.append(f"• 기관 5일 순매수: {sign}{flow.inst_net_5d:.0f}억 [{flow.data_source}]")
    if flow.foreign_net_5d is not None:
        sign = "+" if flow.foreign_net_5d >= 0 else ""
        lines.append(f"• 외국인 5일 순매수: {sign}{flow.foreign_net_5d:.0f}억")

    for note in flow.flow_notes[:2]:
        lines.append(f"• {note}")

    lines.append(f"• 기술 점수: {tech.score:.0f}/100  수급 점수: {flow.flow_score:.0f}/100")
    if tech.overheat:
        lines.append("※ 수급집중 가능성 HIGH여도 과열 시 신뢰도 낮아짐")
    lines.append("")
    return "\n".join(lines)


def _section_chain(report: InstitutionalInvestmentReport) -> str:
    """섹션 5: 체인 후보."""
    lines = ["[5] 체인 후보"]

    def _fmt_cand(c: ChainCandidate, ctype: str) -> str:
        lag = f" [{c.expected_lag}]" if c.expected_lag else ""
        wo = " (관찰전용)" if c.watch_only else ""
        reason = f" — {c.connection_reason[:30]}" if c.connection_reason else ""
        return f"• [{ctype}]{wo} {c.name}({c.symbol}) 점수={c.chain_score:.0f}{lag}{reason}"

    if report.chain_beneficiaries:
        lines.append("▷ 수혜 가능성 후보 (확정 아님)")
        for c in report.chain_beneficiaries:
            lines.append(_fmt_cand(c, "수혜"))
    if report.chain_burdens:
        lines.append("▷ 상대적 부담 후보 (확정 아님)")
        for c in report.chain_burdens:
            lines.append(_fmt_cand(c, "부담"))
    if report.chain_peers:
        lines.append("▷ 피어 후보")
        for c in report.chain_peers:
            lines.append(_fmt_cand(c, "피어"))

    if not (report.chain_beneficiaries or report.chain_burdens or report.chain_peers):
        lines.append("• 체인 후보 확인 제한 (관계 데이터 없음)")

    lines.append("※ source 상승이 target 상승을 보장하지 않음 — 상관관계 ≠ 인과관계")
    lines.append("")
    return "\n".join(lines)


def _section_risk(report: InstitutionalInvestmentReport) -> str:
    """섹션 6: 리스크와 반론."""
    lines = ["[6] 리스크·반론"]
    for r in report.risk_factors[:4]:
        lines.append(f"• {r}")
    if report.missing_checks:
        lines.append("▷ 확인 필요:")
        for m in report.missing_checks[:3]:
            lines.append(f"  - {m}")
    lines.append("")
    return "\n".join(lines)


def _section_watch_criteria(report: InstitutionalInvestmentReport) -> str:
    """섹션 7: 관찰 기준."""
    lines = ["[7] 관찰 기준"]
    if report.entry_conditions:
        lines.append("▷ 좋은 조건:")
        for e in report.entry_conditions[:3]:
            lines.append(f"  ✓ {e}")
    if report.exit_conditions:
        lines.append("▷ 리스크 기준:")
        for e in report.exit_conditions[:3]:
            lines.append(f"  ✗ {e}")
    lines.append(f"▷ 기대 보상 구간: {report.reward_range}")
    if report.key_dates:
        lines.append("▷ 확인 날짜/이벤트:")
        for d in report.key_dates[:3]:
            lines.append(f"  • {d}")
    lines.append("")
    return "\n".join(lines)


def _section_score_detail(report: InstitutionalInvestmentReport) -> str:
    """점수 상세."""
    sc = report.score
    lines = [
        f"[점수 상세] {sc.grade} ({sc.total:.0f}/100)",
        f"증거품질: {sc.evidence_quality:.0f}/15  섹터적합: {sc.sector_valuation_fit:.0f}/15",
        f"기술셋업: {sc.technical_setup:.0f}/20  수급: {sc.institutional_flow:.0f}/15",
        f"체인: {sc.chain_read_through:.0f}/15  타이밍: {sc.timing_risk_reward:.0f}/10",
        f"리스크패널티: -{sc.risk_penalty:.0f}/10",
        "",
    ]
    return "\n".join(lines)


# ── 메인 포맷 함수 ────────────────────────────────────────────────────────────


def format_institutional_report(
    report: InstitutionalInvestmentReport,
    max_chars: int = 3900,
) -> list[str]:
    """기관식 리포트를 텔레그램 4000자 chunk 목록으로 변환.

    Returns:
        list[str] — 각 요소는 Telegram sendMessage 1회분 (4000자 이하).
    """
    header = _section_header(report)
    s1 = _section_why_now(report)
    s2 = _section_sector(report)
    s3 = _section_consensus(report)
    s4 = _section_technical_flow(report)
    s5 = _section_chain(report)
    s6 = _section_risk(report)
    s7 = _section_watch_criteria(report)
    sd = _section_score_detail(report)
    footer = _DISCLAIMER

    # 1차 메시지: header + s1 + s2 + s3
    first = header + s1 + s2 + s3
    # 2차 메시지: s4 + s5
    second = s4 + s5
    # 3차 메시지: s6 + s7 + score + footer
    third = s6 + s7 + sd + footer

    chunks: list[str] = []
    for raw in [first, second, third]:
        # 4000자 초과 시 재분할
        if len(raw) <= max_chars:
            chunks.append(raw)
        else:
            for i in range(0, len(raw), max_chars):
                chunks.append(raw[i : i + max_chars])

    # 금지 표현 검사 (개발 시 warn)
    import logging as _logging
    _log = _logging.getLogger(__name__)
    all_text = "\n".join(chunks)
    found = _check_forbidden(all_text)
    if found:
        _log.warning("[report_formatter] 금지 표현 감지: %s", found)

    return chunks


def format_report_summary(report: InstitutionalInvestmentReport) -> str:
    """단일 요약 문자열 (짧은 버전)."""
    sc = report.score
    return (
        f"[기관식 리포트] {report.name}({report.symbol})\n"
        f"등급: {sc.grade} ({sc.total:.0f}점)\n"
        f"{report.one_line_conclusion}\n"
        f"{_DISCLAIMER}"
    )


# ── /체인 포맷 ────────────────────────────────────────────────────────────────


def format_chain_candidates(
    symbol: str,
    name: str,
    beneficiaries: list[ChainCandidate],
    burdens: list[ChainCandidate],
    peers: list[ChainCandidate],
) -> str:
    """텔레그램 /체인 명령 출력 포맷."""
    lines = [f"🔗 체인 분석 — {name}({symbol})", ""]

    def _block(title: str, cands: list[ChainCandidate]) -> list[str]:
        if not cands:
            return []
        block = [f"▷ {title}"]
        for c in cands:
            lag = f" [{c.expected_lag}]" if c.expected_lag else ""
            wo = " ★관찰전용" if c.watch_only else ""
            score_str = f" (점수 {c.chain_score:.0f})"
            reason = f"\n  └ {c.connection_reason[:40]}" if c.connection_reason else ""
            rsi_str = f" RSI={c.target_rsi:.0f}" if c.target_rsi else ""
            ma_str = f" {c.target_ma_position}" if c.target_ma_position else ""
            block.append(
                f"• {c.name}({c.symbol}){wo}{score_str}{lag}{rsi_str}{ma_str}{reason}"
            )
        block.append("")
        return block

    lines.extend(_block("수혜 가능성 후보 (확정 아님)", beneficiaries))
    lines.extend(_block("상대적 부담 후보 (확정 아님)", burdens))
    lines.extend(_block("피어 후보", peers))

    if not (beneficiaries or burdens or peers):
        lines.append("• 체인 후보 확인 제한 (관계 데이터 없음)")

    lines.append("※ source 상승이 target 상승을 보장하지 않음")
    lines.append("※ LOW confidence 항목은 관찰전용 — 직접 확인 필요")
    lines.append("")
    lines.append(_DISCLAIMER)
    return "\n".join(lines)


# ── /기관수급 포맷 ─────────────────────────────────────────────────────────


def format_institutional_flow(
    symbol: str,
    name: str,
    flow: InstitutionalFlowSignal,
    technical: TechnicalAccumulationSignal,
) -> str:
    """텔레그램 /기관수급 명령 출력 포맷."""
    is_kr = symbol.endswith((".KS", ".KQ"))
    lines = [
        f"📊 수급집중 가능성 분석 — {name}({symbol})",
        "━━━━━━━━━━━━━━━━━━━━━━",
        f"▶ 수급집중 가능성: {flow.flow_level}  (점수 {flow.flow_score:.0f}/100)",
        "",
    ]

    # 기술 지표
    rsi = f"{technical.rsi_1d:.0f}" if technical.rsi_1d is not None else "확인 제한"
    bb = f"{technical.bb_pct:.2f}" if technical.bb_pct is not None else "확인 제한"
    vol = f"{technical.vol_ratio_20d:.1f}배" if technical.vol_ratio_20d is not None else "확인 제한"
    lines.append(f"• RSI 1D: {rsi}")
    lines.append(f"• 볼린저밴드 위치: {bb}  (수축: {'예' if technical.bb_squeeze else '아니오'})")
    lines.append(f"• OBV 추세: {technical.obv_trend}")
    lines.append(f"• 거래량 20일 평균 대비: {vol}")

    ma20 = "MA20 위" if technical.above_ma20 else ("MA20 아래" if technical.above_ma20 is False else "확인 제한")
    ma60 = "MA60 위" if technical.above_ma60 else ("MA60 아래" if technical.above_ma60 is False else "확인 제한")
    lines.append(f"• {ma20} / {ma60}")
    lines.append("")

    # 기관/외국인 수급 (KRX)
    if is_kr:
        inst_5 = f"{flow.inst_net_5d:+.0f}억" if flow.inst_net_5d is not None else "확인 제한"
        inst_20 = f"{flow.inst_net_20d:+.0f}억" if flow.inst_net_20d is not None else "확인 제한"
        fgn_5 = f"{flow.foreign_net_5d:+.0f}억" if flow.foreign_net_5d is not None else "확인 제한"
        lines.append(f"• 기관 5일 순매수: {inst_5} / 20일: {inst_20} [{flow.data_source}]")
        if flow.inst_consecutive_buy > 0:
            lines.append(f"• 기관 연속 순매수: {flow.inst_consecutive_buy}일")
        elif flow.inst_consecutive_sell > 0:
            lines.append(f"• 기관 연속 순매도: {flow.inst_consecutive_sell}일")
        lines.append(f"• 외국인 5일 순매수: {fgn_5}")
        if flow.foreign_consecutive_buy > 0:
            lines.append(f"• 외국인 연속 순매수: {flow.foreign_consecutive_buy}일")
        lines.append("")

    # proxy 신호
    lines.append("[ Proxy 신호 ]")
    if flow.price_obv_divergence:
        lines.append("✓ 가격 횡보 + OBV 상승 — 잠재적 매집 proxy")
    if flow.bb_squeeze_recovery:
        lines.append("✓ 볼린저밴드 수축 후 MA20 회복")
    if flow.obv_slope == "UP":
        lines.append("✓ OBV 상승 추세")

    for note in flow.flow_notes[:4]:
        lines.append(f"• {note}")

    if technical.overheat:
        lines.append("")
        lines.append("⚠ 과열 추격주의 — 수급집중 HIGH여도 추격 진입 리스크 있음")

    lines.append("")
    lines.append("※ '기관 매집 확정' 표현 금지. 공개 데이터 기반 proxy 추정값임.")
    lines.append(_DISCLAIMER)
    return "\n".join(lines)
