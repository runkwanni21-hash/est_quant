from __future__ import annotations

import asyncio
from datetime import UTC
from typing import Annotated

import httpx
import typer
from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn
from rich.table import Table

from tele_quant.cli._app import app
from tele_quant.cli._common import _settings, console
from tele_quant.ollama_client import OllamaClient
from tele_quant.pipeline import TeleQuantPipeline
from tele_quant.telegram_client import TelegramGateway
from tele_quant.telegram_sender import TelegramSender
from tele_quant.textutil import mask_bot_token


@app.command()
def doctor() -> None:
    """환경 설정을 빠르게 점검합니다."""
    settings = _settings()
    table = Table(title="Tele Quant Doctor")
    table.add_column("Item")
    table.add_column("Status")
    table.add_row("TELEGRAM_API_ID", "OK" if settings.telegram_api_id else "MISSING")
    table.add_row("TELEGRAM_API_HASH", "OK" if settings.telegram_api_hash else "MISSING")
    table.add_row("SEND_MODE", settings.telegram_send_mode)
    table.add_row("BOT_TOKEN", "설정됨" if settings.telegram_bot_token else "없음")
    table.add_row("SOURCE_CHATS", str(len(settings.source_chats)))
    table.add_row("INCLUDE_ALL_CHANNELS", str(settings.telegram_include_all_channels))
    table.add_row("ANALYSIS_ENABLED", str(settings.analysis_enabled))
    table.add_row("DIGEST_CHUNK_SIZE", str(settings.digest_chunk_size))
    table.add_row("OLLAMA_HOST", settings.ollama_host)
    table.add_row("SQLITE_PATH", str(settings.sqlite_path))
    table.add_row("INTRADAY_TECH_ENABLED", str(settings.intraday_tech_enabled))
    table.add_row("INTRADAY_PERIOD", settings.intraday_period)
    table.add_row("INTRADAY_INTERVAL", settings.intraday_interval)
    table.add_row("WEEKEND_MACRO_ONLY", str(settings.weekend_macro_only))
    console.print(table)

    collect_issues = settings.validate_minimum(mode="collect")
    send_issues = settings.validate_minimum(mode="send")
    if collect_issues or send_issues:
        console.print("[yellow]텔레그램 미설정 (yfinance 기반 기능은 동작합니다):[/yellow]")
        for issue in collect_issues + send_issues:
            console.print(f"  [dim]- {issue}[/dim]")
    else:
        console.print("[green]기본 설정 OK[/green]")

    async def check_ollama() -> None:
        ok = await OllamaClient(settings).health()
        console.print(f"Ollama: {'[green]OK[/green]' if ok else '[red]연결 실패[/red]'}")

    asyncio.run(check_ollama())


@app.command()
def auth() -> None:
    """텔레그램 사용자 계정 로그인을 1회 수행합니다."""

    async def run() -> None:
        settings = _settings()
        async with TelegramGateway(settings):
            console.print("[green]텔레그램 로그인/세션 생성 완료[/green]")

    asyncio.run(run())


@app.command("list-chats")
def list_chats(
    limit: Annotated[int, typer.Option("--limit", help="가져올 대화/채널 수")] = 300,
    only_channels: Annotated[bool, typer.Option("--only-channels/--all-dialogs")] = True,
) -> None:
    """내 계정이 볼 수 있는 텔레그램 채널 목록을 보여줍니다."""

    async def run() -> None:
        settings = _settings()
        async with TelegramGateway(settings) as gateway:
            rows = await gateway.list_dialogs(limit=limit, only_channels=only_channels)
        table = Table(title="Telegram chats/channels")
        table.add_column("id", overflow="fold")
        table.add_column("username")
        table.add_column("title")
        table.add_column("type")
        table.add_column("unread", justify="right")
        for row in rows:
            table.add_row(
                str(row.get("id") or ""),
                row.get("username") or "",
                row.get("title") or "",
                row.get("type") or "",
                str(row.get("unread") or 0),
            )
        console.print(table)
        console.print(
            "\n.env.local의 TELEGRAM_SOURCE_CHATS에는 username 또는 id를 쉼표로 넣으면 됩니다."
        )

    asyncio.run(run())


