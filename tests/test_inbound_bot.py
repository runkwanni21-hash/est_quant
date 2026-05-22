"""Tests for inbound_bot.py."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tele_quant.inbound_bot import (
    _find_beneficiaries,
    _find_victims,
    _get_allowed_ids,
    _get_inbound_token,
    _handle_command,
    _resolve_symbol,
    analyze_single,
)

# ── _resolve_symbol ───────────────────────────────────────────────────────────

class TestResolveSymbol:
    def test_ks_code_with_suffix(self) -> None:
        result = _resolve_symbol("005930.KS")
        assert result is not None
        sym, market = result
        assert sym == "005930.KS"
        assert market == "KR"

    def test_kq_code_with_suffix(self) -> None:
        result = _resolve_symbol("247540.KQ")
        assert result is not None
        assert result[1] == "KR"

    def test_six_digit_no_suffix(self) -> None:
        result = _resolve_symbol("005930")
        assert result is not None
        assert result[0] == "005930.KS"
        assert result[1] == "KR"

    def test_us_ticker_uppercase(self) -> None:
        result = _resolve_symbol("NVDA")
        assert result is not None
        sym, market = result
        assert sym == "NVDA"
        assert market == "US"

    def test_korean_name_exact(self) -> None:
        result = _resolve_symbol("삼성전자")
        assert result is not None
        sym, market = result
        assert sym == "005930.KS"
        assert market == "KR"

    def test_korean_name_partial(self) -> None:
        result = _resolve_symbol("SK하이닉스")
        assert result is not None
        assert result[0] == "000660.KS"

    def test_english_name_case_insensitive(self) -> None:
        result = _resolve_symbol("nvidia")
        assert result is not None
        assert result[0] == "NVDA"

    def test_unknown_returns_none(self) -> None:
        assert _resolve_symbol("XYZUNKNOWN99999") is None

    def test_unknown_korean_returns_none(self) -> None:
        assert _resolve_symbol("존재하지않는회사이름XYZ") is None

    def test_case_insensitive_us(self) -> None:
        result = _resolve_symbol("nvda")
        assert result is not None
        assert result[0] == "NVDA"


# ── _get_allowed_ids ──────────────────────────────────────────────────────────

class TestGetAllowedIds:
    def _settings(self, inbound_ids: str = "", target_chat_id: str | None = None) -> MagicMock:
        s = MagicMock()
        s.telegram_inbound_allowed_ids = inbound_ids
        s.telegram_bot_target_chat_id = target_chat_id
        return s

    def test_explicit_ids(self) -> None:
        s = self._settings(inbound_ids="123,456,789")
        ids = _get_allowed_ids(s)
        assert ids == {"123", "456", "789"}

    def test_fallback_to_target_chat(self) -> None:
        s = self._settings(inbound_ids="", target_chat_id="999")
        ids = _get_allowed_ids(s)
        assert "999" in ids

    def test_empty_both_returns_empty(self) -> None:
        s = self._settings(inbound_ids="", target_chat_id=None)
        ids = _get_allowed_ids(s)
        assert ids == set()

    def test_whitespace_stripped(self) -> None:
        s = self._settings(inbound_ids=" 100 , 200 ")
        ids = _get_allowed_ids(s)
        assert "100" in ids
        assert "200" in ids


# ── _get_inbound_token ────────────────────────────────────────────────────────

class TestGetInboundToken:
    def test_dedicated_token_preferred(self) -> None:
        s = MagicMock()
        s.telegram_inbound_bot_token = "INBOUND_TOKEN"
        s.telegram_bot_token = "FALLBACK_TOKEN"
        assert _get_inbound_token(s) == "INBOUND_TOKEN"

    def test_fallback_to_bot_token(self) -> None:
        s = MagicMock()
        s.telegram_inbound_bot_token = None
        s.telegram_bot_token = "FALLBACK_TOKEN"
        assert _get_inbound_token(s) == "FALLBACK_TOKEN"

    def test_both_none_returns_none(self) -> None:
        s = MagicMock()
        s.telegram_inbound_bot_token = None
        s.telegram_bot_token = None
        assert _get_inbound_token(s) is None


# ── analyze_single ────────────────────────────────────────────────────────────

class TestAnalyzeSingle:
    def _mock_tech(self, rsi: float = 45.0, close: float = 470_000.0) -> dict:
        return {
            "rsi": rsi,
            "obv": "상승",
            "bb_pct": 30.0,
            "close": close,
            "vol_ratio": 1.3,
        }

    def _mock_fund(self) -> MagicMock:
        from datetime import UTC, datetime

        from tele_quant.fundamentals import FundamentalSnapshot
        return FundamentalSnapshot(
            symbol="128940.KS",
            market="KR",
            sector="제약",
            fetched_at=datetime.now(UTC),
            pe_trailing=14.0,
            pb=1.5,
            roe=16.0,
            w52_position_pct=40.0,
            current_price=470_000.0,
            market_cap_krw=2_000_000_000_000,
        )

    def test_returns_string(self) -> None:
        with (
            patch("tele_quant.daily_alpha._fetch_4h_data", return_value=self._mock_tech()),
            patch("tele_quant.fundamentals.fetch_fundamentals", return_value=self._mock_fund()),
        ):
            result = analyze_single("128940.KS", "KR")
        assert isinstance(result, str)
        assert len(result) > 50

    def test_contains_symbol(self) -> None:
        with (
            patch("tele_quant.daily_alpha._fetch_4h_data", return_value=self._mock_tech()),
            patch("tele_quant.fundamentals.fetch_fundamentals", return_value=self._mock_fund()),
        ):
            result = analyze_single("128940.KS", "KR")
        assert "128940" in result

    def test_contains_disclaimer(self) -> None:
        with (
            patch("tele_quant.daily_alpha._fetch_4h_data", return_value=self._mock_tech()),
            patch("tele_quant.fundamentals.fetch_fundamentals", return_value=self._mock_fund()),
        ):
            result = analyze_single("128940.KS", "KR")
        assert "투자 판단" in result

    def test_no_buy_sell_language(self) -> None:
        with (
            patch("tele_quant.daily_alpha._fetch_4h_data", return_value=self._mock_tech()),
            patch("tele_quant.fundamentals.fetch_fundamentals", return_value=self._mock_fund()),
        ):
            result = analyze_single("128940.KS", "KR")
        assert "매수 권장" not in result
        assert "매도 권장" not in result

    def test_overbought_suggests_short(self) -> None:
        with (
            patch("tele_quant.daily_alpha._fetch_4h_data", return_value=self._mock_tech(rsi=78.0)),
            patch("tele_quant.fundamentals.fetch_fundamentals", return_value=self._mock_fund()),
        ):
            result = analyze_single("128940.KS", "KR")
        assert "SHORT" in result

    def test_oversold_suggests_long(self) -> None:
        with (
            patch("tele_quant.daily_alpha._fetch_4h_data", return_value=self._mock_tech(rsi=28.0)),
            patch("tele_quant.fundamentals.fetch_fundamentals", return_value=self._mock_fund()),
        ):
            result = analyze_single("128940.KS", "KR")
        assert "LONG" in result

    def test_tech_fetch_failure_still_returns_text(self) -> None:
        with (
            patch("tele_quant.daily_alpha._fetch_4h_data", side_effect=RuntimeError("네트워크 오류")),
            patch("tele_quant.fundamentals.fetch_fundamentals", return_value=self._mock_fund()),
        ):
            result = analyze_single("128940.KS", "KR")
        assert isinstance(result, str)
        assert "128940" in result

    def test_us_symbol_dollar_price(self) -> None:
        from datetime import UTC, datetime

        from tele_quant.fundamentals import FundamentalSnapshot
        us_fund = FundamentalSnapshot(
            symbol="NVDA",
            market="US",
            sector="Technology",
            fetched_at=datetime.now(UTC),
            pe_trailing=35.0,
            pb=25.0,
            roe=80.0,
            w52_position_pct=60.0,
            current_price=875.0,
        )
        with (
            patch("tele_quant.daily_alpha._fetch_4h_data",
                  return_value=self._mock_tech(close=875.0)),
            patch("tele_quant.fundamentals.fetch_fundamentals", return_value=us_fund),
        ):
            result = analyze_single("NVDA", "US")
        assert "$" in result


# ── _handle_command ───────────────────────────────────────────────────────────

class TestHandleCommand:
    """명령 라우팅만 테스트 (실제 API 호출 없이)."""

    def _make_deps(self):
        client = AsyncMock()
        token = "TEST_TOKEN"
        chat_id = "12345"
        settings = MagicMock()
        settings.telegram_bot_target_chat_id = "12345"
        settings.telegram_inbound_allowed_ids = ""
        store = None
        return client, token, chat_id, settings, store

    @pytest.mark.asyncio
    async def test_help_command(self) -> None:
        client, token, chat_id, settings, store = self._make_deps()
        with patch("tele_quant.inbound_bot._send", new=AsyncMock()) as mock_send_fn:
            await _handle_command("/도움말", chat_id, client, token, store, settings)
            assert mock_send_fn.called

    @pytest.mark.asyncio
    async def test_unknown_symbol_analyze(self) -> None:
        client, token, chat_id, settings, store = self._make_deps()
        replies: list[str] = []

        async def capture_send(c, t, cid, text):
            replies.append(text)

        with (
            patch("tele_quant.inbound_bot._send", side_effect=capture_send),
            patch("tele_quant.inbound_bot._send_typing", new=AsyncMock()),
        ):
            await _handle_command("/분석 XYZUNKNOWN99", chat_id, client, token, store, settings)

        assert any("인식할 수 없습니다" in r or "찾을 수 없습니다" in r for r in replies)

    @pytest.mark.asyncio
    async def test_analyze_known_symbol(self) -> None:
        client, token, chat_id, settings, store = self._make_deps()
        replies: list[str] = []
        from datetime import UTC, datetime

        from tele_quant.fundamentals import FundamentalSnapshot

        async def capture_send(c, t, cid, text):
            replies.append(text)

        mock_fund = FundamentalSnapshot(
            symbol="005930.KS", market="KR", sector="반도체",
            fetched_at=datetime.now(UTC), current_price=78_000.0,
        )

        with (
            patch("tele_quant.inbound_bot._send", side_effect=capture_send),
            patch("tele_quant.inbound_bot._send_typing", new=AsyncMock()),
            patch("tele_quant.daily_alpha._fetch_4h_data", return_value={"rsi": 50.0, "close": 78_000.0}),
            patch("tele_quant.fundamentals.fetch_fundamentals", return_value=mock_fund),
        ):
            await _handle_command("/분석 삼성전자", chat_id, client, token, store, settings)

        full = "\n".join(replies)
        assert "005930" in full or "삼성전자" in full

    @pytest.mark.asyncio
    async def test_macro_command(self) -> None:
        client, token, chat_id, settings, store = self._make_deps()
        replies: list[str] = []
        from datetime import UTC, datetime

        from tele_quant.macro_pulse import MacroSnapshot

        async def capture_send(c, t, cid, text):
            replies.append(text)

        mock_snap = MacroSnapshot(
            fetched_at=datetime.now(UTC),
            wti_price=78.0, wti_chg=0.5,
            us10y=4.40, us10y_chg=5.0,
            usd_krw=1380.0, usd_krw_chg=0.0,
            vix=15.0, vix_chg=-0.5,
            gold_price=2320.0, gold_chg=0.2,
            sp500_chg=0.3, kospi_chg=0.1,
            dxy=104.0, dxy_chg=0.1,
            regime="중립",
            interpretations=[],
        )

        with (
            patch("tele_quant.inbound_bot._send", side_effect=capture_send),
            patch("tele_quant.inbound_bot._send_typing", new=AsyncMock()),
            patch("tele_quant.macro_pulse.fetch_macro_snapshot", return_value=mock_snap),
        ):
            await _handle_command("/매크로", chat_id, client, token, store, settings)

        assert any("매크로" in r or "WTI" in r or "중립" in r for r in replies)

    @pytest.mark.asyncio
    async def test_portfolio_without_store(self) -> None:
        client, token, chat_id, settings, _store = self._make_deps()
        replies: list[str] = []

        async def capture_send(c, t, cid, text):
            replies.append(text)

        with (
            patch("tele_quant.inbound_bot._send", side_effect=capture_send),
            patch("tele_quant.inbound_bot._send_typing", new=AsyncMock()),
        ):
            await _handle_command("/포트", chat_id, client, token, None, settings)

        assert any("DB" in r or "연결" in r for r in replies)


# ── _find_beneficiaries / _find_victims ──────────────────────────────────────

class TestFindBeneficiaries:
    def _make_rules(self) -> list[dict]:
        return [
            {
                "id": "nvda_chain",
                "chain_name": "AI GPU Chain",
                "market": "US",
                "source_symbols": [{"symbol": "NVDA", "name": "NVIDIA"}],
                "source_keywords": [],
                "beneficiaries": [
                    {
                        "relation_type": "BENEFICIARY",
                        "sector": "Memory",
                        "connection": "AI demand",
                        "symbols": [
                            {"symbol": "MU", "name": "Micron"},
                            {"symbol": "TSM", "name": "TSMC"},
                        ],
                    }
                ],
                "victims_on_bearish": [
                    {
                        "relation_type": "VICTIM",
                        "sector": "Legacy",
                        "connection": "demand shift",
                        "symbols": [
                            {"symbol": "INTC", "name": "Intel"},
                        ],
                    }
                ],
            }
        ]

    def test_returns_string(self) -> None:
        with patch("tele_quant.supply_chain_alpha.load_supply_chain_rules", return_value=self._make_rules()):
            result = _find_beneficiaries("NVDA", None)
        assert isinstance(result, str)

    def test_contains_beneficiary_symbol(self) -> None:
        with patch("tele_quant.supply_chain_alpha.load_supply_chain_rules", return_value=self._make_rules()):
            result = _find_beneficiaries("NVDA", None)
        assert "MU" in result or "TSM" in result

    def test_no_match_returns_fallback(self) -> None:
        with patch("tele_quant.supply_chain_alpha.load_supply_chain_rules", return_value=self._make_rules()):
            result = _find_beneficiaries("XYZUNKNOWN99", None)
        assert "없음" in result or "미충족" in result

    def test_contains_disclaimer(self) -> None:
        with patch("tele_quant.supply_chain_alpha.load_supply_chain_rules", return_value=self._make_rules()):
            result = _find_beneficiaries("NVDA", None)
        assert "투자 판단" in result

    def test_no_forbidden_words(self) -> None:
        with patch("tele_quant.supply_chain_alpha.load_supply_chain_rules", return_value=self._make_rules()):
            result = _find_beneficiaries("NVDA", None)
        forbidden = ["매수 권장", "수혜 확정", "확정 수익"]
        for word in forbidden:
            assert word not in result, f"Forbidden: '{word}'"

    def test_no_self_loop(self) -> None:
        with patch("tele_quant.supply_chain_alpha.load_supply_chain_rules", return_value=self._make_rules()):
            result = _find_beneficiaries("NVDA", None)
        assert "NVDA(NVDA)" not in result


class TestFindVictims:
    def _make_rules(self) -> list[dict]:
        return [
            {
                "id": "nvda_chain",
                "chain_name": "AI GPU Chain",
                "market": "US",
                "source_symbols": [{"symbol": "NVDA", "name": "NVIDIA"}],
                "source_keywords": [],
                "beneficiaries": [],
                "victims_on_bearish": [
                    {
                        "relation_type": "VICTIM",
                        "sector": "Legacy",
                        "connection": "demand shift",
                        "symbols": [
                            {"symbol": "INTC", "name": "Intel"},
                            {"symbol": "AMD", "name": "AMD"},
                        ],
                    }
                ],
            }
        ]

    def test_returns_string(self) -> None:
        with patch("tele_quant.supply_chain_alpha.load_supply_chain_rules", return_value=self._make_rules()):
            result = _find_victims("NVDA", None)
        assert isinstance(result, str)

    def test_contains_victim_symbol(self) -> None:
        with patch("tele_quant.supply_chain_alpha.load_supply_chain_rules", return_value=self._make_rules()):
            result = _find_victims("NVDA", None)
        assert "INTC" in result or "AMD" in result

    def test_no_match_returns_fallback(self) -> None:
        with patch("tele_quant.supply_chain_alpha.load_supply_chain_rules", return_value=self._make_rules()):
            result = _find_victims("XYZUNKNOWN99", None)
        assert "없음" in result or "미충족" in result

    def test_no_forbidden_expressions(self) -> None:
        with patch("tele_quant.supply_chain_alpha.load_supply_chain_rules", return_value=self._make_rules()):
            result = _find_victims("NVDA", None)
        forbidden = ["피해 확정", "무조건 하락", "반드시 하락", "확정 손실", "매도 권장"]
        for word in forbidden:
            assert word not in result, f"Forbidden: '{word}'"

    def test_uses_risk_label_not_definitive(self) -> None:
        with patch("tele_quant.supply_chain_alpha.load_supply_chain_rules", return_value=self._make_rules()):
            result = _find_victims("NVDA", None)
        assert "리스크" in result

    def test_contains_disclaimer(self) -> None:
        with patch("tele_quant.supply_chain_alpha.load_supply_chain_rules", return_value=self._make_rules()):
            result = _find_victims("NVDA", None)
        assert "인과관계" in result or "투자 판단" in result

    def test_no_self_loop(self) -> None:
        with patch("tele_quant.supply_chain_alpha.load_supply_chain_rules", return_value=self._make_rules()):
            result = _find_victims("NVDA", None)
        assert "NVDA(NVDA)" not in result


class TestPihaeCommand:
    """'/피해 후보 <종목>' 명령 라우팅 테스트."""

    def _make_deps(self):
        client = AsyncMock()
        token = "TEST_TOKEN"
        chat_id = "12345"
        settings = MagicMock()
        settings.telegram_bot_target_chat_id = "12345"
        settings.telegram_inbound_allowed_ids = ""
        store = None
        return client, token, chat_id, settings, store

    @pytest.mark.asyncio
    async def test_pihaehuboo_no_args(self) -> None:
        client, token, chat_id, settings, store = self._make_deps()
        replies: list[str] = []

        async def capture_send(c, t, cid, text):
            replies.append(text)

        with (
            patch("tele_quant.inbound_bot._send", side_effect=capture_send),
            patch("tele_quant.inbound_bot._send_typing", new=AsyncMock()),
        ):
            await _handle_command("/피해 후보", chat_id, client, token, store, settings)

        assert any("사용법" in r for r in replies)

    @pytest.mark.asyncio
    async def test_pihaehuboo_unknown_symbol(self) -> None:
        client, token, chat_id, settings, store = self._make_deps()
        replies: list[str] = []

        async def capture_send(c, t, cid, text):
            replies.append(text)

        with (
            patch("tele_quant.inbound_bot._send", side_effect=capture_send),
            patch("tele_quant.inbound_bot._send_typing", new=AsyncMock()),
        ):
            await _handle_command("/피해 후보 XYZUNKNOWN99", chat_id, client, token, store, settings)

        assert any("찾을 수 없습니다" in r for r in replies)

    @pytest.mark.asyncio
    async def test_pihaehuboo_known_symbol(self) -> None:
        client, token, chat_id, settings, store = self._make_deps()
        replies: list[str] = []

        async def capture_send(c, t, cid, text):
            replies.append(text)

        with (
            patch("tele_quant.inbound_bot._send", side_effect=capture_send),
            patch("tele_quant.inbound_bot._send_typing", new=AsyncMock()),
            patch(
                "tele_quant.supply_chain_alpha.load_supply_chain_rules",
                return_value=[],
            ),
        ):
            await _handle_command("/피해 후보 NVDA", chat_id, client, token, store, settings)

        full = "\n".join(replies)
        assert len(full) > 0


# ── /분석 sub-options ──────────────────────────────────────────────────────────


class TestBunseokSubOptions:
    def _make_deps(self):
        client = MagicMock()
        token = "test_token"
        chat_id = 999
        settings = MagicMock()
        settings.allowed_chat_ids = [chat_id]
        store = MagicMock()
        return client, token, chat_id, settings, store

    @pytest.mark.asyncio
    async def test_bunseok_basic(self) -> None:
        """기본 /분석 명령이 응답을 반환한다."""
        client, token, chat_id, settings, store = self._make_deps()
        replies: list[str] = []

        async def capture_send(c, t, cid, text):
            replies.append(text)

        from datetime import UTC, datetime

        from tele_quant.fundamentals import FundamentalSnapshot
        mock_fund = FundamentalSnapshot(
            symbol="NVDA", market="US", sector="Semiconductors",
            fetched_at=datetime.now(UTC), current_price=875.0,
        )

        with (
            patch("tele_quant.inbound_bot._send", side_effect=capture_send),
            patch("tele_quant.inbound_bot._send_typing", new=AsyncMock()),
            patch("tele_quant.daily_alpha._fetch_4h_data", return_value={"rsi": 55.0, "close": 875.0}),
            patch("tele_quant.fundamentals.fetch_fundamentals", return_value=mock_fund),
            patch("tele_quant.stock_snapshot.fetch_price_window", return_value=None),
        ):
            await _handle_command("/분석 NVDA", chat_id, client, token, store, settings)

        full = "\n".join(replies)
        assert "NVDA" in full
        assert "투자 판단" in full

    @pytest.mark.asyncio
    async def test_bunseok_sub_option_deep_parses(self) -> None:
        """'/분석 NVDA deep' — deep 옵션이 파싱되고 응답이 나온다."""
        client, token, chat_id, settings, store = self._make_deps()
        replies: list[str] = []

        async def capture_send(c, t, cid, text):
            replies.append(text)

        from datetime import UTC, datetime

        from tele_quant.fundamentals import FundamentalSnapshot

        mock_fund = FundamentalSnapshot(
            symbol="NVDA", market="US", sector="Semiconductors",
            fetched_at=datetime.now(UTC), current_price=875.0,
        )

        with (
            patch("tele_quant.inbound_bot._send", side_effect=capture_send),
            patch("tele_quant.inbound_bot._send_typing", new=AsyncMock()),
            patch("tele_quant.daily_alpha._fetch_4h_data", return_value={"rsi": 50.0, "close": 875.0}),
            patch("tele_quant.fundamentals.fetch_fundamentals", return_value=mock_fund),
            patch("tele_quant.stock_snapshot.fetch_price_window", return_value=None),
        ):
            await _handle_command("/분석 NVDA deep", chat_id, client, token, store, settings)

        full = "\n".join(replies)
        assert len(full) > 0

    @pytest.mark.asyncio
    async def test_bunseok_sub_option_기본(self) -> None:
        """'/분석 삼성전자 기본' — 기본 옵션이 종목코드와 분리된다."""
        client, token, chat_id, settings, store = self._make_deps()
        replies: list[str] = []

        async def capture_send(c, t, cid, text):
            replies.append(text)

        from datetime import UTC, datetime

        from tele_quant.fundamentals import FundamentalSnapshot

        mock_fund = FundamentalSnapshot(
            symbol="005930.KS", market="KR", sector="반도체",
            fetched_at=datetime.now(UTC), current_price=70000.0,
        )

        with (
            patch("tele_quant.inbound_bot._send", side_effect=capture_send),
            patch("tele_quant.inbound_bot._send_typing", new=AsyncMock()),
            patch("tele_quant.daily_alpha._fetch_4h_data", return_value={"rsi": 50.0, "close": 70000.0}),
            patch("tele_quant.fundamentals.fetch_fundamentals", return_value=mock_fund),
            patch("tele_quant.stock_snapshot.fetch_price_window", return_value=None),
        ):
            await _handle_command("/분석 삼성전자 기본", chat_id, client, token, store, settings)

        full = "\n".join(replies)
        assert "005930" in full or "삼성" in full or "투자 판단" in full

    @pytest.mark.asyncio
    async def test_bunseok_empty_query_shows_usage(self) -> None:
        """'/분석' (종목 없음) — 사용법 안내가 나온다."""
        client, token, chat_id, settings, store = self._make_deps()
        replies: list[str] = []

        async def capture_send(c, t, cid, text):
            replies.append(text)

        with (
            patch("tele_quant.inbound_bot._send", side_effect=capture_send),
            patch("tele_quant.inbound_bot._send_typing", new=AsyncMock()),
        ):
            await _handle_command("/분석", chat_id, client, token, store, settings)

        full = "\n".join(replies)
        assert "사용법" in full or "옵션" in full
