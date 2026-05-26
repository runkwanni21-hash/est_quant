"""텔레그램 수신 봇 — 사용자 명령을 받아 즉시 분석 응답을 돌려준다.

지원 명령:
  /분석 <종목코드|이름>  — 개별 종목 즉시 분석 (펀더멘탈 + 기술적 + 수혜주 힌트)
  /리포트 <종목> [deep] — 기관식 스윙 리포트 (1~3분, 품질 우선)
  /체인 <종목>          — 관계 체인 후보 (수혜/부담/피어)
  /기관수급 <종목>      — 기관/외국인 수급집중 가능성 분석
  /브리핑 [KR|US]       — 4H 통합 브리핑 (30초~1분 소요)
  /포트                  — 모의 포트폴리오 현황
  /매크로                — 매크로 온도계 (WTI·금리·환율·VIX)
  /수혜주 <종목>         — 수급 체인 수혜주 발굴
  /피해 후보 <종목>      — 수급 체인 비용 압박·수요 전환 리스크 후보 발굴
  /도움말                — 명령 목록

보안: TELEGRAM_INBOUND_ALLOWED_IDS 에 등록된 chat_id 만 응답.
미등록 시 TELEGRAM_BOT_TARGET_CHAT_ID 로 fallback.

실계좌 주문 없음. 공개 정보 기반 리서치 보조.
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import TYPE_CHECKING, Any

import httpx

from tele_quant.stock_snapshot import analyze_single  # noqa: F401 (re-exported for tests)
from tele_quant.textutil import mask_bot_token

if TYPE_CHECKING:
    from tele_quant.db import Store
    from tele_quant.settings import Settings

log = logging.getLogger(__name__)

_DISCLAIMER = "⚠ 공개 정보 기반 리서치 보조 — 투자 판단 책임은 사용자에게 있음"

_HELP_TEXT = """\
🤖 **tele-quant 봇 명령어**

/분석 <종목>   — 개별 종목 즉시 분석 (10~30초)
  예) /분석 삼성전자   /분석 005930   /분석 NVDA

/리포트 <종목> [deep]  — 기관식 스윙 리포트 (1~3분, 품질 우선)
  예) /리포트 NVDA   /리포트 005930.KS deep

/체인 <종목>  — 관계 체인 후보 (수혜/부담/피어)
  예) /체인 NVDA   /체인 삼성전자

/기관수급 <종목>  — 수급집중 가능성 분석
  예) /기관수급 005930   /기관수급 NVDA

/브리핑 [KR|US]  — 4H 통합 브리핑 (30초~1분 소요)
  예) /브리핑   /브리핑 US

/포트  — 모의 포트폴리오 현황

/매크로  — 매크로 온도계 (WTI·금리·환율·VIX)

/수혜주 <종목>  — 이슈 수혜주 발굴
  예) /수혜주 삼성전자

/피해 후보 <종목>  — 비용 압박·수요 전환 리스크 후보
  예) /피해 후보 NVDA   /피해 후보 삼성전자

/수주 <종목>  — 수주잔고 조회 (조선·방산·인프라 등)
  예) /수주 HD현대중공업   /수주 329180.KS

/도움말  — 이 도움말