@app.command()
def once(
    send: Annotated[
        bool, typer.Option("--send/--no-send", help="요약을 텔레그램으로 보낼지")
    ] = True,
    hours: Annotated[
        float | None, typer.Option("--hours", help="몇 시간 전까지 볼지. 기본은 .env.local")
    ] = None,
    macro_only: Annotated[
        bool,
        typer.Option("--macro-only/--full", help="매크로 다이제스트만 전송, 종목 분석 생략"),
    ] = False,
) -> None:
    """수집→중복제거→Ollama 요약을 1회 실행합니다. ANALYSIS_ENABLED=true이면 종목 시나리오도 전송."""

    async def run() -> None:
        settings = _settings()
        pipeline = TeleQuantPipeline(settings)
        digest, analysis = await pipeline.run_once(send=send, hours=hours, macro_only=macro_only)
        console.rule("[dim]Digest Preview[/dim]")
        console.print(mask_bot_token(digest))
        if analysis:
            console.rule("[dim]Analysis Preview[/dim]")
            console.print(analysis)
        elif macro_only:
            console.print("[dim]macro-only 모드: 종목 분석 생략[/dim]")

    asyncio.run(run())


@app.command()
def loop() -> None:
    """DIGEST_INTERVAL_HOURS(기본 4시간) 간격으로 계속 실행합니다."""

    async def run() -> None:
        settings = _settings()
        pipeline = TeleQuantPipeline(settings)
        await pipeline.run_loop()

    asyncio.run(run())


@app.command()
def analyze(
    send: Annotated[
        bool, typer.Option("--send/--no-send", help="분석 메시지를 텔레그램으로 보낼지")
    ] = False,
    hours: Annotated[float | None, typer.Option("--hours", help="몇 시간 전까지 볼지")] = None,
) -> None:
    """데이터를 수집하고 종목 시나리오 분석만 실행합니다."""

    async def run() -> None:
        settings = _settings()
        pipeline = TeleQuantPipeline(settings)
        # run_once with analysis enabled but we only send analysis message
        _, analysis = await pipeline.run_once(send=False, hours=hours)
        if analysis:
            if send:
                async with TelegramGateway(settings) as gateway:
                    sender = TelegramSender(settings, gateway=gateway)
                    await sender.send(analysis)
                console.print("[green]분석 메시지 전송 완료[/green]")
            console.rule("[dim]Analysis[/dim]")
            console.print(analysis)
        else:
            console.print(
                "[yellow]분석할 종목 후보가 없습니다. (최소 점수 미달 또는 데이터 없음)[/yellow]"
            )

    asyncio.run(run())


