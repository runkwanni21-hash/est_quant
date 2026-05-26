from __future__ import annotations

from typing import Annotated

import typer

from tele_quant.cli._app import app
from tele_quant.cli._common import _settings, console


@app.command("order-backlog")
def order_backlog_cmd(
    symbol: Annotated[
        str, typer.Option("--symbol", help="특정 심볼 지정 (없으면 전체 고수주잔고 레지스트리 + DB 신규 공시)")
    ] = "",
    market: Annotated[
        str, typer.Option("--market", help="KR 또는 US (symbol 없을 때 필터)")
    ] = "",
    days: Annotated[
        int, typer.Option("--days", help="최근 N일 공시 조회 범위")
    ] = 30,
    no_send: Annotated[
        bool, typer.Option("--no-send/--send", help="전송 없이 출력만")
    ] = True,
) -> None:
    """수주잔고 현황 조회 — DART(KR) + EDGAR(US) + yfinance 병렬 수집.

    Example: uv run tele-quant order-backlog
             uv run tele-quant order-backlog --symbol 329180.KS
             uv run tele-quant order-backlog --market US --days 60
    """
    from tele_quant.db import Store
    from tele_quant.order_backlog import (
        _STATIC_BACKLOG,
        build_backlog_section,
        fetch_backlog_events,
        save_backlog_events,
    )
    from tele_quant.relation_feed import _UNIVERSE_KR, _UNIVERSE_US

    settings = _settings()
    store = Store(settings.sqlite_path)
    dart_key = getattr(settings, "opendart_api_key", "") or ""

    # 대상 심볼 결정
    if symbol:
        symbols = [symbol]
    else:
        # 기본: 전체 유니버스 + 정적 레지스트리 심볼
        registry_syms = list(_STATIC_BACKLOG.keys())
        universe_syms = list(_UNIVERSE_KR) + list(_UNIVERSE_US)
        all_syms = list(dict.fromkeys(registry_syms + universe_syms))
        if market.upper() == "KR":
            symbols = [s for s in all_syms if s.endswith((".KS", ".KQ"))]
        elif market.upper() == "US":
            symbols = [s for s in all_syms if not s.endswith((".KS", ".KQ"))]
        else:
            symbols = all_syms

    console.print(f"[cyan]수주잔고 조회 시작: {len(symbols)}개 심볼, 최근 {days}일[/cyan]")

    events = fetch_backlog_events(
        symbols=symbols,
        dart_api_key=dart_key,
        lookback_days=days,
        timeout=12.0,
        max_workers=8,
    )

    saved = save_backlog_events(events, store)
    console.print(f"[green]DB 저장: {saved}건 신규[/green]")

    # 리포트 출력
    section = build_backlog_section(events, top_n=15)
    console.print(section)

    if not no_send and events:
        import asyncio

        from tele_quant.telegram_client import TelegramGateway
        from tele_quant.telegram_sender import TelegramSender

        async def _send() -> None:
            async with TelegramGateway(settings) as gateway:
                sender = TelegramSender(settings, gateway=gateway)
                await sender.send(section)

        asyncio.run(_send())
        console.print("[green]order-backlog 전송 완료[/green]")


