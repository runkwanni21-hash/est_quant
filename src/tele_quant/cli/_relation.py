from __future__ import annotations

import asyncio
from typing import Annotated

import typer

from tele_quant.cli._app import app
from tele_quant.cli._common import _settings, console
from tele_quant.telegram_sender import TelegramSender


@app.command("relation-feed")
def relation_feed_cmd(
    send: Annotated[
        bool,
        typer.Option("--send/--no-send", help="요약을 텔레그램으로 전송할지"),
    ] = False,
    no_fallback: Annotated[
        bool,
        typer.Option("--no-fallback", help="fallback lead-lag 계산 생략"),
    ] = False,
    fallback_only: Annotated[
        bool,
        typer.Option("--fallback-only", help="fallback 후보만 표시 (stock feed 표 숨김)"),
    ] = False,
    force_fallback: Annotated[
        bool,
        typer.Option("--force-fallback", help="stock feed leadlag가 있어도 fallback 강제 계산"),
    ] = False,
    review: Annotated[
        bool,
        typer.Option("--review/--no-review", help="저장된 relation 신호 성과 리뷰 표시"),
    ] = False,
    limit: Annotated[
        int,
        typer.Option("--limit", help="stock feed lead-lag 표 최대 출력 행 수 (0=전체)"),
    ] = 20,
    show_all: Annotated[
        bool,
        typer.Option("--all", help="stock feed lead-lag 표 전체 출력 (--limit 무시)"),
    ] = False,
) -> None:
    """stock-relation-ai 공유 피드를 읽고 급등·급락 후행 후보를 출력합니다."""
    from tele_quant.relation_feed import build_relation_feed_section, load_relation_feed
    from tele_quant.telegram_client import TelegramGateway

    settings = _settings()
    feed = load_relation_feed(settings)

    if not feed.available:
        console.print("[yellow]relation feed 없음[/yellow]")
        for w in feed.load_warnings:
            console.print(f"  - {w}")
        return

    summary = feed.summary
    assert summary is not None

    # Compute fallback when appropriate
    should_compute_fallback = (
        not no_fallback and feed.movers and (not feed.leadlag or force_fallback)
    )
    if should_compute_fallback:
        try:
            from dataclasses import replace

            from tele_quant.local_data import load_correlation, load_price_history
            from tele_quant.relation_fallback import compute_fallback_leadlag

            price_store = load_price_history(settings)
            corr_store = load_correlation(settings)
            feed_for_fallback = (
                replace(feed, leadlag=[]) if (fallback_only or force_fallback) else feed
            )
            feed.fallback_candidates = compute_fallback_leadlag(
                feed_for_fallback, settings, price_store, corr_store
            )
        except Exception as _fb_exc:
            console.print(f"[yellow]fallback 계산 실패: {type(_fb_exc).__name__}[/yellow]")

    fb = feed.fallback_candidates

    # Summary table
    from rich.table import Table
    table = Table(title="Relation Feed Summary (자체 계산)")
    table.add_column("항목")
    table.add_column("값")
    table.add_row("기준일", summary.asof_date)
    table.add_row("생성일시", summary.generated_at)
    table.add_row("스캔 종목", str(summary.price_rows))
    table.add_row("급등락 모버", str(len(feed.movers)))
    table.add_row("상관관계 후보", str(len(fb)))
    if no_fallback:
        fallback_status = "생략 (--no-fallback)"
    elif fb:
        fallback_status = f"계산됨 ({len(fb)}건)"
    elif should_compute_fallback:
        fallback_status = "계산됨 (0건)"
    else:
        fallback_status = "후보 없음"
    table.add_row("lead-lag 계산", fallback_status)
    if fb:
        med = sum(1 for c in fb if c.confidence == "medium")
        low = sum(1 for c in fb if c.confidence == "low")
        table.add_row("신뢰도", f"medium={med} / low={low}")
    table.add_row("status", summary.status)
    if summary.warnings:
        table.add_row("warnings", ", ".join(summary.warnings))
    console.print(table)

    # Stock feed lead-lag table (hidden when --fallback-only)
    if fallback_only:
        if feed.leadlag and not force_fallback:
            console.print(
                f"[dim]stock feed leadlag가 {len(feed.leadlag)}개 존재하므로 fallback 계산 생략."
                " --force-fallback으로 강제 계산 가능[/dim]"
            )
    elif feed.leadlag:
        display_limit = 0 if show_all else max(limit, 0)
        seen_pairs: set[tuple[str, str]] = set()
        rows_to_display: list = []
        for r in feed.leadlag:
            pair = (r.source_symbol, r.target_symbol)
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)
            rows_to_display.append(r)
            if display_limit and len(rows_to_display) >= display_limit:
                break

        total_unique = sum(1 for r in {(r.source_symbol, r.target_symbol) for r in feed.leadlag})
        caption = (
            f"전체 {total_unique}개"
            if show_all or display_limit == 0 or len(rows_to_display) >= total_unique
            else f"총 {total_unique}개 중 상위 {len(rows_to_display)}개 표시 (--all로 전체 출력)"
        )
        ll_table = Table(
            title=f"Stock Feed Lead-Lag 후보 ({len(feed.leadlag)}개)",
            caption=caption,
        )
        ll_table.add_column("source")
        ll_table.add_column("등락률", justify="right")
        ll_table.add_column("move")
        ll_table.add_column("target")
        ll_table.add_column("relation")
        ll_table.add_column("lag", justify="right")
        ll_table.add_column("prob", justify="right")
        ll_table.add_column("lift", justify="right")
        ll_table.add_column("conf")
        ll_table.add_column("note")

        for r in rows_to_display:
            src_name = (r.source_name or r.source_symbol)[:20]
            tgt_name = (r.target_name or r.target_symbol)[:20]
            sign = "+" if r.source_move_type == "UP" else "-"
            ll_table.add_row(
                f"{src_name} / {r.source_symbol}",
                f"{sign}{abs(r.source_return_pct):.1f}%",
                r.source_move_type,
                f"{tgt_name} / {r.target_symbol}",
                r.relation_type[:15],
                str(r.lag_days),
                f"{r.conditional_prob:.1%}",
                f"{r.lift:.2f}x",
                r.confidence,
                r.note[:30] if r.note else "",
            )
        console.print(ll_table)
    elif not feed.leadlag and not fb:
        console.print("[yellow]lead-lag 후보 없음[/yellow]")

    # Fallback table
    if fb:
        fb_table = Table(
            title=f"Tele Quant Fallback 후보 ({len(fb)}개)",
            caption="self-computed / max confidence: medium",
        )
        fb_table.add_column("source")
        fb_table.add_column("return", justify="right")
        fb_table.add_column("target")
        fb_table.add_column("relation")
        fb_table.add_column("market_path")
        fb_table.add_column("lag", justify="right")
        fb_table.add_column("prob", justify="right")
        fb_table.add_column("base", justify="right")
        fb_table.add_column("lift", justify="right")
        fb_table.add_column("events", justify="right")
        fb_table.add_column("conf")

        for c in fb:
            sign = "+" if c.source_move_type == "UP" else ""
            src_disp = (c.source_name or c.source_symbol)[:18]
            fb_table.add_row(
                f"{src_disp} / {c.source_symbol}",
                f"{sign}{c.source_return_pct:.1f}%",
                c.target_symbol,
                c.relation_type[:14],
                c.market_path,
                str(c.lag_days),
                f"{c.conditional_prob:.1%}",
                f"{c.base_prob:.1%}",
                f"{c.lift:.2f}x",
                str(c.event_count),
                c.confidence,
            )
        console.print(fb_table)

    # Full section preview
    section = build_relation_feed_section(feed, settings=settings)
    if section:
        console.rule("[dim]섹션 미리보기[/dim]")
        console.print(section)

    if send:
        async def _send() -> None:
            async with TelegramGateway(settings) as gateway:
                sender = TelegramSender(settings, gateway=gateway)
                await sender.send(section)
            console.print("[green]relation feed 섹션 전송 완료[/green]")

        asyncio.run(_send())

    if review:
        from datetime import timedelta

        from tele_quant.db import Store
        from tele_quant.models import utc_now
        from tele_quant.weekly import build_relation_signal_review_section

        _store = Store(settings.sqlite_path)
        _since = utc_now() - timedelta(days=7)
        _review_section = build_relation_signal_review_section(_store, since=_since)
        console.rule("[dim]Relation Signal 성과 리뷰 (최근 7일)[/dim]")
        console.print(_review_section)