@app.command()
def candidates(
    hours: Annotated[float | None, typer.Option("--hours", help="몇 시간 전까지 볼지")] = None,
    use_llm: Annotated[
        bool,
        typer.Option("--llm/--no-llm", help="LLM 정밀 추출 사용 (느림, 기본: AliasBook 빠른 추출)"),
    ] = False,
    expanded: Annotated[
        bool,
        typer.Option("--expanded/--no-expanded", help="상관관계/섹터 확장 후보 포함"),
    ] = False,
) -> None:
    """종목 후보 목록을 표로 보여줍니다.

    기본(--no-llm): AliasBook 기반 빠른 추출 (Ollama 없이 10초 내외).
    --llm: LLM 정밀 추출 (느리지만 더 풍부한 결과).
    --expanded: 상관관계·섹터 확장 후보까지 포함.
    """

    async def run() -> None:
        settings = _settings()
        pipeline = TeleQuantPipeline(settings)
        cands = await pipeline.run_candidates(hours=hours, use_llm=use_llm, expanded=expanded)
        if not cands:
            console.print("[yellow]언급된 종목 후보가 없습니다.[/yellow]")
            return

        if expanded:
            table = Table(title=f"종목 후보 ({len(cands)}개, 확장 포함)")
            table.add_column("종목명")
            table.add_column("심볼")
            table.add_column("시장")
            table.add_column("섹터")
            table.add_column("출처")
            table.add_column("언급", justify="right")
            table.add_column("호재수", justify="right")
            table.add_column("리스크수", justify="right")
            table.add_column("상관피어")
            for c in cands:
                sector = getattr(c, "sector", "") or "미분류"
                origin = getattr(c, "origin", "") or ""
                peer_parent = getattr(c, "correlation_parent", "") or ""
                peer_val = getattr(c, "correlation_value", None)
                if peer_parent and peer_val is not None:
                    peer = f"{peer_parent}({peer_val:.2f})"
                else:
                    peer = peer_parent
                table.add_row(
                    c.name or "",
                    c.symbol,
                    c.market,
                    sector,
                    origin,
                    str(c.mentions),
                    str(len(c.catalysts)),
                    str(len(c.risks)),
                    peer,
                )
        else:
            table = Table(title=f"종목 후보 ({len(cands)}개)")
            table.add_column("종목명")
            table.add_column("심볼")
            table.add_column("시장")
            table.add_column("언급횟수", justify="right")
            table.add_column("심리")
            table.add_column("호재수", justify="right")
            table.add_column("리스크수", justify="right")
            for c in cands:
                table.add_row(
                    c.name or "",
                    c.symbol,
                    c.market,
                    str(c.mentions),
                    c.sentiment,
                    str(len(c.catalysts)),
                    str(len(c.risks)),
                )
        console.print(table)

    asyncio.run(run())


@app.command("test-send")
def test_send() -> None:
    """텔레그램 전송만 테스트합니다."""

    async def run() -> None:
        settings = _settings()
        async with TelegramGateway(settings) as gateway:
            sender = TelegramSender(settings, gateway=gateway)
            await sender.send("Tele Quant 전송 테스트 ✅")
        console.print("[green]전송 완료[/green]")

    asyncio.run(run())


@app.command("bot-chat-id")
def bot_chat_id() -> None:
    """BotFather 봇의 getUpdates 결과에서 chat_id를 찾습니다."""

    async def run() -> None:
        settings = _settings()
        sender = TelegramSender(settings)
        updates = await sender.get_bot_updates()
        if not updates:
            console.print("봇에게 /start를 보낸 뒤 다시 실행하세요.")
            return
        table = Table(title="Bot updates")
        table.add_column("chat_id")
        table.add_column("from")
        table.add_column("text")
        for update in updates[-10:]:
            msg = update.get("message") or update.get("channel_post") or {}
            chat = msg.get("chat") or {}
            user = msg.get("from") or {}
            table.add_row(
                str(chat.get("id", "")),
                user.get("username") or user.get("first_name") or "",
                msg.get("text", ""),
            )
        console.print(table)

    asyncio.run(run())


@app.command()
def evidence(
    hours: Annotated[float | None, typer.Option("--hours", help="몇 시간 전까지 볼지")] = None,
) -> None:
    """EvidenceCluster 목록을 표로 출력합니다. (압축된 증거 묶음 확인)"""

    async def run() -> None:
        settings = _settings()
        pipeline = TeleQuantPipeline(settings)

        lookback = hours if hours is not None else settings.fetch_lookback_hours
        issues = settings.validate_minimum()
        if issues:
            console.print("[red]설정 오류: " + "; ".join(issues) + "[/red]")
            return

        from tele_quant.evidence import build_evidence_clusters

        async with TelegramGateway(settings) as gateway:
            kept, stats = await pipeline._collect_and_dedupe(gateway, lookback)

        clusters = build_evidence_clusters(kept, settings)

        table = Table(title=f"Evidence Clusters ({len(clusters)}개, {lookback}h)")
        table.add_column("ID", overflow="fold")
        table.add_column("극성")
        table.add_column("티커")
        table.add_column("테마")
        table.add_column("출처수", justify="right")
        table.add_column("점수", justify="right")
        table.add_column("헤드라인")

        for c in clusters[:40]:
            pol_icon = {"positive": "📈", "negative": "📉", "neutral": "📌"}.get(c.polarity, "")
            table.add_row(
                c.cluster_id,
                pol_icon + c.polarity,
                ",".join(c.tickers[:3]),
                ",".join(c.themes[:3]),
                str(c.source_count),
                f"{c.cluster_score:.1f}",
                c.headline[:50],
            )
        console.print(table)
        console.print(
            f"수집: tg={stats.telegram_items} naver={stats.report_items} dedup후={stats.kept_items}"
        )

    asyncio.run(run())