@app.command("backlog-refresh")
def backlog_refresh_cmd(
    market: Annotated[
        str, typer.Option("--market", help="KR 또는 US (기본: 전체)")
    ] = "",
    days: Annotated[
        int, typer.Option("--days", help="최근 N일 공시 조회 범위")
    ] = 30,
    symbols: Annotated[
        str, typer.Option("--symbols", help="콤마 구분 심볼 목록 (없으면 전체 유니버스)")
    ] = "",
    save: Annotated[
        bool, typer.Option("--save/--no-save", help="DB 저장 여부")
    ] = True,
    max_workers: Annotated[
        int, typer.Option("--max-workers", help="병렬 수집 worker 수")
    ] = 6,
    source: Annotated[
        str, typer.Option("--source", help="수집 소스 필터: all|dart|edgar|yfinance|static")
    ] = "all",
    include_static: Annotated[
        bool, typer.Option("--include-static/--no-static", help="정적 레지스트리 포함 여부")
    ] = True,
    send: Annotated[
        bool, typer.Option("--send/--no-send", help="결과 텔레그램 전송 여부")
    ] = False,
) -> None:
    """수주잔고 데이터 갱신 — DART/EDGAR/yfinance 병렬 수집 후 DB 저장.

    Example: uv run tele-quant backlog-refresh
             uv run tele-quant backlog-refresh --market KR --days 60
             uv run tele-quant backlog-refresh --symbols 329180.KS,009540.KS --save
    """
    from tele_quant.db import Store
    from tele_quant.order_backlog import (
        _STATIC_BACKLOG,
        build_backlog_section,
        fetch_backlog_events,
        save_backlog_events,
    )
    from tele_quant.relation_feed import _UNIVERSE_KR, _UNIVERSE_US

    settings = _settings()
    store = Store(settings.sqlite_path)
    dart_key = getattr(settings, "opendart_api_key", "") or ""

    if symbols:
        sym_list = [s.strip() for s in symbols.split(",") if s.strip()]
    else:
        registry_syms = list(_STATIC_BACKLOG.keys())
        universe_syms = list(_UNIVERSE_KR) + list(_UNIVERSE_US)
        all_syms = list(dict.fromkeys(registry_syms + universe_syms))
        if market.upper() == "KR":
            sym_list = [s for s in all_syms if s.endswith((".KS", ".KQ"))]
        elif market.upper() == "US":
            sym_list = [s for s in all_syms if not s.endswith((".KS", ".KQ"))]
        else:
            sym_list = all_syms

    console.print(f"[cyan]backlog-refresh: {len(sym_list)}개 심볼, 최근 {days}일, 소스={source}[/cyan]")

    events = fetch_backlog_events(
        symbols=sym_list,
        dart_api_key=dart_key,
        lookback_days=days,
        timeout=15.0,
        max_workers=max_workers,
        include_static=include_static,
        sources=source,
    )
    console.print(f"수집 이벤트: {len(events)}건")

    if save:
        saved = save_backlog_events(events, store)
        console.print(f"[green]DB 저장: {saved}건 신규[/green]")

    section = build_backlog_section(events, top_n=20)
    console.print(section)

    if send and events:
        import asyncio

        from tele_quant.telegram_client import TelegramGateway
        from tele_quant.telegram_sender import TelegramSender

        async def _send() -> None:
            async with TelegramGateway(settings) as gateway:
                sender = TelegramSender(settings, gateway=gateway)
                await sender.send(section)

        asyncio.run(_send())
        console.print("[green]backlog-refresh 전송 완료[/green]")


