from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from tele_quant.weekly_cycle_orchestrator import (
    WeeklyCycleSlot,
    detect_slot,
    run_cycle_briefing,
)

KST = timezone(timedelta(hours=9))


# ── detect_slot ───────────────────────────────────────────────────────────────

def _kst(year, month, day, hour, minute=0):
    return datetime(year, month, day, hour, minute, tzinfo=KST)


def test_monday_07_is_monday_open():
    # 2026-05-18 월요일 07:30 KST
    dt = _kst(2026, 5, 18, 7, 30)
    assert detect_slot(dt) == WeeklyCycleSlot.MONDAY_OPEN


def test_monday_11_is_weekday_4h():
    dt = _kst(2026, 5, 18, 11, 0)
    assert detect_slot(dt) == WeeklyCycleSlot.WEEKDAY_4H


def test_tuesday_07_is_weekday_4h():
    dt = _kst(2026, 5, 19, 7, 0)
    assert detect_slot(dt) == WeeklyCycleSlot.WEEKDAY_4H


def test_saturday_11_is_weekend_issue():
    # 2026-05-23 토요일
    dt = _kst(2026, 5, 23, 11, 0)
    assert detect_slot(dt) == WeeklyCycleSlot.WEEKEND_ISSUE


def test_sunday_15_is_weekend_issue():
    # 2026-05-24 일요일 15시
    dt = _kst(2026, 5, 24, 15, 0)
    assert detect_slot(dt) == WeeklyCycleSlot.WEEKEND_ISSUE


def test_sunday_23_is_sunday_review():
    # 2026-05-24 일요일 23시
    dt = _kst(2026, 5, 24, 23, 0)
    assert detect_slot(dt) == WeeklyCycleSlot.SUNDAY_REVIEW


def test_friday_15_is_weekday_4h():
    # 2026-05-22 금요일 15시
    dt = _kst(2026, 5, 22, 15, 0)
    assert detect_slot(dt) == WeeklyCycleSlot.WEEKDAY_4H


# ── run_cycle_briefing ────────────────────────────────────────────────────────

def _make_store():
    store = MagicMock()
    store.connect.return_value.__enter__ = MagicMock(
        return_value=MagicMock(execute=MagicMock(return_value=MagicMock(fetchall=MagicMock(return_value=[]))))
    )
    store.connect.return_value.__exit__ = MagicMock(return_value=False)
    store.recent_cycle_messages.return_value = []
    store.recent_recommendation_log.return_value = []
    store.save_cycle_message.return_value = True
    return store


def _make_settings():
    s = MagicMock()
    s.sqlite_path = "/tmp/test.sqlite"
    s.advisory_only_mode = True
    s.advisory_max_longs = 3
    return s


@patch("tele_quant.macro_pulse.fetch_macro_snapshot")
def test_monday_open_contains_key_phrases(mock_macro):
    mock_macro.side_effect = Exception("skip")
    store = _make_store()
    settings = _make_settings()
    result = run_cycle_briefing(
        WeeklyCycleSlot.MONDAY_OPEN, store, settings, save_to_db=False
    )
    assert "월요일" in result
    assert "보수 모드" in result
    assert "퀀터멘탈 관찰 브리핑" in result
    assert "매수·매도 확정 아님" in result


def test_monday_open_no_buy_recommend():
    store = _make_store()
    settings = _make_settings()
    with patch("tele_quant.macro_pulse.fetch_macro_snapshot", side_effect=Exception("skip")):
        result = run_cycle_briefing(WeeklyCycleSlot.MONDAY_OPEN, store, settings, save_to_db=False)
    assert "매수 권장" not in result
    assert "매도 권장" not in result
    assert "확정 수익" not in result


@patch("tele_quant.advisor_4h.run_4h_advisory")
def test_weekday_4h_delegates_to_advisory(mock_advisory):
    mock_advisory.return_value = "4H advisory mock output — 공개 정보 기반 리서치 보조 — 매수·매도 확정 아님."
    store = _make_store()
    settings = _make_settings()
    result = run_cycle_briefing(WeeklyCycleSlot.WEEKDAY_4H, store, settings, save_to_db=False)
    assert "advisory mock output" in result
    mock_advisory.assert_called_once()


@patch("tele_quant.macro_pulse.fetch_macro_snapshot")
def test_weekend_issue_no_long_short_recommendation(mock_macro):
    mock_macro.side_effect = Exception("skip")
    store = _make_store()
    settings = _make_settings()
    result = run_cycle_briefing(WeeklyCycleSlot.WEEKEND_ISSUE, store, settings, save_to_db=False)
    assert "주말 브리핑" in result
    assert "LONG 관찰" not in result or "관찰은 월요일" in result
    assert "SHORT 관찰" not in result or "관찰은 월요일" in result
    assert "매수·매도 확정 아님" in result


@patch("tele_quant.macro_pulse.fetch_macro_snapshot")
def test_sunday_review_contains_review_sections(mock_macro):
    mock_macro.side_effect = Exception("skip")
    store = _make_store()
    settings = _make_settings()
    result = run_cycle_briefing(WeeklyCycleSlot.SUNDAY_REVIEW, store, settings, save_to_db=False)
    assert "주간" in result
    assert "성과 리뷰" in result or "리뷰" in result
    assert "매수·매도 확정 아님" in result


def test_auto_slot_resolves():
    store = _make_store()
    settings = _make_settings()
    # 월요일 오전 07:30이면 monday-open
    mon_morning = _kst(2026, 5, 18, 7, 30)
    with (
        patch("tele_quant.weekly_cycle_orchestrator.datetime") as mock_dt,
        patch("tele_quant.macro_pulse.fetch_macro_snapshot", side_effect=Exception("skip")),
    ):
        mock_dt.now.return_value = mon_morning
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        result = run_cycle_briefing(
            WeeklyCycleSlot.AUTO, store, settings, now=mon_morning, save_to_db=False
        )
    assert "퀀터멘탈 관찰 브리핑" in result


# ── 금지 표현 검증 ─────────────────────────────────────────────────────────────

FORBIDDEN = [
    "매수 권장", "매도 권장", "확정 수익", "수익 보장",
    "반드시 상승", "자동매매", "실계좌 주문",
    "세력 매집 확정", "기관 매집 확정",
]


@pytest.mark.parametrize("slot", [
    WeeklyCycleSlot.MONDAY_OPEN,
    WeeklyCycleSlot.WEEKEND_ISSUE,
    WeeklyCycleSlot.SUNDAY_REVIEW,
])
@patch("tele_quant.macro_pulse.fetch_macro_snapshot", side_effect=Exception("skip"))
def test_no_forbidden_expressions(mock_macro, slot):
    store = _make_store()
    settings = _make_settings()
    result = run_cycle_briefing(slot, store, settings, save_to_db=False)
    for phrase in FORBIDDEN:
        assert phrase not in result, f"금지 표현 발견: '{phrase}'"