@app.command()
def sources(
    hours: Annotated[float | None, typer.Option("--hours", help="몇 시간 전까지 볼지")] = None,
) -> None:
    """채널별 수집량 / 품질점수 / 드롭 현황을 표로 출력합니다."""

    async def run() -> None:
        settings = _settings()
        lookback = hours if hours is not None else settings.fetch_lookback_hours
        issues = settings.validate_minimum()
        if issues:
            console.print("[red]설정 오류: " + "; ".join(issues) + "[/red]")
            return

        from tele_quant.source_quality import score_source_message

        async with TelegramGateway(settings) as gateway:
            raw_items = await gateway.fetch_recent_messages(hours=lookback)

        # Per-source aggregation
        source_stats: dict[str, dict] = {}
        for item in raw_items:
            sn = item.source_name
            if sn not in source_stats:
                source_stats[sn] = {"total": 0, "dropped": 0, "scores": []}
            sc = score_source_message(sn, item.text)
            source_stats[sn]["total"] += 1
            source_stats[sn]["scores"].append(sc)
            if settings.source_quality_enabled and sc < settings.source_quality_min_score:
                source_stats[sn]["dropped"] += 1

        table = Table(title=f"Source Stats ({len(source_stats)}채널, {lookback}h)")
        table.add_column("채널명")
        table.add_column("수집", justify="right")
        table.add_column("드롭", justify="right")
        table.add_column("평균점수", justify="right")

        sorted_sources = sorted(source_stats.items(), key=lambda x: x[1]["total"], reverse=True)
        for sn, st in sorted_sources[:30]:
            scores = st["scores"]
            avg = sum(scores) / len(scores) if scores else 0.0
            table.add_row(sn[:40], str(st["total"]), str(st["dropped"]), f"{avg:.1f}")

        console.print(table)

    asyncio.run(run())


@app.command("validate-tickers")
def validate_tickers() -> None:
    """config/ticker_aliases.yml의 모든 심볼을 yfinance로 검증합니다."""
    import yfinance as yf

    from tele_quant.analysis.aliases import load_alias_config

    settings = _settings()
    try:
        book = load_alias_config()
    except FileNotFoundError:
        console.print(
            f"[red]ticker_aliases.yml을 찾을 수 없습니다: {settings.ticker_aliases_path}[/red]"
        )
        return

    all_syms = book.all_symbols
    results: list[tuple[str, str, str, bool]] = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("yfinance 검증 중…", total=len(all_syms))
        for sym_def in all_syms:
            try:
                hist = yf.Ticker(sym_def.symbol).history(period="5d", auto_adjust=True)
                ok = not hist.empty
            except Exception:
                ok = False
            results.append((sym_def.symbol, sym_def.name, sym_def.market, ok))
            progress.advance(task)

    table = Table(title="Ticker Validation")
    table.add_column("Symbol", overflow="fold")
    table.add_column("Name")
    table.add_column("Market")
    table.add_column("Status", justify="center")

    failed = 0
    for symbol, name, market, ok in results:
        status = "[green]OK[/green]" if ok else "[red]FAIL[/red]"
        table.add_row(symbol, name, market, status)
        if not ok:
            failed += 1

    console.print(table)
    if failed:
        console.print(
            f"[yellow]{failed}/{len(results)}개 심볼 데이터 없음 (상폐·이름변경 확인)[/yellow]"
        )
    else:
        console.print(f"[green]전체 {len(results)}개 심볼 검증 OK[/green]")