@app.command("pair-watch")
def pair_watch_cmd(
    sector: Annotated[
        str | None,
        typer.Option("--sector", help="섹터 필터: semiconductor|ess|cosmetics|defense"),
    ] = None,
    hours: Annotated[
        float | None,
        typer.Option("--hours", help="4H 기준 시간 (현재는 universe 가격 기준이므로 참고용)"),
    ] = None,
    send: Annotated[
        bool,
        typer.Option("--send/--no-send", help="관찰 섹션을 텔레그램으로 전송할지"),
    ] = False,
    no_db: Annotated[
        bool,
        typer.Option("--no-db", help="DB에 신호를 저장하지 않음"),
    ] = False,
) -> None:
    """선행·후행 페어 관찰 후보를 실시간으로 계산하고 표시합니다.

    출력: source / source_return / target / target_return / gap / prob / lift / confidence / action

    예: source NVDA +5.1% → target SK하이닉스 +0.6%, gap=미반응, confidence=medium, action=4H 확인 후보
    """
    from tele_quant.live_pair_watch import (
        build_pair_watch_section,
        format_signal_oneline,
        run_pair_watch,
    )
    from tele_quant.telegram_client import TelegramGateway

    settings = _settings()

    async def run() -> None:
        relation_feed = None
        try:
            from tele_quant.relation_feed import load_relation_feed

            relation_feed = load_relation_feed(settings)
        except Exception:
            pass

        corr_store = None
        try:
            from tele_quant.local_data import load_correlation

            corr_store = load_correlation(settings)
        except Exception:
            pass

        signals, used_stale, diagnostics = run_pair_watch(
            settings,
            sector_filter=sector,
            relation_feed=relation_feed,
            corr_store=corr_store,
        )

        if diagnostics:
            for d in diagnostics:
                console.print(f"[yellow]⚠ {d}[/yellow]")

        if used_stale:
            console.print("[dim]일부 가격 캐시 사용[/dim]")

        if not signals:
            console.print("[yellow]현재 기준 충족 pair-watch 신호 없음[/yellow]")
            console.print("[dim](source 움직임 부족 또는 min_confidence 미달)[/dim]")
            return

        from rich.table import Table
        table = Table(title=f"선행·후행 페어 관찰 ({len(signals)}개 신호)")
        table.add_column("source")
        table.add_column("4H 등락", justify="right")
        table.add_column("1D 등락", justify="right")
        table.add_column("→ target")
        table.add_column("target 4H", justify="right")
        table.add_column("gap")
        table.add_column("prob", justify="right")
        table.add_column("lift", justify="right")
        table.add_column("confidence")
        table.add_column("action")

        from tele_quant.live_pair_watch import _fmt_return

        for sig in signals:
            prob_str = f"{sig.conditional_prob:.1%}" if sig.conditional_prob is not None else "N/A"
            lift_str = f"{sig.lift:.1f}x" if sig.lift is not None else "N/A"
            action_short = (
                sig.watch_action.split(" — ")[0] if " — " in sig.watch_action else sig.watch_action
            )[:20]
            gap_color = {
                "미반응": "green",
                "약세전이미확인": "yellow",
                "부분반응": "blue",
                "현재불일치": "red",
                "불일치": "red",
                "이미반응": "dim",
            }.get(sig.gap_type, "white")
            is_rule_based = sig.conditional_prob is None and sig.lift is None
            conf_display = "규칙기반" if is_rule_based else sig.confidence
            table.add_row(
                f"{sig.source_name[:16]} / {sig.source_symbol}",
                _fmt_return(sig.source_return_4h),
                _fmt_return(sig.source_return_1d),
                f"{sig.target_name[:16]} / {sig.target_symbol}",
                _fmt_return(sig.target_return_4h),
                f"[{gap_color}]{sig.gap_type}[/{gap_color}]",
                prob_str,
                lift_str,
                conf_display,
                action_short,
            )
        console.print(table)

        # One-liner summary
        console.rule("[dim]요약[/dim]")
        for sig in signals[:5]:
            console.print(format_signal_oneline(sig))

        # Section preview
        section = build_pair_watch_section(
            signals,
            settings=settings,
            used_stale_cache=used_stale,
            diagnostics=diagnostics,
        )
        if section:
            console.rule("[dim]섹션 미리보기[/dim]")
            console.print(section)

        # DB save
        if not no_db:
            try:
                from tele_quant.db import Store

                store = Store(settings.sqlite_path)
                saved = store.save_pair_watch_signals(signals)
                if saved:
                    console.print(f"[green]pair_watch_history 저장: {saved}건[/green]")
            except Exception as exc:
                console.print(f"[yellow]DB 저장 실패: {exc}[/yellow]")

        # Telegram send
        if send and section:
            async with TelegramGateway(settings) as gateway:
                sender = TelegramSender(settings, gateway=gateway)
                await sender.send(section)
            console.print("[green]pair-watch 섹션 전송 완료[/green]")

    asyncio.run(run())