──────────────
공개 정보 기반 리서치 보조. 실계좌 주문 없음.
"""

# ── 심볼 해석 ─────────────────────────────────────────────────────────────────

def _resolve_symbol(query: str) -> tuple[str, str] | None:
    """종목 코드 또는 이름을 (symbol, market) 튜플로 변환.

    Returns None if the query cannot be resolved to a known symbol.
    """
    from tele_quant.relation_feed import _NAME_MAP, _UNIVERSE_US

    q = query.strip()

    # 1. 6자리 숫자 + .KS/.KQ 코드
    if re.match(r"^\d{6}\.(KS|KQ)$", q, re.IGNORECASE):
        sym = q.upper()
        return sym, "KR"

    # 6자리 숫자만 (접미사 없음) → .KS 추가
    if re.match(r"^\d{6}$", q):
        sym = q + ".KS"
        return sym, "KR"

    # 2. US 티커 (대문자 1~5자)
    q_up = q.upper()
    if re.match(r"^[A-Z]{1,5}$", q_up) and (q_up in _UNIVERSE_US or q_up in _NAME_MAP):
        return q_up, "US"

    # 3. 한글/영문 이름 완전 일치 (대소문자 무시)
    q_low = q.lower()
    for sym, name in _NAME_MAP.items():
        if name.lower() == q_low:
            market = "KR" if sym.endswith((".KS", ".KQ")) else "US"
            return sym, market

    # 4. 한글/영문 이름 부분 포함 일치 (가장 짧은 이름이 우선)
    candidates: list[tuple[str, str, str]] = []  # (sym, market, name)
    for sym, name in _NAME_MAP.items():
        n_low = name.lower()
        if q_low in n_low or n_low in q_low:
            market = "KR" if sym.endswith((".KS", ".KQ")) else "US"
            candidates.append((sym, market, name))

    if candidates:
        # 이름이 짧을수록 더 직접적인 매칭
        candidates.sort(key=lambda x: len(x[2]))
        return candidates[0][0], candidates[0][1]

    return None


def _market_of(symbol: str) -> str:
    return "KR" if symbol.endswith((".KS", ".KQ")) else "US"


# analyze_single은 stock_snapshot.py에서 re-export (모듈 상단 import 참조)


# ── 수혜주 발굴 ───────────────────────────────────────────────────────────────

def _find_beneficiaries(symbol: str, store: Store | None) -> str:
    """종목의 수급 체인 수혜주 목록 반환."""
    from tele_quant.relation_feed import _NAME_MAP
    from tele_quant.supply_chain_alpha import (
        MoverEvent,
        _match_mover_to_rules,
        load_supply_chain_rules,
    )

    market = _market_of(symbol)
    name = _NAME_MAP.get(symbol, symbol)

    try:
        rules = load_supply_chain_rules()
    except Exception as exc:
        log.warning("[inbound] rule load failed: %s", exc)
        return f"{name} 체인 규칙 로드 실패"

    mover = MoverEvent(
        symbol=symbol, name=name, market=market,
        return_1d=5.0, direction="BULLISH", confidence="HIGH",
        volume_ratio=2.0, reason_type="catalyst", reason_ko="체인 조회",
    )

    matched = _match_mover_to_rules(mover, rules)

    # 1. Supply-chain rules에서 beneficiaries 추출
    items: list[str] = []
    seen: set[str] = set()
    for rule in matched[:6]:
        for ben_group in rule.get("beneficiaries", []):
            connection = ben_group.get("connection", "")
            for sym_entry in ben_group.get("symbols", []):
                tsym = sym_entry.get("symbol", "")
                tname = sym_entry.get("name", tsym)
                if not tsym or tsym == symbol or tsym in seen:
                    continue
                seen.add(tsym)
                display_name = _NAME_MAP.get(tsym, tname)
                note = f"[{connection}]" if connection else ""
                items.append(f"• {display_name}({tsym}) {note}")
            if len(items) >= 8:
                break

    # 2. DB relation_edges에서 추가 (BENEFICIARY / PEER_MOMENTUM)
    if store is not None:
        try:
            edges = store.get_all_relation_edges(active_only=True)
            bene_types = {"BENEFICIARY", "PEER_MOMENTUM", "SUPPLIER", "CUSTOMER"}
            for e in edges:
                if e.get("source_symbol") != symbol:
                    continue
                if e.get("relation_type") not in bene_types:
                    continue
                tsym = e.get("target_symbol", "")
                if not tsym or tsym in seen:
                    continue
                seen.add(tsym)
                display_name = _NAME_MAP.get(tsym, tsym)
                score = e.get("relation_score")
                score_str = f" score={score:.0f}" if score is not None else ""
                items.append(f"• {display_name}({tsym}){score_str} [DB]")
                if len(items) >= 10:
                    break
        except Exception as exc:
            log.debug("[inbound] beneficiary DB lookup failed: %s", exc)

    if not items:
        return (
            f"{name}({symbol}) — 수혜주 체인 없음\n"
            "체인 규칙에 등록되지 않은 종목이거나 매칭 조건 미충족."
        )

    lines = [f"🔗 **{name}({symbol}) 수혜주 체인**\n"]
    lines.extend(items)
    lines.append("")
    lines.append("⚠ 과거 패턴·규칙 기반 리서치 보조 — 실제 반응은 별도 확인 필요")
    lines.append("상관관계는 인과관계가 아님. 투자 판단 책임은 사용자에게 있음.")
    return "\n".join(lines)


def _find_victims(symbol: str, store: Store | None) -> str:
    """종목 급등 시 비용 압박·수요 전환 리스크가 예상되는 종목 목록.

    '피해 확정' 표현 사용 금지. 상대적 비용 압박 리스크 / 수요 전환 리스크로 표현.
    """
    from tele_quant.relation_feed import _NAME_MAP
    from tele_quant.supply_chain_alpha import (
        MoverEvent,
        _match_mover_to_rules,
        load_supply_chain_rules,
    )

    market = _market_of(symbol)
    name = _NAME_MAP.get(symbol, symbol)

    try:
        rules = load_supply_chain_rules()
    except Exception as exc:
        log.warning("[inbound] rule load failed: %s", exc)
        return f"{name} 체인 규칙 로드 실패"

    # BEARISH mover로 victims_on_bearish 조회 (source가 하락할 때 체인 피해)
    mover_bearish = MoverEvent(
        symbol=symbol, name=name, market=market,
        return_1d=-5.0, direction="BEARISH", confidence="HIGH",
        volume_ratio=2.0, reason_type="catalyst", reason_ko="피해 후보 조회",
    )

    matched = _match_mover_to_rules(mover_bearish, rules)

    items: list[str] = []
    seen: set[str] = set()

    # 1. Supply-chain rules victims_on_bearish
    for rule in matched[:6]:
        for vic_group in rule.get("victims_on_bearish", []):
            connection = vic_group.get("connection", "")
            for sym_entry in vic_group.get("symbols", []):
                tsym = sym_entry.get("symbol", "")
                tname = sym_entry.get("name", tsym)
                if not tsym or tsym == symbol or tsym in seen:
                    continue
                seen.add(tsym)
                display_name = _NAME_MAP.get(tsym, tname)
                # 완곡한 표현 — "피해 확정" 금지
                note = f"[{connection}]" if connection else ""
                items.append(f"• {display_name}({tsym}) {note} — 수요 전환 리스크")
                if len(items) >= 8:
                    break

    # 2. DB relation_edges — VICTIM / COMPETITOR / INPUT_COST_VICTIM (UP_LEADS_DOWN)
    if store is not None:
        try:
            edges = store.get_all_relation_edges(active_only=True)
            victim_types = {"VICTIM", "COMPETITOR", "INPUT_COST_VICTIM"}
            for e in edges:
                if e.get("source_symbol") != symbol:
                    continue
                rel_type = e.get("relation_type", "")
                direction = e.get("direction", "")
                if rel_type not in victim_types and direction != "UP_LEADS_DOWN":
                    continue
                tsym = e.get("target_symbol", "")
                if not tsym or tsym in seen:
                    continue
                seen.add(tsym)
                display_name = _NAME_MAP.get(tsym, tsym)
                score = e.get("relation_score")
                score_str = f" score={score:.0f}" if score is not None else ""
                # 완곡한 표현
                risk_label = "상대적 비용 압박 리스크" if rel_type == "INPUT_COST_VICTIM" else "수요 전환 리스크"
                items.append(f"• {display_name}({tsym}){score_str} [DB] — {risk_label}")
                if len(items) >= 10:
                    break
        except Exception as exc:
            log.debug("[inbound] victim DB lookup failed: %s", exc)

    if not items:
        return (
            f"{name}({symbol}) — 체인 리스크 후보 없음\n"
            "규칙에 등록되지 않은 종목이거나 매칭 조건 미충족."
        )

    lines = [f"⚠ **{name}({symbol}) 비용 압박·수요 전환 리스크 후보**\n"]
    lines.extend(items)
    lines.append("")
    lines.append("※ '상대적 비용 압박 리스크' / '수요 전환 리스크' — 하락 확정이 아님.")
    lines.append("상관관계는 인과관계가 아님. 투자 판단 책임은 사용자에게 있음.")
    return "\n".join(lines)


# ── 텔레그램 API 헬퍼 ─────────────────────────────────────────────────────────

async def _tg_get(
    client: httpx.AsyncClient,
    token: str,
    method: str,
    **params: Any,
) -> dict[str, Any]:
    url = f"https://api.telegram.org/bot{token}/{method}"
    resp = await client.get(url, params=params, timeout=35.0)
    resp.raise_for_status()
    return resp.json()


async def _tg_post(
    client: httpx.AsyncClient,
    token: str,
    method: str,
    payload: dict[str, Any],
) -> None:
    url = f"https://api.telegram.org/bot{token}/{method}"
    resp = await client.post(url, json=payload, timeout=15.0)
    if resp.status_code == 400:
        log.warning("[inbound] 400 Bad Request: %s", mask_bot_token(resp.text[:300]))
    else:
        resp.raise_for_status()


async def _send(
    client: httpx.AsyncClient,
    token: str,
    chat_id: int | str,
    text: str,
) -> None:
    """텍스트를 4000자 청크로 나눠 전송."""
    chunks = [text[i : i + 4000] for i in range(0, len(text), 4000)]
    for i, chunk in enumerate(chunks):
        prefix = f"({i + 1}/{len(chunks)})\n" if len(chunks) > 1 else ""
        await _tg_post(
            client,
            token,
            "sendMessage",
            {"chat_id": chat_id, "text": prefix + chunk, "disable_web_page_preview": True},
        )


async def _send_typing(
    client: httpx.AsyncClient,
    token: str,
    chat_id: int | str,
) -> None:
    import contextlib as _contextlib
    with _contextlib.suppress(Exception):
        await _tg_post(
            client, token, "sendChatAction", {"chat_id": chat_id, "action": "typing"}
        )


# ── 명령 처리 ─────────────────────────────────────────────────────────────────

async def _handle_command(
    text: str,
    chat_id: int | str,
    client: httpx.AsyncClient,
    token: str,
    store: Store | None,
    settings: Settings,
) -> None:
    """단일 메시지 텍스트를 파싱하고 적절한 응답을 보낸다."""
    text = text.strip()
    cmd, _, args = text.partition(" ")
    cmd = cmd.lower().lstrip("/")
    args = args.strip()

    # 봇 멘션 (@botname) 제거
    cmd = cmd.split("@")[0]

    await _send_typing(client, token, chat_id)

    # ── /도움말 / /help ───────────────────────────────────────────────────────
    if cmd in ("도움말", "help", "start"):
        await _send(client, token, chat_id, _HELP_TEXT)
        return

    # ── /매크로 ───────────────────────────────────────────────────────────────
    if cmd in ("매크로", "macro"):
        def _do_macro() -> str:
            from tele_quant.macro_pulse import (
                build_macro_section,
                fetch_macro_snapshot,
            )
            snap = fetch_macro_snapshot()
            return "📊 매크로 온도계\n\n" + build_macro_section(snap) + f"\n\n{_DISCLAIMER}"
        try:
            reply = await asyncio.get_event_loop().run_in_executor(None, _do_macro)
        except Exception as exc:
            log.warning("[inbound] macro failed: %s", exc)
            reply = f"매크로 데이터 조회 실패: {exc}"
        await _send(client, token, chat_id, reply)
        return

    # ── /포트 ─────────────────────────────────────────────────────────────────
    if cmd in ("포트", "portfolio", "포트폴리오"):
        if store is None:
            await _send(client, token, chat_id, "DB 연결이 없어 포트폴리오 조회 불가")
            return
        try:
            from tele_quant.mock_portfolio import (
                build_portfolio_section,
                get_portfolio_summary,
            )
            summary = get_portfolio_summary(store)
            section = build_portfolio_section(store)
            header = (
                f"💼 모의 포트폴리오\n"
                f"보유 {summary['open_count']}/{summary['max_positions']}  "
                f"승률 {summary['win_rate']:.0f}%  "
                f"평균수익 {summary['avg_return']:+.1f}%\n\n"
            )
            reply = header + section + f"\n\n{_DISCLAIMER}"
        except Exception as exc:
            log.warning("[inbound] portfolio failed: %s", exc)
            reply = f"포트폴리오 조회 실패: {exc}"
        await _send(client, token, chat_id, reply)
        return

    # ── /브리핑 [KR|US] ────────────────────────────────────────────────────────
    if cmd in ("브리핑", "briefing"):
        market = args.upper() if args.upper() in ("KR", "US") else "KR"
        await _send(
            client, token, chat_id,
            f"⏳ {market} 4H 브리핑 생성 중... (30초~1분 소요)",
        )
        if store is None:
            await _send(client, token, chat_id, "DB 연결이 없어 브리핑 실행 불가")
            return
        try:
            from tele_quant.briefing import run_4h_briefing
            _store, _settings, _market = store, settings, market
            reply = await asyncio.get_event_loop().run_in_executor(
                None, lambda: run_4h_briefing(_market, _store, _settings)
            )
        except Exception as exc:
            log.warning("[inbound] briefing failed: %s", exc)
            reply = f"브리핑 생성 실패: {exc}"
        await _send(client, token, chat_id, reply)
        return

    # ── /수혜주 <종목> ─────────────────────────────────────────────────────────
    if cmd in ("수혜주", "beneficiary", "chain"):
        if not args:
            await _send(client, token, chat_id, "사용법: /수혜주 삼성전자")
            return
        resolved = _resolve_symbol(args)
        if resolved is None:
            await _send(client, token, chat_id, f"'{args}' 종목을 찾을 수 없습니다.")
            return
        symbol, _market = resolved
        _sym2, _st2 = symbol, store
        reply = await asyncio.get_event_loop().run_in_executor(
            None, lambda: _find_beneficiaries(_sym2, _st2)
        )
        await _send(client, token, chat_id, reply)
        return

    # ── /피해 후보 <종목> ──────────────────────────────────────────────────────
    # cmd = "피해" 일 때 args에 "후보 <종목>" 또는 "<종목>" 이 올 수 있음
    if cmd in ("피해후보", "피해 후보", "victim", "risk", "피해"):
        # "피해 후보 NVDA" → cmd="피해", args="후보 NVDA" → args 앞에 "후보" 제거
        query = args.removeprefix("후보").strip() if args.startswith("후보") else args
        if not query:
            await _send(client, token, chat_id, "사용법: /피해 후보 NVDA  또는  /피해 후보 삼성전자")
            return
        resolved = _resolve_symbol(query)
        if resolved is None:
            await _send(client, token, chat_id, f"'{query}' 종목을 찾을 수 없습니다.")
            return
        symbol, _market = resolved
        _sym3, _st3 = symbol, store
        reply = await asyncio.get_event_loop().run_in_executor(
            None, lambda: _find_victims(_sym3, _st3)
        )
        await _send(client, token, chat_id, reply)
        return

    # ── /리포트 <종목> [deep] ──────────────────────────────────────────────────
    if cmd in ("리포트", "report"):
        _tokens_r = args.split()
        use_deep_r = False
        if _tokens_r and _tokens_r[-1].lower() in ("deep", "심층"):
            use_deep_r = True
            query_r = " ".join(_tokens_r[:-1])
        else:
            query_r = args
        if not query_r:
            await _send(
                client, token, chat_id,
                "사용법: /리포트 NVDA  또는  /리포트 005930.KS deep",
            )
            return
        resolved = _resolve_symbol(query_r)
        if resolved is None:
            await _send(client, token, chat_id, f"'{query_r}' 종목을 찾을 수 없습니다.")
            return
        symbol, market = resolved
        await _send(client, token, chat_id, f"⏳ {symbol} 기관식 리포트 생성 중... (1~3분 소요)")
        try:
            from tele_quant.analysis.report_builder import build_institutional_report
            from tele_quant.analysis.report_formatter import format_institutional_report
            _sym_r, _mkt_r, _st_r, _deep_r, _set_r = symbol, market, store, use_deep_r, settings

            def _run_report() -> list[str]:
                rpt = build_institutional_report(_sym_r, _mkt_r, _st_r, _set_r, _deep_r)
                return format_institutional_report(rpt)

            chunks = await asyncio.get_event_loop().run_in_executor(None, _run_report)
            for chunk in chunks:
                await _send(client, token, chat_id, chunk)
        except Exception as exc:
            log.warning("[inbound] report failed %s: %s", symbol, exc)
            # fallback → /분석
            try:
                from tele_quant.stock_snapshot import build_stock_snapshot, format_stock_snapshot
                _sym_f, _mkt_f, _st_f = symbol, market, store

                def _run_fallback() -> str:
                    snap = build_stock_snapshot(_sym_f, _mkt_f, _st_f, deep=False, quick=False)
                    return f"리포트 생성 실패 — /분석 결과로 대체\n\n{format_stock_snapshot(snap)}"

                reply = await asyncio.get_event_loop().run_in_executor(None, _run_fallback)
                await _send(client, token, chat_id, reply)
            except Exception as exc2:
                await _send(client, token, chat_id, f"{symbol} 리포트 생성 실패: {exc}\n분석 fallback 실패: {exc2}")
        return

    # ── /체인 <종목> ────────────────────────────────────────────────────────────
    if cmd in ("체인", "chain_report", "chainreport"):
        if not args:
            await _send(client, token, chat_id, "사용법: /체인 NVDA  또는  /체인 삼성전자")
            return
        resolved = _resolve_symbol(args)
        if resolved is None:
            await _send(client, token, chat_id, f"'{args}' 종목을 찾을 수 없습니다.")
            return
        symbol, market = resolved
        await _send(client, token, chat_id, f"⏳ {symbol} 체인 분석 중...")
        try:
            from tele_quant.analysis.chain_recommendation_engine import build_chain_candidates
            from tele_quant.analysis.report_formatter import format_chain_candidates
            from tele_quant.relation_feed import _NAME_MAP
            _sym_c, _mkt_c, _st_c = symbol, market, store

            def _run_chain() -> str:
                _name = _NAME_MAP.get(_sym_c, _sym_c)
                bens, burdens, peers = build_chain_candidates(
                    _sym_c, _mkt_c, _st_c, max_per_type=3,
                )
                return format_chain_candidates(_sym_c, _name, bens, burdens, peers)

            reply = await asyncio.get_event_loop().run_in_executor(None, _run_chain)
        except Exception as exc:
            log.warning("[inbound] chain failed %s: %s", symbol, exc)
            reply = f"{symbol} 체인 분석 실패: {exc}"
        await _send(client, token, chat_id, reply)
        return

    # ── /기관수급 <종목> ────────────────────────────────────────────────────────
    if cmd in ("기관수급", "flow", "institutional"):
        if not args:
            await _send(client, token, chat_id, "사용법: /기관수급 005930  또는  /기관수급 NVDA")
            return
        resolved = _resolve_symbol(args)
        if resolved is None:
            await _send(client, token, chat_id, f"'{args}' 종목을 찾을 수 없습니다.")
            return
        symbol, market = resolved
        await _send(client, token, chat_id, f"⏳ {symbol} 수급 분석 중...")
        try:
            from tele_quant.analysis.institutional_flow import compute_institutional_flow
            from tele_quant.analysis.report_formatter import format_institutional_flow
            from tele_quant.analysis.technical_signal_engine import (
                compute_technical_accumulation_signal,
            )
            from tele_quant.relation_feed import _NAME_MAP
            _sym_if = symbol

            def _run_flow() -> str:
                _name = _NAME_MAP.get(_sym_if, _sym_if)
                tech = compute_technical_accumulation_signal(_sym_if)
                flow = compute_institutional_flow(
                    _sym_if,
                    rsi=tech.rsi_1d,
                    ret_20d=tech.ret_20d,
                    vol_ratio=tech.vol_ratio_20d,
                    bb_pct=tech.bb_pct,
                )
                return format_institutional_flow(_sym_if, _name, flow, tech)

            reply = await asyncio.get_event_loop().run_in_executor(None, _run_flow)
        except Exception as exc:
            log.warning("[inbound] flow failed %s: %s", symbol, exc)
            reply = f"{symbol} 수급 분석 실패: {exc}"
        await _send(client, token, chat_id, reply)
        return

    # ── /수주 <종목> ──────────────────────────────────────────────────────────
    if cmd in ("수주", "backlog", "order", "수주잔고"):
        query_raw = args if args else ""
        if not query_raw:
            await _send(client, token, chat_id, "사용법: /수주 HD현대중공업  또는  /수주 329180.KS")
            return
        resolved = _resolve_symbol(query_raw)
        if resolved is None:
            await _send(client, token, chat_id, f"'{query_raw}' 종목을 찾을 수 없습니다.")
            return
        symbol, _mkt = resolved
        _sym_b, _st_b = symbol, store
        await _send(client, token, chat_id, f"⏳ {symbol} 수주잔고 조회 중...")
        try:
            from tele_quant.order_backlog import format_backlog_summary, get_backlog_for_symbol
            from tele_quant.sector_macro import detect_seed_sector

            def _run_backlog() -> str:
                _sector = detect_seed_sector(_sym_b, _st_b) if _st_b else ""
                _events = get_backlog_for_symbol(_sym_b, store=_st_b)
                if not _events:
                    return (
                        f"📋 {_sym_b} 수주잔고\n"
                        "공개자료 기준 최근 수주 정보 확인 제한.\n"
                        "DART 공시(dart.fss.or.kr) 직접 확인 권장.\n\n"
                        f"{_DISCLAIMER}"
                    )
                return format_backlog_summary(_events, sector_id=_sector or "") + f"\n\n{_DISCLAIMER}"

            reply = await asyncio.get_event_loop().run_in_executor(None, _run_backlog)
        except Exception as exc:
            log.warning("[inbound] backlog failed %s: %s", symbol, exc)
            reply = f"수주잔고 조회 실패: {exc}"
        await _send(client, token, chat_id, reply)
        return

    # ── /분석 <종목> [빠른|상세|deep|차트] ─────────────────────────────────
    query = args if cmd in ("분석", "analyze", "analysis") else text

    if not query:
        await _send(
            client, token, chat_id,
            "사용법: /분석 삼성전자  또는  /분석 NVDA\n"
            "  기본: 가격·펀더멘탈·실적·섹터분석·이슈 3개 (deep-lite)\n"
            "  /분석 NVDA 빠른  — 가격/기술/펀더멘탈 중심 (빠름)\n"
            "  /분석 NVDA 상세  — 이슈 5개·관계 후보 5개\n"
            "  /분석 NVDA deep  — DART/SEC/RSS 공시까지 심층 조회\n"
            "  /분석 NVDA 차트  — 스윙·수급·5% 기대 보상 구간 중심",
        )
        return

    # 서브 옵션 파싱: 'NVDA 빠른' / '삼성전자 상세' / 'NVDA deep' / '005930 차트'
    _sub_opt = ""
    _tokens = query.split()
    _opt_keywords = ("상세", "deep", "빠른", "basic", "chart", "차트", "기본")
    if len(_tokens) >= 2 and _tokens[-1].lower() in _opt_keywords:
        _sub_opt = _tokens[-1].lower()
        query = " ".join(_tokens[:-1])

    # 기본(/분석 NVDA)은 deep-lite=True (실적+섹터분석+이슈 포함)
    # 빠른/basic은 deep=False (가격/기술 중심)
    use_deep = _sub_opt == "deep"
    use_quick = _sub_opt in ("빠른", "basic")
    # deep-lite: 기본·상세·차트 모드 → deep=False지만 earnings/sector_intel 포함
    # (build_stock_snapshot은 deep=False여도 sector_intelligence/earnings를 항상 호출)

    resolved = _resolve_symbol(query)
    if resolved is None:
        await _send(
            client, token, chat_id,
            f"'{query}' 를 인식할 수 없습니다.\n"
            "예) /분석 삼성전자   /분석 005930   /분석 NVDA",
        )
        return

    symbol, market = resolved
    mode_label = "빠른분석" if use_quick else ("심층분석" if use_deep else "분석")
    await _send(client, token, chat_id, f"⏳ {symbol} {mode_label} 중...")
    try:
        from tele_quant.stock_snapshot import build_stock_snapshot, format_stock_snapshot
        _sym, _mkt, _st, _deep, _quick = symbol, market, store, use_deep, use_quick

        def _run() -> str:
            snap = build_stock_snapshot(_sym, _mkt, _st, deep=_deep, quick=_quick)
            return format_stock_snapshot(snap)

        reply = await asyncio.get_event_loop().run_in_executor(None, _run)
    except Exception as exc:
        log.warning("[inbound] analyze failed %s: %s", symbol, exc)
        reply = f"{symbol} 분석 실패: {exc}"
    await _send(client, token, chat_id, reply)


# ── 폴링 루프 ─────────────────────────────────────────────────────────────────

def _get_allowed_ids(settings: Settings) -> set[str]:
    """허용된 chat_id 집합 반환. 미설정이면 TELEGRAM_BOT_TARGET_CHAT_ID 사용."""
    raw = getattr(settings, "telegram_inbound_allowed_ids", "") or ""
    ids = {s.strip() for s in raw.split(",") if s.strip()}
    if not ids and settings.telegram_bot_target_chat_id:
        ids.add(str(settings.telegram_bot_target_chat_id))
    return ids


def _get_inbound_token(settings: Settings) -> str | None:
    """수신 봇 토큰 반환. 전용 설정이 없으면 기존 BOT_TOKEN 사용."""
    token = getattr(settings, "telegram_inbound_bot_token", None) or settings.telegram_bot_token
    return token


async def run_inbound_bot(settings: Settings, store: Store | None = None) -> None:
    """텔레그램 수신 봇 폴링 루프 (무한 루프, Ctrl-C로 종료).

    getUpdates long-polling 방식 사용 (webhook 불필요).
    """
    token = _get_inbound_token(settings)
    if not token:
        raise ValueError(
            "TELEGRAM_BOT_TOKEN 또는 TELEGRAM_INBOUND_BOT_TOKEN 이 설정되지 않았습니다.\n"
            ".env.local 에 TELEGRAM_BOT_TOKEN=<토큰> 을 추가하세요."
        )

    allowed_ids = _get_allowed_ids(settings)
    log.info(
        "[inbound-bot] 시작 — 허용된 chat_id: %s",
        ", ".join(allowed_ids) if allowed_ids else "(제한 없음)",
    )

    offset = 0
    retry_delay = 1.0

    async with httpx.AsyncClient(timeout=40.0) as client:
        # 봇 정보 확인
        try:
            me = await _tg_get(client, token, "getMe")
            bot_name = me.get("result", {}).get("username", "unknown")
            log.info("[inbound-bot] 연결됨 @%s", bot_name)
        except Exception as exc:
            raise RuntimeError(
                f"Telegram getMe 실패 — 토큰을 확인하세요: {mask_bot_token(str(exc))}"
            ) from exc

        while True:
            try:
                data = await _tg_get(
                    client, token, "getUpdates",
                    offset=offset, timeout=30, allowed_updates="message",
                )
                updates: list[dict[str, Any]] = data.get("result", [])
                retry_delay = 1.0  # 성공 시 리셋

                for update in updates:
                    offset = update["update_id"] + 1
                    msg = update.get("message", {})
                    chat_id = str(msg.get("chat", {}).get("id", ""))
                    text = msg.get("text", "")

                    if not text or not chat_id:
                        continue

                    # 보안: 허용된 채팅 ID만 처리
                    if allowed_ids and chat_id not in allowed_ids:
                        log.warning(
                            "[inbound-bot] 미허가 chat_id=%s — 무시 (텍스트: %s…)",
                            chat_id,
                            text[:40],
                        )
                        continue

                    log.info("[inbound-bot] 수신 chat=%s text=%s…", chat_id, text[:60])

                    # 명령 처리 (에러가 나도 루프 유지)
                    try:
                        await _handle_command(text, chat_id, client, token, store, settings)
                    except Exception as exc:
                        log.error("[inbound-bot] 명령 처리 오류: %s", exc, exc_info=True)
                        import contextlib as _cl
                        with _cl.suppress(Exception):
                            await _send(client, token, chat_id, f"처리 중 오류 발생: {exc}")

            except httpx.TimeoutException:
                # long-poll timeout은 정상 — 바로 다시 폴링
                continue
            except asyncio.CancelledError:
                log.info("[inbound-bot] 종료 신호 수신")
                break
            except Exception as exc:
                masked = mask_bot_token(str(exc))
                log.warning("[inbound-bot] 폴링 오류 (%.0fs 후 재시도): %s", retry_delay, masked)
                await asyncio.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, 60.0)  # exponential back-off
