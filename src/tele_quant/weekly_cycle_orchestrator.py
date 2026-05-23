"""Weekly Cycle Orchestrator — 요일/시간대별 브리핑 정책 중앙 관리.

Slot:
  monday_open   — 월요일 07:00 KST, 보수적 LONG 모드
  weekday_4h    — 평일 4H 퀀터멘탈 관찰 브리핑
  weekend_issue — 주말 이슈/공시/정책 전용 (차트 추천 없음)
  sunday_review — 일요일 23:00 주간 성과 리뷰
  auto          — KST 시각 기준 자동 판정

공개 정보 기반 리서치 보조. 투자 판단 책임은 사용자에게 있음.
"매수 권장" / "매도 권장" / "확정 수익" 표현 금지.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tele_quant.db import Store
    from tele_quant.settings import Settings

log = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))

DISCLAIMER = (
    "⚠ 공개 정보 기반 리서치 보조 — 매수·매도 확정 아님. "
    "투자 판단 책임은 사용자에게 있음"
)


class WeeklyCycleSlot(StrEnum):
    MONDAY_OPEN = "monday_open"
    WEEKDAY_4H = "weekday_4h"
    WEEKEND_ISSUE = "weekend_issue"
    SUNDAY_REVIEW = "sunday_review"
    AUTO = "auto"


@dataclass
class CycleContext:
    slot: WeeklyCycleSlot
    kst_now: datetime
    market: str = "ALL"


def detect_slot(now: datetime | None = None) -> WeeklyCycleSlot:
    """KST 현재 시각 기준 slot 자동 판정.

    - Mon 06:00~08:00 KST → monday_open
    - Sun 23:00~01:00 KST → sunday_review
    - Sat/Sun → weekend_issue
    - Mon~Fri 그 외 → weekday_4h
    """
    kst = (now or datetime.now(KST)).astimezone(KST)
    wd = kst.weekday()  # 0=Mon, 6=Sun
    h = kst.hour

    if wd == 0 and 6 <= h < 8:
        return WeeklyCycleSlot.MONDAY_OPEN
    if wd == 6 and h == 23:
        return WeeklyCycleSlot.SUNDAY_REVIEW
    if wd in (5, 6):
        return WeeklyCycleSlot.WEEKEND_ISSUE
    return WeeklyCycleSlot.WEEKDAY_4H


# ── Monday Open ──────────────────────────────────────────────────────────────

def build_monday_open_briefing(
    store: Store,
    settings: Settings,
    market: str = "ALL",
) -> str:
    """월요일 오전 07:00 KST 브리핑.

    - 지난주 시황 요약
    - 금요일 급등/급락 종목
    - 주말 뉴스/공시
    - 포트폴리오 리스크 점검 (EXIT 관찰)
    - 신규 LONG은 매우 보수적 (WATCH_ONLY 수준)
    """
    from datetime import UTC
    utc_now_str = datetime.now(UTC).strftime("%m/%d %H:%M")
    parts: list[str] = []

    parts.append(f"📊 월요일 오전 퀀터멘탈 관찰 브리핑 — {utc_now_str} UTC")
    parts.append("⚠ 월요일 오전 보수 모드: 신규 LONG 관찰은 제한, 지난주 급등 종목은 차익실현/리스크 점검 우선")
    parts.append("")

    # ── 1. 지난주 시황 ──────────────────────────────────────────────────────
    parts.append("━━ 📅 지난주 시황 ━━")
    try:
        macro_section = _build_last_week_macro()
        parts.append(macro_section)
    except Exception as e:
        log.debug("[monday_open] macro fetch failed: %s", e)
        parts.append("(시황 데이터 수집 중)")
    parts.append("")

    # ── 2. 금요일 급등/급락 종목 ───────────────────────────────────────────
    parts.append("━━ ⚡ 주말 갭 리스크 — 금요일 급등/급락 종목 ━━")
    try:
        mover_section = _build_friday_movers(store, market)
        parts.append(mover_section)
    except Exception as e:
        log.debug("[monday_open] friday movers failed: %s", e)
        parts.append("(급등/급락 데이터 조회 중)")
    parts.append("")

    # ── 3. 주말 뉴스/공시/정책 ────────────────────────────────────────────
    parts.append("━━ 📰 주말 뉴스/공시/정책 변화 ━━")
    try:
        news_section = _build_weekend_news_summary(store)
        parts.append(news_section)
    except Exception as e:
        log.debug("[monday_open] weekend news failed: %s", e)
        parts.append("(주말 뉴스 수집 중)")
    parts.append("")

    # ── 4. 포트폴리오 리스크 점검 ─────────────────────────────────────────
    parts.append("━━ 💼 보유 포지션 리스크 점검 (EXIT 관찰) ━━")
    try:
        port_section = _build_portfolio_risk_check(store)
        parts.append(port_section)
    except Exception as e:
        log.debug("[monday_open] portfolio check failed: %s", e)
        parts.append("(포트폴리오 조회 중)")
    parts.append("")

    # ── 5. 주간 캘린더 ────────────────────────────────────────────────────
    parts.append("━━ 📅 이번 주 체크포인트 ━━")
    parts.append("📌 DART 공시 / SEC 8-K 모니터링")
    parts.append("📌 주요 실적 발표 일정 확인")
    parts.append("📌 연준 발언 / FOMC 일정 확인")
    parts.append("📌 신규 LONG 진입은 직접 이벤트 확인 후 신중하게 판단")
    parts.append("")

    # ── 면책 ──────────────────────────────────────────────────────────────
    parts.append("─" * 30)
    parts.append(DISCLAIMER)

    return "\n".join(parts)


def _build_last_week_macro() -> str:
    """지난 1주 매크로 지표 요약."""
    try:
        from tele_quant.macro_pulse import fetch_macro_snapshot
        snap = fetch_macro_snapshot()
        lines = []
        if snap.sp500_chg is not None:
            lines.append(f"S&P500 주간: {snap.sp500_chg:+.1f}%")
        if snap.kospi_chg is not None:
            lines.append(f"KOSPI: {snap.kospi_chg:+.1f}%")
        if snap.us10y is not None:
            chg = f"{snap.us10y_chg:+.1f}bp" if snap.us10y_chg else ""
            lines.append(f"10Y: {snap.us10y:.2f}% {chg}")
        if snap.usd_krw is not None:
            lines.append(f"USD/KRW: {snap.usd_krw:,.0f}")
        if snap.vix is not None:
            lines.append(f"VIX: {snap.vix:.1f}")
        if snap.wti is not None:
            lines.append(f"WTI: ${snap.wti:.1f}")
        regime = getattr(snap, "regime", "") or ""
        if regime:
            lines.append(f"레짐: {regime}")
        return "\n".join(lines) if lines else "매크로 데이터 없음"
    except Exception:
        return "(매크로 데이터 수집 실패)"


def _build_friday_movers(store: Store, market: str = "ALL") -> str:
    """금요일 급등/급락 종목 (mover_chain_history 또는 surge_events 기반)."""
    from tele_quant.models import utc_now
    since = utc_now() - timedelta(days=3)  # 금요일 포함 3일
    lines: list[str] = []
    try:
        with store.connect() as conn:
            # surge_events에서 최근 3일 급등 이벤트
            rows = conn.execute(
                """SELECT symbol, name, market, intraday_pct, catalyst_type, catalyst_ko
                   FROM surge_events
                   WHERE created_at>=? AND abs(intraday_pct)>=3
                   ORDER BY abs(intraday_pct) DESC LIMIT 10""",
                (since.isoformat(),),
            ).fetchall()
        if rows:
            for r in rows:
                pct = r["intraday_pct"]
                icon = "🚀" if pct > 0 else "📉"
                reason = r["catalyst_ko"] or r["catalyst_type"] or "이유 불명"
                lines.append(f"{icon} {r['name'] or r['symbol']}({r['symbol']}) {pct:+.1f}% — {reason}")
        else:
            lines.append("(최근 3일 급등/급락 이벤트 없음 또는 데이터 미수집)")
    except Exception as e:
        lines.append(f"(조회 실패: {e})")
    lines.append("→ 주말 갭 리스크 확인 — 월요일 오전 추격보다 방향 확인 후 판단")
    return "\n".join(lines)


def _build_weekend_news_summary(store: Store) -> str:
    """주말 뉴스/공시 요약 (raw_items 기반)."""
    from tele_quant.models import utc_now
    since = utc_now() - timedelta(hours=60)  # 금요일 장마감 이후
    try:
        with store.connect() as conn:
            rows = conn.execute(
                """SELECT title, source_type, source_name, published_at
                   FROM raw_items WHERE published_at>=?
                   ORDER BY published_at DESC LIMIT 10""",
                (since.isoformat(),),
            ).fetchall()
        if not rows:
            return "(주말 뉴스/공시 데이터 없음)"
        lines = []
        for r in rows:
            src = r["source_name"] or r["source_type"]
            lines.append(f"• [{src}] {(r['title'] or '')[:80]}")
        return "\n".join(lines[:8])
    except Exception as e:
        return f"(뉴스 조회 실패: {e})"


def _build_portfolio_risk_check(store: Store) -> str:
    """모의 포트폴리오 EXIT 관찰 체크."""
    try:
        with store.connect() as conn:
            rows = conn.execute(
                "SELECT symbol, name, side, entry_price, status FROM mock_portfolio_positions WHERE status='open' LIMIT 6"
            ).fetchall()
        if not rows:
            return "보유 포지션 없음"
        lines = []
        for r in rows:
            lines.append(f"• {r['name'] or r['symbol']}({r['symbol']}) {r['side']} — 관찰 기준가 {r['entry_price']:,.0f}")
        lines.append("→ 주간 +8% 이상 종목은 차익실현/리스크 점검 우선")
        return "\n".join(lines)
    except Exception as e:
        return f"(포트폴리오 조회 실패: {e})"


# ── Weekday 4H ───────────────────────────────────────────────────────────────

def build_weekday_4h_briefing(
    store: Store,
    settings: Settings,
    market: str = "ALL",
) -> str:
    """평일 4H 퀀터멘탈 관찰 브리핑.

    기존 run_4h_advisory를 호출해 표준 브리핑을 생성하고
    catalyst 분류와 advisory_recommendation_log 저장을 추가한다.
    """
    from tele_quant.advisor_4h import run_4h_advisory

    try:
        briefing = run_4h_advisory(market=market, store=store, settings=settings)
    except Exception as e:
        log.warning("[weekday_4h] advisory failed: %s", e)
        briefing = f"[브리핑 생성 실패: {e}]\n{DISCLAIMER}"

    return briefing


# ── Weekend Issue ─────────────────────────────────────────────────────────────

def build_weekend_issue_briefing(
    store: Store,
    settings: Settings,
) -> str:
    """주말 이슈/공시/정책 전용 브리핑. 차트 기반 LONG/SHORT 추천 없음."""
    from datetime import UTC
    utc_now_str = datetime.now(UTC).strftime("%m/%d %H:%M")
    parts: list[str] = []

    parts.append(f"📊 주말 이슈 브리핑 — {utc_now_str} UTC")
    parts.append("i 주말 브리핑: 공시/정책/이벤트 중심 — 차트 기반 LONG/SHORT 관찰은 월요일 장 시작 후 확인")
    parts.append("")

    # ── 매크로 ────────────────────────────────────────────────────────────
    parts.append("━━ 💹 매크로/리스크 레짐 ━━")
    try:
        parts.append(_build_last_week_macro())
    except Exception:
        parts.append("(매크로 데이터 수집 중)")
    parts.append("")

    # ── 공시/뉴스 ─────────────────────────────────────────────────────────
    parts.append("━━ 📰 주말 공시/뉴스/정책 ━━")
    try:
        parts.append(_build_weekend_news_summary(store))
    except Exception:
        parts.append("(뉴스 데이터 수집 중)")
    parts.append("")

    # ── 다음 주 캘린더 ────────────────────────────────────────────────────
    parts.append("━━ 📅 다음 주 이벤트 캘린더 ━━")
    try:
        cal_section = _build_next_week_calendar(store, settings)
        parts.append(cal_section)
    except Exception as e:
        log.debug("[weekend_issue] calendar failed: %s", e)
        parts.append("(캘린더 데이터 수집 중)")
    parts.append("")

    parts.append("━━ ⚠ 주말 관찰 정책 ━━")
    parts.append("• 주말 신규 LONG/SHORT 관찰 없음 — 차트 분석은 월요일 장 시작 후 확인")
    parts.append("• 공시/뉴스 모니터링 중 — 중요 이벤트 발생 시 월요일 오전 브리핑에 반영")
    parts.append("")

    parts.append("─" * 30)
    parts.append(DISCLAIMER)

    return "\n".join(parts)


def _build_next_week_calendar(store: Store, settings: Settings) -> str:
    """다음 주 이벤트 캘린더 (economic_calendar 기반)."""
    try:
        from tele_quant.economic_calendar import fetch_calendar_events
        events = fetch_calendar_events(settings, days_ahead=7)
        if not events:
            return "캘린더 이벤트 없음 (데이터 미수집)"
        lines = []
        for ev in events[:8]:
            date = (ev.get("date") or "")[:10]
            name = ev.get("name") or ev.get("event") or ""
            impact = ev.get("impact") or ev.get("importance") or ""
            lines.append(f"• {date} [{impact}] {name[:60]}")
        return "\n".join(lines)
    except Exception as e:
        return f"(캘린더 조회 실패: {e})"


# ── Sunday Review ─────────────────────────────────────────────────────────────

def build_sunday_weekly_review(
    store: Store,
    settings: Settings,
) -> str:
    """일요일 23:00 KST 주간 성과 리뷰.

    - 이번 주 시황
    - 주중 제시한 LONG/SHORT/EXIT 관찰 후보 결과
    - 잘 맞은 관계 / 실패한 관계
    - 다음 주 watchlist
    """
    from datetime import UTC
    kst_ref = datetime.now(KST)
    utc_now_str = datetime.now(UTC).strftime("%m/%d %H:%M")
    parts: list[str] = []

    parts.append(f"📊 주간 퀀터멘탈 성과 리뷰 — {utc_now_str} UTC")
    parts.append(f"기간: {(kst_ref - timedelta(days=7)).strftime('%m/%d')} ~ {kst_ref.strftime('%m/%d')} KST")
    parts.append("")

    # ── 1. 이번 주 시황 ──────────────────────────────────────────────────
    parts.append("━━ 📅 이번 주 시황 ━━")
    try:
        parts.append(_build_last_week_macro())
    except Exception:
        parts.append("(시황 데이터 수집 중)")
    parts.append("")

    # ── 2. 주간 cycle messages 요약 ──────────────────────────────────────
    parts.append("━━ 📋 이번 주 발행된 브리핑 ━━")
    try:
        from tele_quant.models import utc_now as _utc_now
        since_7d = _utc_now() - timedelta(days=7)
        cycle_msgs = store.recent_cycle_messages(since=since_7d, limit=30)
        if cycle_msgs:
            slot_counts: dict[str, int] = {}
            for m in cycle_msgs:
                slot_counts[m.get("slot", "?")] = slot_counts.get(m.get("slot", "?"), 0) + 1
            for slot, cnt in sorted(slot_counts.items()):
                parts.append(f"  {slot}: {cnt}건")
        else:
            parts.append("  (이번 주 브리핑 기록 없음)")
    except Exception as e:
        parts.append(f"  (브리핑 기록 조회 실패: {e})")
    parts.append("")

    # ── 3. LONG/SHORT/EXIT 관찰 후보 결과 ────────────────────────────────
    parts.append("━━ 🏆 이번 주 LONG 관찰 후보 결과 ━━")
    parts.append(_build_weekly_performance(store, side_filter="LONG_OBSERVE"))
    parts.append("")

    parts.append("━━ 📉 이번 주 SHORT 관찰 후보 결과 ━━")
    parts.append(_build_weekly_performance(store, side_filter="SHORT_OBSERVE"))
    parts.append("")

    parts.append("━━ 🔄 EXIT 관찰 후보 결과 ━━")
    parts.append(_build_weekly_performance(store, side_filter="EXIT_CHECK"))
    parts.append("")

    # ── 4. 관계 검증 ─────────────────────────────────────────────────────
    parts.append("━━ 🔗 관계 검증 결과 ━━")
    try:
        parts.append(_build_relation_review(store))
    except Exception as e:
        parts.append(f"(관계 검증 실패: {e})")
    parts.append("")

    # ── 5. 다음 주 watchlist ──────────────────────────────────────────────
    parts.append("━━ 📌 다음 주 확인할 5가지 ━━")
    parts.append(_build_next_week_watchlist(store))
    parts.append("")

    # ── 6. 월요일 오전 정책 안내 ─────────────────────────────────────────
    parts.append("━━ ⚠ 월요일 오전 정책 ━━")
    parts.append("• 신규 LONG 관찰은 직접 이벤트 확인 필수 — 보수적 접근")
    parts.append("• 주말 갭 리스크 — 금요일 급등 종목 월요일 추격주의")
    parts.append("• 무효화/리스크 기준 도달 종목 우선 EXIT 관찰")
    parts.append("")

    parts.append("─" * 30)
    parts.append(DISCLAIMER)

    return "\n".join(parts)


def _build_weekly_performance(store: Store, side_filter: str) -> str:
    """advisory_recommendation_log 기반 주간 성과 계산."""
    from tele_quant.models import utc_now
    since_7d = utc_now() - timedelta(days=7)
    try:
        recs = store.recent_recommendation_log(since=since_7d, side=side_filter, limit=50)
    except Exception:
        return "(데이터 없음)"

    if not recs:
        return f"이번 주 {side_filter} 관찰 없음"

    lines: list[str] = []
    hit_count = 0
    total_return = 0.0
    reviewed = 0

    for r in recs:
        sym = r.get("symbol", "")
        name = r.get("name", "") or sym
        score = r.get("score") or 0
        ret = r.get("review_return_pct")
        status = r.get("status", "OPEN")

        if ret is not None:
            reviewed += 1
            total_return += ret
            icon = "✅" if (side_filter == "LONG_OBSERVE" and ret > 0) or (side_filter == "SHORT_OBSERVE" and ret < 0) else "❌"
            if icon == "✅":
                hit_count += 1
            lines.append(f"  {icon} {name}({sym}) {ret:+.1f}% [{status}]")
        else:
            lines.append(f"  ⏳ {name}({sym}) {score:.0f}점 [OPEN — 평가 대기]")

    summary_parts = [f"총 {len(recs)}개 관찰"]
    if reviewed > 0:
        win_rate = hit_count / reviewed * 100
        avg_ret = total_return / reviewed
        summary_parts.append(f"검토됨 {reviewed}개 | 적중 {win_rate:.0f}% | 평균 {avg_ret:+.1f}%")
    lines.insert(0, " / ".join(summary_parts))
    lines.append("⚠ 가상 등락 — 실제 매매 수익·손실 아님. 리서치 시스템 사후 검증.")

    return "\n".join(lines)


def _build_relation_review(store: Store) -> str:
    """relation_follow_events 기반 관계 hit/miss 요약."""
    from tele_quant.models import utc_now
    since_7d = utc_now() - timedelta(days=7)
    try:
        with store.connect() as conn:
            rows = conn.execute(
                """SELECT source_symbol, target_symbol, expected_direction,
                          hit_1d, hit_3d, target_return_1d
                   FROM relation_follow_events
                   WHERE created_at>=? ORDER BY created_at DESC LIMIT 30""",
                (since_7d.isoformat(),),
            ).fetchall()
    except Exception:
        return "(relation 데이터 없음)"

    if not rows:
        return "이번 주 relation follow 이벤트 없음"

    hit_1d = sum(1 for r in rows if r["hit_1d"] == 1)
    total = len(rows)
    lines = [f"relation 검증: {total}개 | 1D 적중 {hit_1d}/{total} ({hit_1d/total*100:.0f}%)"]
    for r in rows[:5]:
        ret = r["target_return_1d"]
        ret_str = f"{ret:+.1f}%" if ret is not None else "평가중"
        hit = "✅" if r["hit_1d"] == 1 else ("❌" if r["hit_1d"] == 0 else "⏳")
        lines.append(f"  {hit} {r['source_symbol']}→{r['target_symbol']} {ret_str}")

    return "\n".join(lines)


def _build_next_week_watchlist(store: Store) -> str:
    """다음 주 주요 체크포인트."""
    lines = [
        "1. DART/SEC 공시 — 수주·계약·임상·실적 발표",
        "2. 연준 발언 / FOMC 일정",
        "3. 한국 금리/수출 데이터",
        "4. 주요 실적 발표 (어닝시즌 확인)",
        "5. 이번 주 급등 source → 다음 주 relation target 반응 추적",
    ]
    return "\n".join(f"{'📌' if i < 5 else '•'} {line}" for i, line in enumerate(lines))


# ── 메인 실행 ─────────────────────────────────────────────────────────────────

def run_cycle_briefing(
    slot: WeeklyCycleSlot | str,
    store: Store,
    settings: Settings,
    market: str = "ALL",
    now: datetime | None = None,
    save_to_db: bool = True,
) -> str:
    """slot에 맞는 브리핑 생성.

    Args:
        slot: WeeklyCycleSlot 또는 문자열
        store: SQLite Store
        settings: Settings
        market: KR | US | ALL
        now: 현재 시각 (None이면 실시간)
        save_to_db: advisory_cycle_messages 저장 여부

    Returns:
        브리핑 텍스트
    """
    if isinstance(slot, str):
        slot = WeeklyCycleSlot(slot) if slot in WeeklyCycleSlot._value2member_map_ else WeeklyCycleSlot.AUTO

    if slot == WeeklyCycleSlot.AUTO:
        slot = detect_slot(now)
        log.info("[cycle] auto-detected slot=%s", slot.value)

    log.info("[cycle] run slot=%s market=%s", slot.value, market)

    if slot == WeeklyCycleSlot.MONDAY_OPEN:
        report = build_monday_open_briefing(store, settings, market=market)
    elif slot == WeeklyCycleSlot.WEEKDAY_4H:
        report = build_weekday_4h_briefing(store, settings, market=market)
    elif slot == WeeklyCycleSlot.WEEKEND_ISSUE:
        report = build_weekend_issue_briefing(store, settings)
    elif slot == WeeklyCycleSlot.SUNDAY_REVIEW:
        report = build_sunday_weekly_review(store, settings)
    else:
        report = build_weekday_4h_briefing(store, settings, market=market)

    if save_to_db:
        try:
            store.save_cycle_message(
                slot=slot.value,
                body=report,
                market=market,
                title=f"{slot.value} {market}",
                sent=False,
            )
        except Exception as e:
            log.debug("[cycle] save_cycle_message failed: %s", e)

    return report