@app.command("pair-watch-cleanup")
def pair_watch_cleanup_cmd(
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run/--apply", help="--dry-run: 변경 없이 통계만 / --apply: 실제 정리"),
    ] = True,
) -> None:
    """pair_watch_history 중복 제거 및 레거시 가격 미기록 row 정리.

    예:
      uv run tele-quant pair-watch-cleanup --dry-run
      uv run tele-quant pair-watch-cleanup --apply
    """
    from tele_quant.db import Store

    settings = _settings()
    store = Store(settings.sqlite_path)

    stats = store.pair_watch_cleanup_stats()

    console.print("\n[bold cyan]Pair-watch cleanup[/bold cyan]")
    console.print(f"  total rows (active):         {stats['total_active']}")
    console.print(f"  duplicate groups:            {stats['duplicate_groups']}")
    console.print(f"  archived duplicates (dry):   {stats['duplicate_rows_to_archive']}")
    console.print(f"  price missing:               {stats['price_missing']}")
    console.print(f"  unverified legacy:           {stats['unverified_legacy']}")

    if dry_run:
        console.print("\n[yellow]--dry-run 모드: DB 변경 없음. --apply 옵션으로 실행하세요.[/yellow]")
        return

    result = store.pair_watch_cleanup_apply()
    console.print("\n[bold green]cleanup --apply 완료[/bold green]")
    console.print(f"  archived duplicates:          {result['archived']}")
    console.print(f"  legacy_missing_price marked:  {result['legacy_marked']}")
    console.print(f"  exact backfilled:             {result['exact_backfilled']}")
    console.print(f"  nearest-day backfilled:       {result['nearest_backfilled']}")
    console.print(f"  failed (no historical price): {result['failed_backfill']}")
    console.print(f"  unverified remaining:         {result['unverified_remaining']}")