@app.command("backlog-report")
def backlog_report_cmd(
    days: Annotated[
        int, typer.Option("--days", help="최근 N일 DB 조회 범위")
    ] = 7,
    top_n: Annotated[
        int, typer.Option("--top-n", help="상위 N개 출력")
    ] = 15,
    send: Annotated[
        bool, typer.Option("--send/--no-send", help="결과 텔레그램 전송 여부")
    ] = False,
) -> None:
    """DB에 저장된 수주잔고 이벤트 기반 리포트 생성.

    Example: uv run tele-quant backlog-report
             uv run tele-quant backlog-report --days 14 --top-n 20
             uv run tele-quant backlog-report --send
    """
    from tele_quant.db import Store
    from tele_quant.order_backlog import (
        _STATIC_BACKLOG,
        BacklogEvent,
        _static_backlog_event,
        build_backlog_section,
    )

    settings = _settings()
    store = Store(settings.sqlite_path)

    rows = store.recent_all_backlog_events(days=days)
    events: list[BacklogEvent] = []
    for r in rows:
        try:
            from datetime import datetime as _dt
            events.append(BacklogEvent(
                symbol=r.get("symbol", ""),
                market=r.get("market", ""),
                source=r.get("source", ""),
                event_date=_dt.fromisoformat(r["event_date"]),
                amount_ok_krw=r.get("amount_ok_krw"),
                amount_usd_million=r.get("amount_usd_million"),
                client=r.get("client", ""),
                contract_type=r.get("contract_type", ""),
                raw_title=r.get("raw_title", ""),
                raw_amount_text=r.get("raw_amount_text", ""),
                chain_tier=r.get("chain_tier", 1),
                backlog_tier=r.get("backlog_tier", "LOW"),
                rcept_no=r.get("rcept_no", ""),
                filing_url=r.get("filing_url", ""),
                corp_name=r.get("corp_name", ""),
                amount_ratio_to_revenue=r.get("amount_ratio_to_revenue"),
                contract_start=r.get("contract_start", ""),
                contract_end=r.get("contract_end", ""),
                parsed_confidence=r.get("parsed_confidence", "LOW"),
                is_amendment=bool(r.get("is_amendment", 0)),
                is_cancellation=bool(r.get("is_cancellation", 0)),
                cik=r.get("cik", ""),
                accession_no=r.get("accession_no", ""),
                source_raw_hash=r.get("source_raw_hash", ""),
            ))
        except Exception:
            pass

    # Fallback: static registry if DB empty
    if not events:
        for sym in _STATIC_BACKLOG:
            ev = _static_backlog_event(sym)
            if ev:
                events.append(ev)

    console.print(f"[cyan]backlog-report: DB {len(rows)}건 + 정적 fallback ({len(events)}건 합계)[/cyan]")
    section = build_backlog_section(events, top_n=top_n)
    console.print(section)

    if send and events:
        import asyncio

        from tele_quant.telegram_client import TelegramGateway
        from tele_quant.telegram_sender import TelegramSender

        async def _send() -> None:
            async with TelegramGateway(settings) as gateway:
                sender = TelegramSender(settings, gateway=gateway)
                await sender.send(section)

        asyncio.run(_send())
        console.print("[green]backlog-report 전송 완료[/green]")


@app.command("backlog-audit")
def backlog_audit_cmd(
    fail_on_high: Annotated[
        bool, typer.Option("--fail-on-high", help="HIGH 이슈 발견 시 exit-code 1")
    ] = False,
) -> None:
    """수주잔고 수집 설정 감사 — API 키, pblntf_ty, 신뢰도 비율 등 점검.

    Example: uv run tele-quant backlog-audit
             uv run tele-quant backlog-audit --fail-on-high
    """
    from rich.table import Table

    from tele_quant.db import Store
    from tele_quant.order_backlog import run_backlog_audit

    settings = _settings()
    store = Store(settings.sqlite_path)

    issues = run_backlog_audit(store=store)

    if not issues:
        console.print("[green]backlog-audit: 이슈 없음[/green]")
        return

    table = Table(title="backlog-audit 결과", show_lines=True)
    table.add_column("심각도", style="bold", min_width=6)
    table.add_column("항목", min_width=20)
    table.add_column("메시지", min_width=40)

    _colors = {"HIGH": "red", "MEDIUM": "yellow", "LOW": "cyan", "INFO": "dim"}
    for row in sorted(issues, key=lambda x: (x.get("severity", "LOW"), x.get("check", x.get("key", "")))):
        color = _colors.get(row.get("severity", "LOW"), "white")
        table.add_row(
            f"[{color}]{row.get('severity', '?')}[/{color}]",
            row.get("check", row.get("key", "")),
            row.get("detail", row.get("message", "")),
        )
    console.print(table)

    high_count = sum(1 for i in issues if i.get("severity") == "HIGH")
    console.print(f"총 이슈: {len(issues)}개 (HIGH {high_count}개)")
    if fail_on_high and high_count > 0:
        raise SystemExit(1)