@app.command()
def providers() -> None:
    """외부 API provider 설정 현황을 표로 출력합니다."""
    from tele_quant.provider_config import available_providers

    result = available_providers(load_external=True)
    table = Table(title="API Providers")
    table.add_column("Provider")
    table.add_column("Status", justify="center")
    for name in [
        "yfinance",
        "fred",
        "finnhub",
        "fmp",
        "alpha_vantage",
        "polygon",
        "newsapi",
        "naver",
    ]:
        enabled = result.get(name, False)
        status = "[green]enabled[/green]" if enabled else "[dim]disabled[/dim]"
        table.add_row(name, status)
    console.print(table)
    console.print("[dim]키 값은 절대 출력하지 않습니다. 존재 여부만 확인합니다.[/dim]")


@app.command("ollama-tags")
def ollama_tags() -> None:
    """Ollama에 설치된 모델 목록을 보여줍니다."""

    async def run() -> None:
        settings = _settings()
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{settings.ollama_host.rstrip('/')}/api/tags")
            resp.raise_for_status()
            data = resp.json()
        table = Table(title="Ollama models")
        table.add_column("name")
        table.add_column("size")
        for model in data.get("models", []):
            table.add_row(model.get("name", ""), str(model.get("size", "")))
        console.print(table)

    asyncio.run(run())


@app.command()
def watchlist() -> None:
    """config/watchlist.yml의 관심종목 그룹·섹터·시간대 초점을 표로 출력합니다."""
    from datetime import datetime

    from rich.table import Table

    from tele_quant.watchlist import load_watchlist, report_focus_for_hour

    settings = _settings()
    cfg = load_watchlist(settings.watchlist_path)
    if cfg is None:
        console.print(f"[red]watchlist.yml을 불러올 수 없습니다: {settings.watchlist_path}[/red]")
        return

    # 그룹별 종목 표
    table = Table(title="Watchlist 그룹 현황")
    table.add_column("그룹 키")
    table.add_column("라벨")
    table.add_column("종목 수", justify="right")
    table.add_column("종목 목록")

    for key, grp in cfg.groups.items():
        table.add_row(
            key,
            grp.label,
            str(len(grp.symbols)),
            ", ".join(grp.symbols[:8]) + ("…" if len(grp.symbols) > 8 else ""),
        )
    console.print(table)

    # 선호 섹터
    if cfg.prefer_sectors:
        console.print("\n[bold]선호 섹터:[/bold] " + ", ".join(cfg.prefer_sectors))

    # 리포트 스타일
    console.print(f"[bold]최대 후보 수:[/bold] {cfg.max_candidates}")
    console.print(f"[bold]관심종목 우선 표시:[/bold] {cfg.show_watchlist_first}")

    # 시간대별 focus
    focus_table = Table(title="시간대별 리포트 초점")
    focus_table.add_column("시간대")
    focus_table.add_column("라벨")
    focus_table.add_column("초점")

    for hour_key, ctx in sorted(cfg.schedule_context.items()):
        focus_table.add_row(
            f"{hour_key}시",
            ctx.get("label", ""),
            ", ".join(ctx.get("focus", [])[:3]),
        )
    console.print(focus_table)

    # 현재 시간 초점
    now_hour = datetime.now(UTC).hour
    cur_focus = report_focus_for_hour(now_hour, cfg)
    if cur_focus:
        console.print(
            f"\n[green]현재({now_hour}시) 초점:[/green] {', '.join(cur_focus.get('focus', []))}"
        )

    if cfg.disclaimer:
        console.print(f"\n[dim]{cfg.disclaimer}[/dim]")