@app.command("top-movers-refresh")
def top_movers_refresh_cmd(
    market: Annotated[
        str, typer.Option("--market", help="시장: US / KR / ALL")
    ] = "ALL",
    days: Annotated[
        int, typer.Option("--days", help="최근 N일 기간 (default 90)")
    ] = 90,
    top_n: Annotated[
        int, typer.Option("--top-n", help="상위 N개 선별 (default 100)")
    ] = 100,
    save: Annotated[
        bool, typer.Option("--save/--no-save", help="DB 저장 여부")
    ] = False,
) -> None:
    """최근 3개월 급등주 자동 선별 (US/KR/ALL).

    Example:
        uv run tele-quant top-movers-refresh --market US --days 90 --top-n 100 --save
        uv run tele-quant top-movers-refresh --market KR --days 90 --top-n 100 --save
        uv run tele-quant top-movers-refresh --market ALL --save
    """
    from pathlib import Path as _Path

    from tele_quant.db import Store as _Store
    from tele_quant.top_mover_miner import fetch_kr_top_movers, fetch_us_top_movers

    settings = _settings()
    store = _Store(_Path(settings.sqlite_path))

    markets = ["US", "KR"] if market.upper() == "ALL" else [market.upper()]

    for mkt in markets:
        console.print(f"\n[bold]Top Movers — {mkt}[/bold] (days={days}, top_n={top_n})")
        run = (fetch_us_top_movers if mkt == "US" else fetch_kr_top_movers)(
            days=days, top_n=top_n
        )
        if not run.members:
            console.print("[yellow]데이터 없음 (universe 부족 또는 네트워크 실패)[/yellow]")
            continue

        for m in run.members[:10]:
            tag = f"[{m.liquidity_tier}]" if m.liquidity_tier else ""
            console.print(
                f"  {m.rank:3d}. {m.symbol:<15} {m.return_pct:+.1f}%  {tag}  {m.name[:30]}"
            )
        if len(run.members) > 10:
            console.print(f"  ... 외 {len(run.members) - 10}개")

        if save:
            run_id = store.save_top_mover_run(run)
            console.print(f"[green]저장 완료 run_id={run_id}[/green]")
        else:
            console.print("[dim](--no-save: DB 저장 안 함)[/dim]")

    console.print("\n⚠ 공개 정보 기반 리서치 보조. 투자 판단 책임은 사용자에게 있음.")


@app.command("relation-mine")
def relation_mine_cmd(
    market: Annotated[
        str, typer.Option("--market", help="시장: US / KR / ALL")
    ] = "ALL",
    days: Annotated[
        int, typer.Option("--days", help="최근 N일 기간 (default 90)")
    ] = 90,
    top_n: Annotated[
        int, typer.Option("--top-n", help="상위 N개 (default 100)")
    ] = 100,
    beneficiaries: Annotated[
        int, typer.Option("--beneficiaries", help="각 source당 수혜주 최소 수")
    ] = 2,
    victims: Annotated[
        int, typer.Option("--victims", help="각 source당 피해주 최소 수")
    ] = 2,
    save: Annotated[
        bool, typer.Option("--save/--no-save", help="DB 저장 여부")
    ] = False,
    from_top_movers: Annotated[
        str, typer.Option("--from-top-movers", help="'latest' 이면 DB 최신 run 사용")
    ] = "",
) -> None:
    """급등주별 수혜주/피해주 관계 엣지 생성.

    Example:
        uv run tele-quant relation-mine --market US --save
        uv run tele-quant relation-mine --from-top-movers latest --save
    """
    from pathlib import Path as _Path

    from tele_quant.db import Store as _Store
    from tele_quant.relation_miner import RelationMiner
    from tele_quant.top_mover_miner import TopMover, fetch_kr_top_movers, fetch_us_top_movers

    settings = _settings()
    store = _Store(_Path(settings.sqlite_path))

    supply_chain_path = _Path("config/supply_chain_rules.yml")
    pair_watch_path = _Path("config/pair_watch_rules.yml")
    sector_cycle_path = _Path("config/sector_cycle_rules.yml")
    miner = RelationMiner(supply_chain_path, pair_watch_path, sector_cycle_path)

    all_movers: list[TopMover] = []
    markets = ["US", "KR"] if market.upper() == "ALL" else [market.upper()]

    if from_top_movers.lower() == "latest":
        for mkt in markets:
            db_run = store.get_latest_top_mover_run(mkt)
            if db_run:
                for m in db_run.get("members", []):
                    all_movers.append(
                        TopMover(
                            symbol=m["symbol"], name=m.get("name", ""),
                            market=m["market"], sector=m.get("sector", ""),
                            rank=m["rank"], start_date=m.get("start_date", ""),
                            end_date=m.get("end_date", ""),
                            start_close=m.get("start_close"),
                            end_close=m.get("end_close"),
                            return_pct=m["return_pct"],
                            avg_turnover=m.get("avg_turnover"),
                            liquidity_tier=m.get("liquidity_tier", ""),
                            source_reason=m.get("source_reason", ""),
                        )
                    )
    else:
        for mkt in markets:
            run = (fetch_us_top_movers if mkt == "US" else fetch_kr_top_movers)(
                days=days, top_n=top_n
            )
            all_movers.extend(run.members)

    if not all_movers:
        console.print("[yellow]선별된 급등주 없음. --from-top-movers latest 또는 --save 후 재시도[/yellow]")
        return

    console.print(f"[bold]Relation Mine[/bold] — {len(all_movers)}개 source mover 처리 중...")
    edges = miner.mine_all(all_movers, max_per_mover=beneficiaries + victims + 4)

    b_count = sum(1 for e in edges if e.relation_type in ("BENEFICIARY", "PEER_MOMENTUM", "SUPPLIER"))
    v_count = sum(1 for e in edges if e.relation_type in ("VICTIM", "COMPETITOR", "INPUT_COST_VICTIM"))
    console.print(f"생성된 엣지: {len(edges)}개 (수혜계열 {b_count}, 피해계열 {v_count})")

    if save:
        from tele_quant.relation_graph import RelationGraph
        rg = RelationGraph()
        rg.add_edges(edges)
        ins, upd = rg.save_to_db(store)
        console.print(f"[green]저장 완료 inserted={ins} updated={upd}[/green]")
    else:
        for e in edges[:15]:
            console.print(
                f"  {e.source_symbol} → {e.target_symbol}"
                f" [{e.relation_type}, {e.direction}, {e.confidence}, score={e.relation_score:.0f}]"
            )
        if len(edges) > 15:
            console.print(f"  ... 외 {len(edges) - 15}개 (--save로 저장)")

    console.print("\n⚠ 상관관계는 인과관계가 아님. 공개 정보 기반 리서치 보조. 투자 판단 책임은 사용자에게 있음.")


