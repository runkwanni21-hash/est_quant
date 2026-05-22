"""Tests for calendar_score_policy — Monday LONG strict / Friday EXIT check."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from tele_quant.calendar_score_policy import (
    CalendarMode,
    CalendarScorePolicy,
    apply_policy_to_score,
    format_policy_note,
    get_current_policy,
)

_KST = timezone(timedelta(hours=9))


def _kst(weekday: int, hour: int) -> datetime:
    """Create a KST datetime for testing. weekday: 0=Mon, 4=Fri."""
    base = datetime(2026, 5, 18, hour, 0, tzinfo=_KST)  # 2026-05-18 = Monday
    return base + timedelta(days=weekday)


# ── get_current_policy ────────────────────────────────────────────────────────


def test_monday_morning_returns_strict_mode():
    now = _kst(0, 9)  # Monday 09:00 KST
    adj = get_current_policy(now=now)
    assert adj.mode == CalendarMode.MONDAY_LONG_STRICT
    assert adj.active is True
    assert adj.long_penalty > 0


def test_monday_before_start_returns_normal():
    now = _kst(0, 5)  # Monday 05:00 KST (before 06:00)
    adj = get_current_policy(now=now)
    assert adj.mode == CalendarMode.NORMAL
    assert adj.active is False


def test_monday_after_end_returns_normal():
    now = _kst(0, 13)  # Monday 13:00 KST (after 12:00)
    adj = get_current_policy(now=now)
    assert adj.mode == CalendarMode.NORMAL


def test_friday_evening_returns_exit_mode():
    now = _kst(4, 16)  # Friday 16:00 KST
    adj = get_current_policy(now=now)
    assert adj.mode == CalendarMode.FRIDAY_EXIT_STRICT
    assert adj.active is True
    assert adj.exit_boost > 0


def test_friday_morning_returns_normal():
    now = _kst(4, 10)  # Friday 10:00 KST (before 14:00)
    adj = get_current_policy(now=now)
    assert adj.mode == CalendarMode.NORMAL


def test_wednesday_returns_normal():
    now = _kst(2, 10)  # Wednesday 10:00 KST
    adj = get_current_policy(now=now)
    assert adj.mode == CalendarMode.NORMAL
    assert adj.active is False


def test_monday_strict_requires_direct_evidence():
    now = _kst(0, 9)
    adj = get_current_policy(now=now)
    assert adj.require_direct_evidence is True


def test_monday_policy_has_min_score():
    now = _kst(0, 9)
    adj = get_current_policy(now=now)
    assert adj.min_score_for_action >= 75.0


def test_friday_policy_has_profit_target():
    now = _kst(4, 16)
    adj = get_current_policy(now=now)
    assert adj.profit_target_pct is not None
    assert adj.profit_target_pct > 0


def test_custom_policy_disabled():
    policy = CalendarScorePolicy(monday_long_strict_enabled=False, friday_exit_strict_enabled=False)
    now = _kst(0, 9)
    adj = get_current_policy(now=now, policy=policy)
    assert adj.mode == CalendarMode.NORMAL


# ── apply_policy_to_score ─────────────────────────────────────────────────────


def test_monday_long_penalty_applied():
    now = _kst(0, 9)
    score, note = apply_policy_to_score(80.0, "LONG", now=now)
    assert score < 80.0
    assert "월요일" in note


def test_monday_short_no_penalty():
    now = _kst(0, 9)
    score, _ = apply_policy_to_score(80.0, "SHORT", now=now)
    assert score == 80.0


def test_monday_gap_chase_extra_penalty():
    now = _kst(0, 9)
    score, note = apply_policy_to_score(80.0, "LONG", price_change_1d=10.0, now=now)
    assert score <= 72.0
    assert "갭" in note


def test_monday_overheat_rsi_extra_penalty():
    now = _kst(0, 9)
    score, note = apply_policy_to_score(80.0, "LONG", rsi_4h=75.0, now=now)
    assert score <= 72.0
    assert "RSI" in note


def test_friday_weekly_winner_penalty():
    now = _kst(4, 16)
    score, note = apply_policy_to_score(80.0, "LONG", price_change_1w=10.0, now=now)
    assert score < 80.0
    assert "차익실현" in note


def test_friday_rsi_overheat_penalty():
    now = _kst(4, 16)
    score, _ = apply_policy_to_score(80.0, "LONG", rsi_4h=75.0, price_change_1w=10.0, now=now)
    assert score <= 69.0


def test_normal_mode_no_adjustment():
    now = _kst(2, 10)
    score, note = apply_policy_to_score(80.0, "LONG", now=now)
    assert score == 80.0
    assert note == ""


def test_score_never_negative():
    now = _kst(0, 9)
    score, _ = apply_policy_to_score(5.0, "LONG", price_change_1d=15.0, rsi_4h=80.0, now=now)
    assert score >= 0.0


# ── format_policy_note ────────────────────────────────────────────────────────


def test_monday_note_no_forbidden_words():
    now = _kst(0, 9)
    note = format_policy_note(now=now)
    forbidden = ["매수 권장", "매도 권장", "확정 수익", "자동매매"]
    for word in forbidden:
        assert word not in note


def test_friday_note_no_forbidden_words():
    now = _kst(4, 16)
    note = format_policy_note(now=now)
    forbidden = ["매수 권장", "매도 추천", "확정 수익", "자동매매"]
    for word in forbidden:
        assert word not in note, f"forbidden: '{word}' in note"


def test_normal_mode_empty_note():
    now = _kst(2, 10)
    assert format_policy_note(now=now) == ""


def test_friday_note_uses_allowed_terms():
    now = _kst(4, 16)
    note = format_policy_note(now=now)
    assert "차익실현" in note or "리스크 점검" in note


def test_monday_note_uses_allowed_terms():
    now = _kst(0, 9)
    note = format_policy_note(now=now)
    assert "엄격" in note or "보수적" in note
