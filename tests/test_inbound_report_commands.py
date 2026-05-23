"""Tests for /리포트, /체인, /기관수급 inbound_bot commands."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

# ── helpers ──────────────────────────────────────────────────────────────────


def _run(coro):
    return asyncio.run(coro)


def _make_client_mock() -> MagicMock:
    mock = MagicMock()
    mock.post = AsyncMock(return_value=MagicMock(status_code=200, raise_for_status=MagicMock()))
    return mock


def _make_settings_mock() -> MagicMock:
    s = MagicMock()
    s.telegram_bot_token = "TEST_TOKEN"
    s.telegram_inbound_bot_token = None
    s.telegram_bot_target_chat_id = "12345"
    s.telegram_inbound_allowed_ids = ""
    return s


# ── /리포트 파싱 ──────────────────────────────────────────────────────────────


def test_report_command_parsing_deep():
    """'/리포트 NVDA deep' 파싱 — use_deep_r=True."""
    from tele_quant.inbound_bot import _handle_command

    sent: list[str] = []

    async def mock_send(client, token, chat_id, text):
        sent.append(text)

    mock_report = MagicMock()
    mock_report.one_line_conclusion = "NVDA — 관찰 B"
    mock_report.score = MagicMock(grade="관찰 B", total=72.0)
    mock_report.error = ""

    with (
        patch("tele_quant.inbound_bot._send", side_effect=mock_send),
        patch("tele_quant.inbound_bot._send_typing", AsyncMock()),
        patch("tele_quant.inbound_bot._resolve_symbol", return_value=("NVDA", "US")),
        patch(
            "tele_quant.analysis.report_builder.build_institutional_report",
            return_value=mock_report,
        ),
        patch(
            "tele_quant.analysis.report_formatter.format_institutional_report",
            return_value=["리포트 내용"],
        ),
    ):
        _run(_handle_command(
            "/리포트 NVDA deep",
            chat_id="12345",
            client=_make_client_mock(),
            token="TOKEN",
            store=None,
            settings=_make_settings_mock(),
        ))

    assert any("⏳" in s for s in sent)
    assert any("리포트 내용" in s for s in sent)


def test_report_command_no_args():
    """인자 없으면 사용법 안내."""
    from tele_quant.inbound_bot import _handle_command

    sent: list[str] = []

    async def mock_send(client, token, chat_id, text):
        sent.append(text)

    with (
        patch("tele_quant.inbound_bot._send", side_effect=mock_send),
        patch("tele_quant.inbound_bot._send_typing", AsyncMock()),
    ):
        _run(_handle_command(
            "/리포트",
            chat_id="12345",
            client=_make_client_mock(),
            token="TOKEN",
            store=None,
            settings=_make_settings_mock(),
        ))

    assert any("사용법" in s for s in sent)


def test_report_command_unknown_symbol():
    """알 수 없는 종목 → 오류 메시지."""
    from tele_quant.inbound_bot import _handle_command

    sent: list[str] = []

    async def mock_send(client, token, chat_id, text):
        sent.append(text)

    with (
        patch("tele_quant.inbound_bot._send", side_effect=mock_send),
        patch("tele_quant.inbound_bot._send_typing", AsyncMock()),
        patch("tele_quant.inbound_bot._resolve_symbol", return_value=None),
    ):
        _run(_handle_command(
            "/리포트 ZZZZZ",
            chat_id="12345",
            client=_make_client_mock(),
            token="TOKEN",
            store=None,
            settings=_make_settings_mock(),
        ))

    assert any("찾을 수 없습니다" in s for s in sent)


# ── /체인 파싱 ────────────────────────────────────────────────────────────────


def test_chain_command_ok():
    """/체인 NVDA → 체인 분석 실행."""
    from tele_quant.inbound_bot import _handle_command

    sent: list[str] = []

    async def mock_send(client, token, chat_id, text):
        sent.append(text)

    with (
        patch("tele_quant.inbound_bot._send", side_effect=mock_send),
        patch("tele_quant.inbound_bot._send_typing", AsyncMock()),
        patch("tele_quant.inbound_bot._resolve_symbol", return_value=("NVDA", "US")),
        patch(
            "tele_quant.analysis.chain_recommendation_engine.build_chain_candidates",
            return_value=([], [], []),
        ),
        patch(
            "tele_quant.analysis.report_formatter.format_chain_candidates",
            return_value="체인 결과",
        ),
    ):
        _run(_handle_command(
            "/체인 NVDA",
            chat_id="12345",
            client=_make_client_mock(),
            token="TOKEN",
            store=None,
            settings=_make_settings_mock(),
        ))

    assert any("체인 결과" in s for s in sent)


def test_chain_command_no_args():
    """/체인 인자 없음 → 사용법."""
    from tele_quant.inbound_bot import _handle_command

    sent: list[str] = []

    async def mock_send(client, token, chat_id, text):
        sent.append(text)

    with (
        patch("tele_quant.inbound_bot._send", side_effect=mock_send),
        patch("tele_quant.inbound_bot._send_typing", AsyncMock()),
    ):
        _run(_handle_command(
            "/체인",
            chat_id="12345",
            client=_make_client_mock(),
            token="TOKEN",
            store=None,
            settings=_make_settings_mock(),
        ))

    assert any("사용법" in s for s in sent)


# ── /기관수급 파싱 ────────────────────────────────────────────────────────────


def test_institutional_flow_command_ok():
    """/기관수급 005930 → 수급 분석 실행."""
    from tele_quant.inbound_bot import _handle_command

    sent: list[str] = []

    async def mock_send(client, token, chat_id, text):
        sent.append(text)

    mock_tech = MagicMock()
    mock_tech.rsi_1d = 55.0
    mock_tech.ret_20d = 5.0
    mock_tech.vol_ratio_20d = 1.2
    mock_tech.bb_pct = 0.6

    mock_flow = MagicMock()
    mock_flow.flow_level = "MEDIUM"

    with (
        patch("tele_quant.inbound_bot._send", side_effect=mock_send),
        patch("tele_quant.inbound_bot._send_typing", AsyncMock()),
        patch("tele_quant.inbound_bot._resolve_symbol", return_value=("005930.KS", "KR")),
        patch(
            "tele_quant.analysis.technical_signal_engine.compute_technical_accumulation_signal",
            return_value=mock_tech,
        ),
        patch(
            "tele_quant.analysis.institutional_flow.compute_institutional_flow",
            return_value=mock_flow,
        ),
        patch(
            "tele_quant.analysis.report_formatter.format_institutional_flow",
            return_value="수급 결과",
        ),
    ):
        _run(_handle_command(
            "/기관수급 005930",
            chat_id="12345",
            client=_make_client_mock(),
            token="TOKEN",
            store=None,
            settings=_make_settings_mock(),
        ))

    assert any("수급 결과" in s for s in sent)


def test_institutional_flow_no_args():
    """/기관수급 인자 없음 → 사용법."""
    from tele_quant.inbound_bot import _handle_command

    sent: list[str] = []

    async def mock_send(client, token, chat_id, text):
        sent.append(text)

    with (
        patch("tele_quant.inbound_bot._send", side_effect=mock_send),
        patch("tele_quant.inbound_bot._send_typing", AsyncMock()),
    ):
        _run(_handle_command(
            "/기관수급",
            chat_id="12345",
            client=_make_client_mock(),
            token="TOKEN",
            store=None,
            settings=_make_settings_mock(),
        ))

    assert any("사용법" in s for s in sent)


# ── /리포트 fallback ──────────────────────────────────────────────────────────


def test_report_fallback_on_error():
    """/리포트 실패 시 /분석 fallback 실행."""
    from tele_quant.inbound_bot import _handle_command

    sent: list[str] = []

    async def mock_send(client, token, chat_id, text):
        sent.append(text)

    mock_snap_text = "fallback 분석 결과"

    with (
        patch("tele_quant.inbound_bot._send", side_effect=mock_send),
        patch("tele_quant.inbound_bot._send_typing", AsyncMock()),
        patch("tele_quant.inbound_bot._resolve_symbol", return_value=("NVDA", "US")),
        patch(
            "tele_quant.analysis.report_builder.build_institutional_report",
            side_effect=Exception("report engine failed"),
        ),
        patch(
            "tele_quant.stock_snapshot.build_stock_snapshot",
            return_value=MagicMock(),
        ),
        patch(
            "tele_quant.stock_snapshot.format_stock_snapshot",
            return_value=mock_snap_text,
        ),
    ):
        _run(_handle_command(
            "/리포트 NVDA",
            chat_id="12345",
            client=_make_client_mock(),
            token="TOKEN",
            store=None,
            settings=_make_settings_mock(),
        ))

    all_sent = " ".join(sent)
    assert "fallback" in all_sent or "대체" in all_sent