@app.command("relation-expand")
def relation_expand_cmd(
    target_edges: Annotated[
        int, typer.Option("--target-edges", help="목표 엣지 수 (default 4000)")
    ] = 4000,
    save: Annotated[
        bool, typer.Option("--save/--no-save", help="DB 저장 여부")
    ] = False,
) -> None:
    """기존 관계 엣지를 확장해 4,000~8,000개 생성.

    Example:
        uv run tele-quant relation-expand --target-edges 8000 --save
    """
    from pathlib import Path as _Path

    from tele_quant.db import Store as _Store
    from tele_quant.relation_graph import RelationGraph
    from tele_quant.relation_miner import RelationMiner
    from tele_quant.top_mover_miner import TopMover

    settings = _settings()
    store = _Store(_Path(settings.sqlite_path))

    supply_chain_path = _Path("config/supply_chain_rules.yml")
    pair_watch_path = _Path("config/pair_watch_rules.yml")
    sector_cycle_path = _Path("config/sector_cycle_rules.yml")
    miner = RelationMiner(supply_chain_path, pair_watch_path, sector_cycle_path)

    existing = store.get_all_relation_edges(active_only=False)
    console.print(f"기존 엣지: {len(existing)}개")

    us_run = store.get_latest_top_mover_run("US")
    kr_run = store.get_latest_top_mover_run("KR")

    movers: list[TopMover] = []
    for run in [us_run, kr_run]:
        if not run:
            continue
        for m in run.get("members", []):
            movers.append(
                TopMover(
                    symbol=m["symbol"], name=m.get("name", ""),
                    market=m["market"], sector=m.get("sector", ""),
                    rank=m["rank"], start_date=m.get("start_date", ""),
                    end_date=m.get("end_date", ""),
                    start_close=m.get("start_close"),
                    end_close=m.get("end_close"),
                    return_pct=m["return_pct"],
                    avg_turnover=m.get("avg_turnover"),
                    liquidity_tier=m.get("liquidity_tier", ""),
                    source_reason=m.get("source_reason", ""),
                )
            )

    if not movers:
        console.print("[yellow]top_mover_runs 없음. 먼저 top-movers-refresh --save 실행[/yellow]")
        return

    edges = miner.mine_all(movers, max_per_mover=20)
    console.print(f"생성된 엣지: {len(edges)}개 (목표 {target_edges}개)")

    if save:
        rg = RelationGraph()
        rg.add_edges(edges)
        ins, upd = rg.save_to_db(store)
        console.print(f"[green]저장 완료 inserted={ins} updated={upd}[/green]")
    else:
        console.print("[dim](--no-save: DB 저장 안 함)[/dim]")

    console.print("\n⚠ 상관관계는 인과관계가 아님. 공개 정보 기반 리서치 보조. 투자 판단 책임은 사용자에게 있음.")


@app.command("relation-follow")
def relation_follow_cmd(
    market: Annotated[
        str, typer.Option("--market", help="시장: US / KR / ALL")
    ] = "ALL",
    hours: Annotated[
        float, typer.Option("--hours", help="source 움직임 감지 lookback 시간 (default 4)")
    ] = 4.0,
    source: Annotated[
        str, typer.Option("--source", help="특정 source 심볼만 처리")
    ] = "",
    save: Annotated[
        bool, typer.Option("--save/--no-save", help="DB 저장 여부")
    ] = False,
) -> None:
    """관계 엣지 추적 — source 움직임 감지 후 target 반응 기록.

    Example:
        uv run tele-quant relation-follow --market ALL --hours 4 --save
        uv run tele-quant relation-follow --source NVDA --save
    """
    from pathlib import Path as _Path

    from tele_quant.db import Store as _Store
    from tele_quant.relation_follow import RelationFollow

    settings = _settings()
    store = _Store(_Path(settings.sqlite_path))

    follower = RelationFollow(store)
    console.print("[bold]Relation Follow[/bold] — source 움직임 스캔 중...")

    events = follower.scan_source_moves(market=market.upper(), hours_back=hours)
    if source:
        events = [e for e in events if e.get("source_symbol", "").upper() == source.upper()]

    if not events:
        console.print("[dim]감지된 source 움직임 없음[/dim]")
    else:
        console.print(f"감지: {len(events)}개 움직임")
        for ev in events[:10]:
            console.print(
                f"  {ev['source_symbol']} {ev['source_move_pct']:+.1f}%"
                f" → {ev['target_symbol']} [{ev['expected_direction']}]"
            )
        if save:
            saved = follower.record_follow_events(events)
            updated = follower.update_pending_returns()
            follower.update_edge_hit_rates()
            console.print(f"[green]저장 {saved}건, 업데이트 {updated}건[/green]")
        else:
            console.print("[dim](--no-save: DB 저장 안 함)[/dim]")

    console.print("\n⚠ 관찰 기록이며 매수·매도 지시가 아닙니다. 투자 판단 책임은 사용자에게 있음.")


@app.command("relation-review")
def relation_review_cmd(
    days: Annotated[
        int, typer.Option("--days", help="최근 N일 성과 분석 (default 30)")
    ] = 30,
    send: Annotated[
        bool, typer.Option("--send/--no-send", help="텔레그램 전송 여부")
    ] = False,
) -> None:
    """관계 엣지 성과 리뷰 — hit_rate, avg_return, 비활성화 추천.

    Example:
        uv run tele-quant relation-review --days 30
    """
    from pathlib import Path as _Path

    from tele_quant.db import Store as _Store
    from tele_quant.relation_follow import build_relation_review

    settings = _settings()
    store = _Store(_Path(settings.sqlite_path))

    report = build_relation_review(store, days=days)
    if not report:
        console.print("[dim]성과 데이터 없음 (relation-follow 먼저 실행)[/dim]")
        return

    console.print(report)

    if send:
        async def _send() -> None:
            sender = TelegramSender(settings)
            await sender.send(report)
        asyncio.run(_send())
        console.print("[green]전송 완료[/green]")


@app.command("relation-report")
def relation_report_cmd(
    top_n: Annotated[
        int, typer.Option("--top-n", help="상위 N개 표시 (default 30)")
    ] = 30,
    send: Annotated[
        bool, typer.Option("--send/--no-send", help="텔레그램 전송 여부")
    ] = False,
) -> None:
    """관계 엣지 리포트 출력.

    Example:
        uv run tele-quant relation-report --top-n 30 --no-send
    """
    from pathlib import Path as _Path

    from tele_quant.db import Store as _Store
    from tele_quant.relation_graph import build_relation_report

    settings = _settings()
    store = _Store(_Path(settings.sqlite_path))

    report = build_relation_report(store, top_n=top_n)
    if not report:
        console.print("[dim]저장된 관계 엣지 없음. relation-mine --save 먼저 실행[/dim]")
        return

    console.print(report)

    if send:
        async def _send() -> None:
            sender = TelegramSender(settings)
            await sender.send(report)
        asyncio.run(_send())
        console.print("[green]전송 완료[/green]")


@app.command("relation-import-sector-seeds")
def relation_import_sector_seeds_cmd(
    seed_dir: Annotated[
        str,
        typer.Option("--dir", help="섹터 시드 YAML 디렉토리 (default: data/research/sector_relation_seeds)"),
    ] = "data/research/sector_relation_seeds",
    dry_run: Annotated[
        bool, typer.Option("--dry-run/--save", help="--dry-run: DB 저장 안 함 (default: dry-run)")
    ] = True,
    aliases_path: Annotated[
        str,
        typer.Option("--aliases", help="ticker_aliases.yml 경로 (default: config/ticker_aliases.yml)"),
    ] = "config/ticker_aliases.yml",
) -> None:
    """섹터 관계 시드 YAML 패키지를 DB에 임포트.

    Example:
        uv run tele-quant relation-import-sector-seeds --dry-run
        uv run tele-quant relation-import-sector-seeds --save
        uv run tele-quant relation-import-sector-seeds --dir data/research/sector_relation_seeds --save
    """
    from pathlib import Path as _Path

    from tele_quant.db import Store as _Store
    from tele_quant.relation_seed_importer import import_sector_seeds

    settings = _settings()
    store = _Store(_Path(settings.sqlite_path))

    seed_path = _Path(seed_dir)
    if not seed_path.exists():
        console.print(f"[red]시드 디렉토리 없음: {seed_path}[/red]")
        raise typer.Exit(1)

    mode_label = "[yellow]DRY-RUN[/yellow]" if dry_run else "[green]SAVE[/green]"
    console.print(f"[bold]Relation Import Sector Seeds[/bold] — 모드: {mode_label}")
    console.print(f"  시드 디렉토리: {seed_path}")

    result = import_sector_seeds(
        seed_dir=seed_path,
        store=store,
        dry_run=dry_run,
        aliases_path=aliases_path,
    )

    console.print("\n[bold]임포트 결과[/bold]")
    console.print(f"  엣지 파싱: {result.edges_read}")
    console.print(f"  bare KR 티커 해소: {result.bare_kr_resolved}")
    console.print(f"  미해소 심볼: {result.unresolved_symbols}")
    console.print(f"  self-loop 제거: {result.self_loops_removed}")
    console.print(f"  중복 건너뜀: {result.duplicates_found}")
    console.print(f"  HIGH→MEDIUM 강등: {result.high_downgraded}")
    console.print(f"  LOW watch_only: {result.low_watch_only}")
    console.print(f"  factor_edge: {result.factor_edges}")
    if not dry_run:
        console.print(f"  삽입: {result.inserted}")
        console.print(f"  업데이트: {result.updated}")
        console.print(f"  건너뜀: {result.skipped}")

    if result.sector_summary:
        console.print("\n[bold]섹터별 현황[/bold]")
        for sector_id, count in sorted(result.sector_summary.items(), key=lambda x: x[1], reverse=True):
            console.print(f"  {sector_id}: {count}개")

    if result.audit_notes:
        console.print("\n[bold]감사 노트[/bold]")
        for note in result.audit_notes[:20]:
            console.print(f"  [dim]{note}[/dim]")
        if len(result.audit_notes) > 20:
            console.print(f"  ... {len(result.audit_notes) - 20}개 더 (--dry-run 모드에서 확인)")

    if dry_run:
        console.print("\n[yellow]DRY-RUN 모드 — DB 미저장. --save 로 실제 저장[/yellow]")
    else:
        console.print("\n[green]섹터 시드 임포트 완료[/green]")

    console.print("\n⚠ 공개 정보 기반 리서치 보조. 투자 판단 책임은 사용자에게 있음.")


@app.command("relation-audit")
def relation_audit_cmd(
    fail_on_high: Annotated[
        bool, typer.Option("--fail-on-high", help="HIGH 위험 발견 시 exit code 1")
    ] = False,
) -> None:
    """관계 엣지 품질 검사 — self-loop, 중복, bare KR 티커, HIGH-without-URL, LOW-active 등.

    Example:
        uv run tele-quant relation-audit
        uv run tele-quant relation-audit --fail-on-high
    """
    import re
    import sys
    from pathlib import Path as _Path

    from tele_quant.db import Store as _Store

    settings = _settings()
    store = _Store(_Path(settings.sqlite_path))

    edges = store.get_all_relation_edges(active_only=False)
    if not edges:
        console.print("[dim]저장된 관계 엣지 없음[/dim]")
        return

    issues: list[tuple[str, str, str]] = []  # (level, edge_id, message)

    seen: set[tuple] = set()
    _SHORT_TICKER = re.compile(r"^[A-Z]{1,2}$")
    _BROKER_NAMES = {"GS", "MS", "DB", "CS", "UBS", "BNP", "JPM", "BAC", "C"}
    _BARE_KR = re.compile(r"^\d{6}$")
    _PLACEHOLDER_URL = re.compile(r"^(TBD|N/A|#|null|placeholder|없음)$", re.IGNORECASE)
    _FORBIDDEN = re.compile(
        r"(매수 권장|매도 권장|확정 수익|반드시 상승|수혜 확정|피해 확정|자동매매|실계좌 주문|상관관계.*인과)"
    )
    from tele_quant.relation_seed_importer import (
        VALID_DIRECTIONS as _VALID_DIRECTIONS,
    )
    from tele_quant.relation_seed_importer import (
        VALID_RELATION_TYPE_RE as _VALID_RELATION_TYPE_RE,
    )

    for e in edges:
        eid = str(e.get("id", "?"))
        src = e.get("source_symbol", "")
        tgt = e.get("target_symbol", "")
        rtype = e.get("relation_type", "")
        direc = e.get("direction", "")
        conf = e.get("confidence", "")
        score = e.get("relation_score", 0)
        hit_rate = e.get("hit_rate")
        ev_url = (e.get("evidence_url") or "").strip()
        summary = e.get("evidence_summary", "") or ""
        active = e.get("active", 1)
        rule_id = e.get("rule_id", "") or ""
        src_market = e.get("source_market", "") or ""

        # self-loop
        if src == tgt:
            issues.append(("HIGH", eid, f"self-loop: {src}"))

        # duplicate
        key = (src, tgt, rtype, direc)
        if key in seen:
            issues.append(("MEDIUM", eid, f"중복 엣지: {src}→{tgt} [{rtype}]"))
        seen.add(key)

        # broker name false-positive (source_market 있으면 실제 티커로 간주, 건너뜀)
        tgt_market = e.get("target_market", "") or ""
        if _SHORT_TICKER.match(src) and src in _BROKER_NAMES and not src_market:
            issues.append(("HIGH", eid, f"브로커명 오탐 source: {src}"))
        if _SHORT_TICKER.match(tgt) and tgt in _BROKER_NAMES and not tgt_market:
            issues.append(("HIGH", eid, f"브로커명 오탐 target: {tgt}"))

        # bare KR ticker (6-digit without .KS/.KQ)
        if _BARE_KR.match(src) and src_market != "COMMODITY":
            issues.append(("HIGH", eid, f"bare KR 티커 미해소 source: {src}"))
        if _BARE_KR.match(tgt):
            issues.append(("HIGH", eid, f"bare KR 티커 미해소 target: {tgt}"))

        # HIGH confidence without valid evidence_url
        valid_url = ev_url and ev_url.startswith("http") and not _PLACEHOLDER_URL.match(ev_url)
        if conf == "HIGH" and not valid_url:
            issues.append(("HIGH", eid, f"HIGH confidence이나 유효 evidence_url 없음: {src}→{tgt}"))

        # LOW active=true (should be watch_only / inactive)
        if conf == "LOW" and active == 1:
            issues.append(("MEDIUM", eid, f"LOW confidence인데 active=1: {src}→{tgt}"))

        # factor edge source treated as stock (rule_id contains factor_edge but no COMMODITY market)
        if "factor_edge" in rule_id and src_market not in ("COMMODITY", "INDEX", "MACRO"):
            issues.append(("MEDIUM", eid, f"factor_edge인데 source_market={src_market!r}: {src}→{tgt}"))

        # direction enum validation (importer 기준과 동일)
        if direc and direc not in _VALID_DIRECTIONS:
            issues.append(("HIGH", eid, f"direction 값 비정상: {direc!r}: {src}→{tgt}"))

        # relation_type 형식 검증 (열린 집합 — regex)
        if rtype and not _VALID_RELATION_TYPE_RE.match(rtype):
            issues.append(("MEDIUM", eid, f"relation_type 형식 오류: {rtype!r}: {src}→{tgt}"))

        # forbidden expressions in summary
        if _FORBIDDEN.search(summary):
            issues.append(("HIGH", eid, f"금지 표현 발견: {src}→{tgt}"))

        if hit_rate is not None and hit_rate < 0.35 and active == 1:
            issues.append(("LOW", eid, f"hit_rate={hit_rate:.0%} 낮음, 비활성화 검토: {src}→{tgt}"))

        if score < 50 and active == 1:
            issues.append(("MEDIUM", eid, f"score={score:.0f} < 50인데 active=1: {src}→{tgt}"))

    high_cnt = sum(1 for lvl, _, _ in issues if lvl == "HIGH")
    med_cnt = sum(1 for lvl, _, _ in issues if lvl == "MEDIUM")
    low_cnt = sum(1 for lvl, _, _ in issues if lvl == "LOW")

    console.print(f"[bold]Relation Audit[/bold] — 총 {len(edges)}개 엣지 검사")
    console.print(f"  HIGH: {high_cnt}  MEDIUM: {med_cnt}  LOW: {low_cnt}")

    _COLORS = {"HIGH": "red", "MEDIUM": "yellow", "LOW": "dim"}
    for lvl, eid, msg in issues:
        color = _COLORS.get(lvl, "white")
        console.print(f"  [{color}][{lvl}][/{color}] id={eid} {msg}")

    if not issues:
        console.print("[green]이슈 없음[/green]")

    if fail_on_high and high_cnt > 0:
        sys.exit(1)


@app.command("relation-export")
def relation_export_cmd(
    output_dir: Annotated[
        str, typer.Option("--output-dir", help="출력 디렉토리 (default: data/generated)")
    ] = "data/generated",
) -> None:
    """관계 엣지를 CSV + YAML로 내보내기.

    Example:
        uv run tele-quant relation-export
        uv run tele-quant relation-export --output-dir data/generated
    """
    from pathlib import Path as _Path

    from tele_quant.db import Store as _Store
    from tele_quant.relation_graph import RelationGraph

    settings = _settings()
    store = _Store(_Path(settings.sqlite_path))

    out_dir = _Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    rg = RelationGraph()
    count = rg.load_from_db(store)
    console.print(f"[bold]Relation Export[/bold] — {count}개 엣지 로드")

    csv_path = out_dir / "relation_edges_latest.csv"
    yml_path = out_dir / "relation_edges_latest.yml"

    n_csv = rg.export_csv(csv_path)
    n_yml = rg.export_yaml(yml_path)

    console.print(f"[green]CSV: {csv_path} ({n_csv}행)[/green]")
    console.print(f"[green]YAML: {yml_path} ({n_yml}개)[/green]")
    console.print("\n⚠ 공개 정보 기반 리서치 보조. 투자 판단 책임은 사용자에게 있음.")
