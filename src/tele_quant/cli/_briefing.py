from __future__ import annotations

import asyncio
from typing import Annotated, Any

import typer

from tele_quant.cli._app import app
from tele_quant.cli._common import _settings, console
from tele_quant.telegram_sender import TelegramSender


@app.command()
def weekly(
    send: Annotated[
        bool, typer.Option("--send/--no-send", help="주간 리포트를 텔레그램으로 전송할지")
    ] = False,
    days: Annotated[int, typer.Option("--days", help="최근 몇 일간의 리포트를 모을지")] = 7,
    mode: Annotated[
        str,
        typer.Option("--mode", help="no_llm: 순수 Python 집계 / deep_polish: Ollama 문장 다듬기"),
    ] = "no_llm",
) -> None:
    """최근 N일 fast 리포트를 모아 주간 총정리를 생성합니다."""
    from datetime import timedelta

    from tele_quant.db import Store
    from tele_quant.models import utc_now
    from tele_quant.telegram_client import TelegramGateway
    from tele_quant.weekly import build_weekly_deterministic_summary, build_weekly_input

    async def run() -> None:
        settings = _settings()
        store = Store(settings.sqlite_path)
        since = utc_now() - timedelta(days=days)
        limit = settings.weekly_max_reports
        reports = store.recent_run_reports(since=since, limit=limit)

        # Load relation feed for weekly report section
        relation_feed_data = None
        try:
            from tele_quant.relation_feed import load_relation_feed

            relation_feed_data = load_relation_feed(settings)
            if relation_feed_data.available:
                console.print(
                    f"[weekly] relation_feed: movers={len(relation_feed_data.movers)}"
                    f" leadlag={len(relation_feed_data.leadlag)}"
                )
        except Exception as _rf_exc:
            console.print(f"[yellow][weekly] relation_feed load failed: {_rf_exc}[/yellow]")

        console.print(
            f"[weekly] reports={len(reports)} days={days} mode={mode}",
        )

        # Load LONG ≥80 scenario history and fetch current prices for performance review
        perf_entries: list[dict] = []
        no_price_count = 0
        if getattr(settings, "weekly_performance_review", True):
            try:
                import yfinance as yf

                scenario_rows = store.recent_scenarios(since=since, side="LONG", min_score=80)
                console.print(f"[weekly] performance scenarios={len(scenario_rows)}")

                # scenario_history에서 price 있는 항목 처리 — 첫 80점 이상 시점 기준
                sym_all: dict[str, list[dict]] = {}
                for row in scenario_rows:
                    sym = row.get("symbol", "")
                    if sym:
                        sym_all.setdefault(sym, []).append(row)

                seen_syms: dict[str, dict] = {}
                for sym, rows_for_sym in sym_all.items():
                    # Sort ascending by created_at → oldest = first 80-point recommendation
                    rows_sorted = sorted(rows_for_sym, key=lambda r: r.get("created_at") or "")
                    first_row = rows_sorted[0]
                    entry_price = first_row.get("signal_price") or first_row.get(
                        "close_price_at_report"
                    )
                    if entry_price is None:
                        for r in rows_sorted:
                            ep = r.get("signal_price") or r.get("close_price_at_report")
                            if ep is not None:
                                first_row = r
                                entry_price = ep
                                break
                    if entry_price is None:
                        continue
                    best_row = max(rows_sorted, key=lambda r: r.get("score") or 0)
                    mkt = "KR" if sym.endswith((".KS", ".KQ")) else "US"
                    seen_syms[sym] = {
                        "symbol": sym,
                        "name": first_row.get("name"),
                        "score": first_row.get("score", 0),
                        "max_score": best_row.get("score", first_row.get("score", 0)),
                        "max_score_at": best_row.get("created_at"),
                        "entry_price": entry_price,
                        "created_at": first_row.get("created_at"),
                        "first_seen_at": first_row.get("created_at"),
                        "repeat_count": len(rows_for_sym),
                        "market": mkt,
                        "entry_basis": "report_time_latest_close",
                        "_source": "scenario_history",
                    }

                for sym, info in seen_syms.items():
                    try:
                        hist = yf.Ticker(sym).history(period="2d", auto_adjust=True)
                        if hist.empty:
                            no_price_count += 1
                            continue
                        current = float(hist["Close"].iloc[-1])
                        ret_pct = (current - info["entry_price"]) / info["entry_price"] * 100
                        perf_entries.append(
                            {
                                **info,
                                "current_price": current,
                                "return_pct": ret_pct,
                                "win": ret_pct > 0,
                            }
                        )
                    except Exception:
                        no_price_count += 1

                # Fallback: scenario_history가 비어 있으면 run_reports analysis_text 파싱
                if not perf_entries and reports:
                    console.print("[weekly] scenario_history 없음 → analysis_text fallback 파싱")
                    from tele_quant.weekly import parse_long_candidates_from_analysis

                    # Diagnose why scenario_history is empty
                    has_long_80 = (
                        any(
                            r.get("side") == "LONG" and (r.get("score") or 0) >= 80
                            for r in scenario_rows
                        )
                        if scenario_rows
                        else False
                    )
                    has_no_price = (
                        any(
                            r.get("close_price_at_report") is None
                            for r in scenario_rows
                            if r.get("side") == "LONG" and (r.get("score") or 0) >= 80
                        )
                        if scenario_rows
                        else False
                    )
                    _diag: list[str] = []
                    if not scenario_rows:
                        _diag.append("DB 저장 없음 (scenario_history 비어 있음)")
                    elif not has_long_80:
                        _diag.append("80점 이상 LONG 후보 없음")
                    elif has_no_price:
                        _diag.append("가격 확인 실패 (close_price_at_report NULL)")
                    if _diag:
                        console.print(f"[weekly] 성과 리뷰 진단: {'; '.join(_diag)}")

                    fallback_seen: dict[str, dict] = {}
                    has_analysis = False
                    for rep in reports:
                        if not rep.analysis:
                            continue
                        has_analysis = True
                        candidates = parse_long_candidates_from_analysis(
                            rep.analysis, min_score=80.0
                        )
                        for cand in candidates:
                            sym = cand["symbol"]
                            if sym and sym not in fallback_seen:
                                fallback_seen[sym] = {
                                    **cand,
                                    "created_at": rep.created_at.isoformat()
                                    if rep.created_at
                                    else None,
                                    "market": "KR" if sym.endswith((".KS", ".KQ")) else "US",
                                }

                    if not has_analysis:
                        _diag.append("분석 리포트 없음 (macro-only 기간)")
                    elif not fallback_seen:
                        _diag.append("fallback 파싱 실패 (80점 이상 롱 섹션 미발견)")

                    console.print(
                        f"[weekly] fallback candidates={len(fallback_seen)} source=analysis_text"
                    )
                    for sym, info in fallback_seen.items():
                        try:
                            hist = yf.Ticker(sym).history(period="2d", auto_adjust=True)
                            if hist.empty:
                                no_price_count += 1
                                continue
                            current = float(hist["Close"].iloc[-1])
                            entry = info.get("entry_price")
                            if entry:
                                ret_pct = (current - entry) / entry * 100
                                perf_entries.append(
                                    {
                                        **info,
                                        "current_price": current,
                                        "return_pct": ret_pct,
                                        "win": ret_pct > 0,
                                        "_source": "fallback",
                                    }
                                )
                            else:
                                no_price_count += 1
                                _diag.append(f"{sym}: 진입가 없음")
                        except Exception:
                            no_price_count += 1

                if no_price_count:
                    console.print(f"[weekly] 가격 확인 불가: {no_price_count}개 제외")

            except Exception as exc:
                console.print(f"[yellow][weekly] performance review failed: {exc}[/yellow]")

        weekly_input = build_weekly_input(reports, performance_entries=perf_entries)
        console.print(
            f"[weekly] tickers={len(weekly_input.top_tickers)}"
            f" macro_keywords={len(weekly_input.macro_keywords)}",
        )

        if weekly_input.report_count == 0:
            console.print("[yellow]최근 리포트가 없어 주간 요약 생략[/yellow]")
            return

        # Relation signal performance review
        relation_signal_review: str | None = None
        try:
            from tele_quant.weekly import build_relation_signal_review_section

            relation_signal_review = build_relation_signal_review_section(store, since=since)
            console.print("[weekly] relation_signal_review=ok")
        except Exception as _rsr_exc:
            console.print(f"[yellow][weekly] relation_signal_review failed: {_rsr_exc}[/yellow]")

        # Pair watch weekly review
        pair_watch_review: str | None = None
        try:
            from tele_quant.live_pair_watch import build_pair_watch_weekly_review

            pair_watch_review = build_pair_watch_weekly_review(
                store, since=since, settings=settings
            )
            console.print("[weekly] pair_watch_review=ok")
        except Exception as _pwr_exc:
            console.print(f"[yellow][weekly] pair_watch_review failed: {_pwr_exc}[/yellow]")

        # SHORT ≥80 성과 — LONG과 같은 방식으로 빌드
        short_entries: list[dict] = []
        try:
            import yfinance as yf

            short_rows = store.recent_scenarios(since=since, side="SHORT", min_score=80)
            short_sym_all: dict[str, list[dict]] = {}
            for row in short_rows:
                sym = row.get("symbol", "")
                if sym:
                    short_sym_all.setdefault(sym, []).append(row)

            for sym, rows_for_sym in short_sym_all.items():
                rows_sorted = sorted(rows_for_sym, key=lambda r: r.get("created_at") or "")
                first_row = rows_sorted[0]
                entry_price = first_row.get("signal_price") or first_row.get(
                    "close_price_at_report"
                )
                if entry_price is None:
                    for r in rows_sorted:
                        ep = r.get("signal_price") or r.get("close_price_at_report")
                        if ep is not None:
                            first_row = r
                            entry_price = ep
                            break
                if entry_price is None:
                    continue
                mkt = "KR" if sym.endswith((".KS", ".KQ")) else "US"
                try:
                    hist = yf.Ticker(sym).history(period="2d", auto_adjust=True)
                    if hist.empty:
                        continue
                    current = float(hist["Close"].iloc[-1])
                    # SHORT 수익률: 신호가 > 현재가 = 적중
                    ret_pct = (entry_price - current) / entry_price * 100
                    short_entries.append(
                        {
                            "symbol": sym,
                            "name": first_row.get("name"),
                            "score": first_row.get("score", 0),
                            "entry_price": entry_price,
                            "current_price": current,
                            "return_pct": ret_pct,
                            "win": ret_pct > 0,
                            "created_at": first_row.get("created_at"),
                            "market": mkt,
                            "_source": "scenario_history",
                        }
                    )
                except Exception:
                    pass
            if short_entries:
                console.print(f"[weekly] short_entries={len(short_entries)}")
        except Exception as _se_exc:
            console.print(f"[yellow][weekly] short_entries build failed: {_se_exc}[/yellow]")

        # Theme board (KR + US 합본)
        weekly_theme_board: str | None = None
        try:
            from tele_quant.theme_board import build_theme_board

            kr_board = build_theme_board("KR", store, settings)
            us_board = build_theme_board("US", store, settings)
            weekly_theme_board = kr_board + "\n\n" + us_board
            console.print("[weekly] theme_board=ok")
        except Exception as _tb_exc:
            console.print(f"[yellow][weekly] theme_board failed: {_tb_exc}[/yellow]")

        # Load AI narrative history for weekly section
        weekly_narratives: list[dict] | None = None
        try:
            weekly_narratives = store.recent_narratives(since=since, limit=40)
            if weekly_narratives:
                console.print(f"[weekly] narrative_history: {len(weekly_narratives)} records")
        except Exception as _wn_exc:
            console.print(f"[yellow][weekly] narrative load failed: {_wn_exc}[/yellow]")

        # Load Fear & Greed history for weekly trend section
        weekly_fear_greed: list[dict] | None = None
        try:
            weekly_fear_greed = store.recent_fear_greed(since=since, limit=50)
            if weekly_fear_greed:
                console.print(f"[weekly] fear_greed_history: {len(weekly_fear_greed)} records")
        except Exception as _fg_exc:
            console.print(f"[yellow][weekly] fear_greed load failed: {_fg_exc}[/yellow]")

        summary = build_weekly_deterministic_summary(
            weekly_input,
            relation_feed_data=relation_feed_data,
            relation_signal_review=relation_signal_review,
            pair_watch_review=pair_watch_review,
            short_entries=short_entries if short_entries else None,
            narratives=weekly_narratives,
            fear_greed_history=weekly_fear_greed,
            daily_alpha_store=store,
            theme_board_section=weekly_theme_board,
        )

        if mode == "deep_polish":
            try:
                from tele_quant.ollama_client import OllamaClient

                ollama = OllamaClient(settings)
                import asyncio as _asyncio

                polished = await _asyncio.wait_for(
                    ollama.polish_weekly_report(summary),
                    timeout=settings.weekly_ollama_timeout_seconds,
                )
                summary = polished
                console.print("[weekly] polish=ok")
            except TimeoutError:
                console.print("[yellow][weekly] polish timeout → deterministic kept[/yellow]")
            except Exception as exc:
                console.print(
                    f"[yellow][weekly] polish failed: {exc} → deterministic kept[/yellow]"
                )
        else:
            console.print("[weekly] polish=skipped")

        if send:
            async with TelegramGateway(settings) as gateway:
                sender = TelegramSender(settings, gateway=gateway)
                await sender.send(summary)
            console.print("[weekly] sent=ok")
        else:
            console.rule("[dim]Weekly Report Preview[/dim]")
            console.print(summary)

    asyncio.run(run())


@app.command("briefing")
def briefing_cmd(
    market: Annotated[
        str, typer.Option("--market", help="시장 (KR / US / ALL)")
    ] = "KR",
    top_n: Annotated[
        int, typer.Option("--top-n", help="LONG/SHORT 후보 최대 수")
    ] = 5,
    send: Annotated[
        bool, typer.Option("--send/--no-send", help="텔레그램 전송 여부")
    ] = False,
    advisory: Annotated[
        bool,
        typer.Option(
            "--advisory/--classic",
            help="advisory 모드(run_4h_advisory) / classic 모드(run_4h_briefing). "
                 "미지정 시 settings.advisory_only_mode 따름",
        ),
    ] = True,
) -> None:
    """4H 퀀터멘탈 브리핑 — 매크로·펀더멘탈·종목·포트폴리오 통합.

    Example: uv run tele-quant briefing --market KR --send
             uv run tele-quant briefing --market ALL --no-send
             uv run tele-quant briefing --market KR --classic --no-send   (구 브리핑 형식)
             uv run tele-quant briefing --market US --advisory --send     (4H 어드바이징)
    """
    from pathlib import Path as _Path

    from tele_quant.db import Store as _Store

    market = market.upper()
    settings = _settings()
    store = _Store(_Path(settings.sqlite_path))

    # advisory 플래그가 명시적으로 --classic이면 False, 그 외에는 settings 값 우선
    use_advisory = advisory and getattr(settings, "advisory_only_mode", True)

    markets = ["KR", "US"] if market == "ALL" else [market]
    mode_label = "advisory" if use_advisory else "classic"

    for mkt in markets:
        console.print(
            f"[bold]4H Briefing[/bold] market={mkt} top_n={top_n} "
            f"mode={mode_label} send={send}"
        )

        try:
            if use_advisory:
                from tele_quant.advisor_4h import run_4h_advisory
                report = run_4h_advisory(mkt, store, settings, top_n=top_n)
            else:
                from tele_quant.briefing import run_4h_briefing
                report = run_4h_briefing(mkt, store, settings, top_n=top_n)
        except Exception as exc:
            console.print(f"[red]briefing failed: {exc}[/red]")
            continue

        if not report:
            console.print(f"[dim]{mkt} 브리핑 생성 실패[/dim]")
            continue

        console.print("\n" + report)

        if send:
            async def _send(r: str = report) -> None:
                sender = TelegramSender(settings)
                await sender.send(r)

            asyncio.run(_send())
            console.print(f"[green]{mkt} 브리핑 전송 완료[/green]")
        else:
            console.print("[dim](--no-send: 미리보기만)[/dim]")


@app.command("cycle-briefing")
def cycle_briefing_cmd(
    slot: Annotated[
        str,
        typer.Option(
            "--slot",
            help="브리핑 슬롯: monday-open | weekday-4h | weekend-issue | sunday-review | auto",
        ),
    ] = "auto",
    market: Annotated[
        str, typer.Option("--market", help="시장 (KR / US / ALL)")
    ] = "ALL",
    send: Annotated[
        bool, typer.Option("--send/--no-send", help="텔레그램 전송 여부")
    ] = False,
) -> None:
    """주간 사이클 퀀터멘탈 관찰 브리핑.

    슬롯:
      monday-open   — 월요일 07:00 KST, 보수적 모드 (주말 갭 리스크 / EXIT 우선)
      weekday-4h    — 평일 4H 퀀터멘탈 관찰 브리핑 (LONG/SHORT 관찰 후보)
      weekend-issue — 주말 이슈/공시/정책 전용 (차트 추천 없음)
      sunday-review — 일요일 23:00 주간 성과 리뷰
      auto          — KST 현재 시각 기준 자동 판정

    Example:
        uv run tele-quant cycle-briefing --slot monday-open --no-send
        uv run tele-quant cycle-briefing --slot weekday-4h --send
        uv run tele-quant cycle-briefing --slot weekend-issue --no-send
        uv run tele-quant cycle-briefing --slot sunday-review --no-send
        uv run tele-quant cycle-briefing --auto --no-send
    """
    from pathlib import Path as _Path

    from tele_quant.db import Store as _Store
    from tele_quant.weekly_cycle_orchestrator import WeeklyCycleSlot, run_cycle_briefing

    _slot_map = {
        "monday-open": WeeklyCycleSlot.MONDAY_OPEN,
        "monday_open": WeeklyCycleSlot.MONDAY_OPEN,
        "weekday-4h": WeeklyCycleSlot.WEEKDAY_4H,
        "weekday_4h": WeeklyCycleSlot.WEEKDAY_4H,
        "weekend-issue": WeeklyCycleSlot.WEEKEND_ISSUE,
        "weekend_issue": WeeklyCycleSlot.WEEKEND_ISSUE,
        "sunday-review": WeeklyCycleSlot.SUNDAY_REVIEW,
        "sunday_review": WeeklyCycleSlot.SUNDAY_REVIEW,
        "auto": WeeklyCycleSlot.AUTO,
    }
    resolved_slot = _slot_map.get(slot.lower(), WeeklyCycleSlot.AUTO)

    settings = _settings()
    store = _Store(_Path(settings.sqlite_path))

    console.print(
        f"[bold]Cycle Briefing[/bold] slot={resolved_slot.value} market={market.upper()} send={send}"
    )

    try:
        report = run_cycle_briefing(
            slot=resolved_slot,
            store=store,
            settings=settings,
            market=market.upper(),
            save_to_db=send,
        )
    except Exception as exc:
        console.print(f"[red]cycle-briefing 실패: {exc}[/red]")
        raise SystemExit(1) from exc

    console.print("\n" + report)

    if send:
        asyncio.run(_do_send(settings, report))
        console.print("[green]cycle-briefing 전송 완료[/green]")
    else:
        console.print("[dim](--no-send: 미리보기만)[/dim]")


async def _do_send(settings: Any, report: str) -> None:
    sender = TelegramSender(settings)
    await sender.send(report)


@app.command("daily-alpha")
def daily_alpha_cmd(
    market: Annotated[
        str, typer.Option("--market", help="시장 (KR 또는 US)")
    ] = "KR",
    send: Annotated[
        bool, typer.Option("--send/--no-send", help="실제 전송 여부 (--no-send: 미리보기만)")
    ] = False,
    top_n: Annotated[
        int, typer.Option("--top-n", help="LONG/SHORT 각 최대 후보 수")
    ] = 4,
    universe_size: Annotated[
        int, typer.Option("--universe-size", help="스크리닝 유니버스 크기")
    ] = 150,
) -> None:
    """Daily Alpha Picks 엔진 실행 (기계적 스크리닝 LONG/SHORT 관찰 후보).

    Example: uv run tele-quant daily-alpha --market KR --no-send
             uv run tele-quant daily-alpha --market US --send
    """
    from pathlib import Path as _Path

    from rich.progress import Progress, SpinnerColumn, TextColumn

    from tele_quant.daily_alpha import (
        SESSION_KR,
        SESSION_US,
        build_daily_alpha_report,
        run_daily_alpha,
    )
    from tele_quant.db import Store as _Store

    market = market.upper()
    if market not in ("KR", "US"):
        console.print("[red]--market 은 KR 또는 US 만 허용됩니다.[/red]")
        raise SystemExit(1)

    session = SESSION_KR if market == "KR" else SESSION_US

    settings = _settings()
    store = _Store(_Path(settings.sqlite_path))

    console.print(f"[bold]Daily Alpha Picks[/bold] market={market} send={send} top_n={top_n}")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as prog:
        task = prog.add_task(f"[cyan]{market} 유니버스 스크리닝 중...", total=None)
        long_picks, short_picks = run_daily_alpha(
            market=market,
            store=store,
            top_n=top_n,
            universe_size=universe_size,
        )
        prog.update(task, description="[green]스크리닝 완료")

    report = build_daily_alpha_report(long_picks, short_picks, market, session_label=session)
    console.print("\n" + report)
    console.print(f"\n[dim]LONG {len(long_picks)}개 / SHORT {len(short_picks)}개 후보[/dim]")

    if send:
        # Save to DB (sent gate)
        all_picks = long_picks + short_picks
        n_saved = store.save_daily_alpha_picks(all_picks, session=session, market=market)
        console.print(f"[green]DB 저장: {n_saved}건 신규 (중복 제외)[/green]")

        if getattr(settings, "advisory_only_mode", True):
            console.print(
                "[yellow]advisory_only_mode=True — daily-alpha를 즉시 발송하지 않습니다. "
                "4H 브리핑에서 섹션③④로 통합됩니다.[/yellow]"
            )
        else:
            async def _send() -> None:
                sender = TelegramSender(settings)
                await sender.send(report)

            asyncio.run(_send())
            console.print(f"[green]전송 완료 ({session})[/green]")
    else:
        console.print("[dim](--no-send: 미리보기만, DB 미저장, 전송 안 함)[/dim]")


@app.command("surge-scan")
def surge_scan_cmd(
    market: Annotated[
        str, typer.Option("--market", help="시장 (KR / US / ALL)")
    ] = "ALL",
    threshold: Annotated[
        float, typer.Option("--threshold", help="장중 급등 임계 % (기본 3.0)")
    ] = 3.0,
    min_gap: Annotated[
        float, typer.Option("--min-gap", help="미반영 갭 최소 % (기본 2.0)")
    ] = 2.0,
    max_workers: Annotated[
        int, typer.Option("--workers", help="병렬 조회 스레드 수")
    ] = 12,
    skip_dedup: Annotated[
        bool, typer.Option("--skip-dedup/--no-skip-dedup", help="중복 알림 체크 건너뜀")
    ] = False,
    force: Annotated[
        bool, typer.Option("--force/--no-force", help="장 마감 시간에도 강제 실행 (테스트용)")
    ] = False,
    send: Annotated[
        bool, typer.Option("--send/--no-send", help="텔레그램 전송 여부")
    ] = False,
) -> None:
    """장중 급등·급락 감지 → 카탈리스트 규명 → 미반영 관련 종목 LONG/SHORT 관찰 후보.

    Example: uv run tele-quant surge-scan --market KR --threshold 3.0 --send
             uv run tele-quant surge-scan --market ALL --no-send
             uv run tele-quant surge-scan --no-send --skip-dedup --force  (장 마감 테스트)
    """
    from pathlib import Path as _Path

    from tele_quant.db import Store as _Store
    from tele_quant.surge_alert import build_surge_report, is_market_open, run_surge_scan

    market = market.upper()
    settings = _settings()
    store = _Store(_Path(settings.sqlite_path))

    console.print(
        f"[bold]Surge Scan[/bold] market={market} threshold={threshold}% "
        f"min_gap={min_gap}% workers={max_workers} send={send} force={force}"
    )

    if not force and not is_market_open(market):
        console.print(f"[dim]시장 마감 시간 — surge-scan 건너뜀 (market={market}, --force 로 강제 실행 가능)[/dim]")
        return

    dart_key = getattr(settings, "dart_api_key", "") or ""

    surges, targets = run_surge_scan(
        market=market,
        threshold=threshold,
        dart_api_key=dart_key,
        max_workers=max_workers,
        store=store,
        skip_dedup=skip_dedup,
    )

    if not surges:
        console.print(f"[dim]급등 종목 없음 (threshold={threshold}% / 최근 중복 제외)[/dim]")
        return

    # min_gap 으로 targets 재필터 (run_surge_scan 기본값과 다를 수 있음)
    if min_gap != 2.0:
        targets = [t for t in targets if t.gap_pct >= min_gap]

    console.print(f"[green]급등 감지: {len(surges)}개  미반영 후보: {len(targets)}개[/green]")
    for ev in surges[:5]:
        console.print(
            f"  {'▲' if ev.direction == 'BULLISH' else '▼'} "
            f"{ev.name}({ev.symbol}) {ev.intraday_pct:+.1f}%  [{ev.catalyst_ko or '이유불명'}]"
        )

    report = build_surge_report(surges, targets, market=market)
    if report:
        console.print("\n" + report)

    if send and report:
        if getattr(settings, "advisory_only_mode", True):
            console.print(
                "[yellow]advisory_only_mode=True — 급등 알림을 즉시 발송하지 않습니다. "
                "4H 브리핑에서 수혜주 체인으로 통합됩니다.[/yellow]"
            )
        else:
            async def _send() -> None:
                sender = TelegramSender(settings)
                await sender.send(report)

            asyncio.run(_send())
            console.print("[green]전송 완료[/green]")
    elif not send:
        console.print("[dim](--no-send: 미리보기만)[/dim]")


@app.command("price-alert")
def price_alert_cmd(
    market: Annotated[
        str | None, typer.Option("--market", help="시장 필터 (KR | US | 생략 시 둘 다)")
    ] = None,
    send: Annotated[
        bool, typer.Option("--send/--no-send", help="실제 텔레그램 전송 여부")
    ] = False,
    force: Annotated[
        bool, typer.Option("--force", help="장중 시간대 체크 없이 강제 실행")
    ] = False,
) -> None:
    """목표가/무효화 레벨 도달 알림 (장중 30분마다 자동 실행).

    Example: uv run tele-quant price-alert --market KR --send
             uv run tele-quant price-alert --force --no-send  (수동 테스트)
    """
    from pathlib import Path as _Path

    from tele_quant.db import Store as _Store
    from tele_quant.price_alert import run_price_alerts

    settings = _settings()
    store = _Store(_Path(settings.sqlite_path))

    mkt_label = market.upper() if market else "KR+US"

    effective_send = send
    if send and getattr(settings, "advisory_only_mode", True):
        console.print(
            "[yellow]advisory_only_mode=True — price-alert를 즉시 발송하지 않습니다. "
            "4H 브리핑 섹션⑥(포트폴리오) 무효화 체크로 통합됩니다.[/yellow]"
        )
        effective_send = False

    console.print(f"[bold]Price Alert[/bold] market={mkt_label} send={effective_send} force={force}")

    triggered = run_price_alerts(
        store=store,
        market=market.upper() if market else None,
        send=effective_send,
        force=force,
    )

    if triggered:
        for t in triggered:
            emoji = "🎯" if t["type"] == "TARGET" else "🚨"
            pick = t["pick"]
            console.print(
                f"  {emoji} {pick.get('side')} {pick.get('symbol')} "
                f"→ {t['type']} @ {t['price']:.2f}"
            )
        console.print(f"\n[green]{len(triggered)}건 알림 처리됨[/green]")
    else:
        console.print("[dim]트리거 없음 (장중 시간 아님이거나 도달 종목 없음)[/dim]")


@app.command("pre-market-alert")
def pre_market_alert_cmd(
    threshold: Annotated[
        float, typer.Option("--threshold", help="US 움직임 최소 기준 (%)")
    ] = 3.0,
    top_n: Annotated[
        int, typer.Option("--top-n", help="표시할 KR 관찰 후보 최대 수")
    ] = 8,
    no_send: Annotated[
        bool, typer.Option("--no-send/--send", help="전송 없이 출력만")
    ] = True,
) -> None:
    """KR 장 개시 전 예열 알림 — US 전일 종가 기준 급등락 → KR 연결 종목 관찰.

    US 마감 후 KR 개장 전(08:00 KST) 실행하면 기관 대비 3시간 선행 정보 활용 가능.

    Example: uv run tele-quant pre-market-alert --no-send
             uv run tele-quant pre-market-alert --send --threshold 2.0
    """
    import asyncio as _asyncio
    from datetime import UTC, datetime, timedelta

    import yfinance as yf

    from tele_quant.relation_feed import _NAME_MAP, _SECTOR_MAP, _UNIVERSE_US
    from tele_quant.supply_chain_alpha import load_supply_chain_rules

    now_kst = datetime.now(UTC) + timedelta(hours=9)
    console.print(f"[cyan]pre-market-alert: {now_kst.strftime('%Y-%m-%d %H:%M KST')} — US 전일 급등락 → KR 예열[/cyan]")

    # ── US 전일 종가 수집 (yfinance 2일, 변동률 계산) ──────────────────────────
    us_movers: list[dict] = []
    for sym in _UNIVERSE_US:
        try:
            ticker = yf.Ticker(sym)
            hist = ticker.history(period="3d", interval="1d", auto_adjust=True)
            if hist is None or len(hist) < 2:
                continue
            prev_close = float(hist["Close"].iloc[-2])
            last_close = float(hist["Close"].iloc[-1])
            if prev_close <= 0:
                continue
            ret_pct = (last_close - prev_close) / prev_close * 100
            if abs(ret_pct) >= threshold:
                us_movers.append({
                    "symbol": sym,
                    "name": _NAME_MAP.get(sym, sym),
                    "sector": _SECTOR_MAP.get(sym, ""),
                    "ret_pct": ret_pct,
                    "last_close": last_close,
                })
        except Exception:
            pass

    us_movers.sort(key=lambda x: abs(x["ret_pct"]), reverse=True)

    if not us_movers:
        console.print(f"[yellow]US ±{threshold}% 이상 움직임 없음[/yellow]")
        return

    # ── 공급망 룰로 KR 연결 종목 탐색 ──────────────────────────────────────────
    rules = load_supply_chain_rules()
    kr_candidates: dict[str, dict] = {}

    for mover in us_movers:
        sym = mover["symbol"]
        direction = "UP" if mover["ret_pct"] > 0 else "DOWN"
        for rule in rules:
            src_syms = [s.get("symbol", "") for s in rule.get("source_symbols", [])]
            if sym not in src_syms:
                continue
            targets_key = "beneficiaries" if direction == "UP" else "victims_on_bearish"
            for group in rule.get(targets_key, []):
                for tgt in group.get("symbols", []):
                    tgt_sym = tgt.get("symbol", "")
                    if not tgt_sym.endswith((".KS", ".KQ")):
                        continue
                    if tgt_sym not in kr_candidates:
                        kr_candidates[tgt_sym] = {
                            "symbol": tgt_sym,
                            "name": tgt.get("name") or _NAME_MAP.get(tgt_sym, tgt_sym),
                            "sector": group.get("sector", ""),
                            "relation": group.get("relation_type", ""),
                            "triggers": [],
                        }
                    kr_candidates[tgt_sym]["triggers"].append(
                        f"{mover['name']}({mover['ret_pct']:+.1f}%)"
                    )

    # ── 리포트 생성 ──────────────────────────────────────────────────────────
    lines: list[str] = [
        f"🌅 KR 장 개시 전 예열 알림 [{now_kst.strftime('%m/%d %H:%M KST')}]",
        "",
        "📊 US 전일 주요 급등락",
    ]

    up_movers = [m for m in us_movers if m["ret_pct"] > 0][:5]
    dn_movers = [m for m in us_movers if m["ret_pct"] < 0][:5]

    if up_movers:
        lines.append("▸ 급등")
        for m in up_movers:
            lines.append(f"  🚀 {m['name']} ({m['symbol']}) {m['ret_pct']:+.1f}% [{m['sector']}]")
    if dn_movers:
        lines.append("▸ 급락")
        for m in dn_movers:
            lines.append(f"  💥 {m['name']} ({m['symbol']}) {m['ret_pct']:+.1f}% [{m['sector']}]")

    lines.append("")
    if kr_candidates:
        lines.append("🇰🇷 오늘 KR 연동 관찰 후보 (공급망·peer 연결)")
        sorted_kr = sorted(
            kr_candidates.values(),
            key=lambda x: len(x["triggers"]),
            reverse=True,
        )[:top_n]
        for i, c in enumerate(sorted_kr, 1):
            rel_label = {
                "LAGGING_BENEFICIARY": "후행수혜",
                "BENEFICIARY": "직접수혜",
                "PEER_MOMENTUM": "피어동조",
                "DEMAND_SLOWDOWN": "수요위험",
                "VICTIM": "피해우려",
            }.get(c["relation"], c["relation"])
            trigger_str = " / ".join(c["triggers"][:3])
            lines.append(
                f"  {i}. {c['name']} ({c['symbol']}) [{rel_label}·{c['sector']}]"
            )
            lines.append(f"     연결: {trigger_str}")
    else:
        lines.append("🇰🇷 KR 연동 후보 없음 (임계값 또는 룰 범위 초과)")

    lines += [
        "",
        "─" * 28,
        "공개 정보 기반 리서치 보조. 투자 판단 책임은 사용자에게 있음.",
    ]

    report = "\n".join(lines)
    console.print(report)

    if not no_send:
        settings = _settings()

        async def _send() -> None:
            from tele_quant.telegram_client import TelegramGateway
            from tele_quant.telegram_sender import TelegramSender
            async with TelegramGateway(settings) as gateway:
                sender = TelegramSender(settings, gateway=gateway)
                await sender.send(report)

        _asyncio.run(_send())
        console.print("[green]pre-market-alert 전송 완료[/green]")


@app.command("alpha-review")
def alpha_review_cmd(
    market: Annotated[
        str, typer.Option("--market", help="시장 (KR 또는 US)")
    ] = "KR",
    days: Annotated[
        int, typer.Option("--days", help="몇 일치 추천 성과를 볼지 (기본 1=당일)")
    ] = 1,
    send: Annotated[
        bool, typer.Option("--send/--no-send", help="텔레그램 전송 여부")
    ] = False,
) -> None:
    """장 마감 후 당일/최근 N일 추천 종목 성과 중간 요약.

    Example: uv run tele-quant alpha-review --market KR --send
             uv run tele-quant alpha-review --market US --days 3 --no-send
    """
    from pathlib import Path as _Path

    from tele_quant.alpha_review import build_alpha_review
    from tele_quant.db import Store as _Store

    market = market.upper()
    settings = _settings()
    store = _Store(_Path(settings.sqlite_path))

    console.print(f"[bold]Alpha Review[/bold] market={market} days={days} send={send}")

    report = build_alpha_review(store, market=market, days_back=days)

    if not report:
        console.print("[dim]성과 데이터 없음 (추천 기록 없거나 가격 조회 실패)[/dim]")
        return

    console.print("\n" + report)

    if send:
        async def _send() -> None:
            sender = TelegramSender(settings)
            await sender.send(report)

        asyncio.run(_send())
        console.print("[green]전송 완료[/green]")
    else:
        console.print("[dim](--no-send: 미리보기만)[/dim]")


@app.command("portfolio-status")
def portfolio_status_cmd(
    send: Annotated[
        bool, typer.Option("--send/--no-send", help="텔레그램 전송 여부")
    ] = False,
) -> None:
    """모의 포트폴리오 현재 P&L 스냅샷.

    Example: uv run tele-quant portfolio-status --no-send
    """
    from pathlib import Path as _Path

    from tele_quant.db import Store as _Store
    from tele_quant.mock_portfolio import build_portfolio_section, get_portfolio_summary

    settings = _settings()
    store = _Store(_Path(settings.sqlite_path))

    summary = get_portfolio_summary(store)
    section = build_portfolio_section(store)

    console.print(f"[bold]모의 포트폴리오[/bold]  보유 {summary['open_count']}/{summary['max_positions']}  "
                  f"승률 {summary['win_rate']:.0f}%  평균수익 {summary['avg_return']:+.1f}%")
    console.print("\n" + section)

    if send and section:
        from datetime import UTC as _UTC
        from datetime import datetime as _datetime
        header = f"💼 모의 포트폴리오 현황 — {_datetime.now(_UTC).strftime('%m/%d %H:%M')} UTC\n"
        report = header + section + "\n\n⚠ 공개 정보 기반 리서치 보조. 투자 판단 책임은 사용자에게 있음"

        async def _send() -> None:
            sender = TelegramSender(settings)
            await sender.send(report)

        asyncio.run(_send())
        console.print("[green]전송 완료[/green]")
    elif not send:
        console.print("[dim](--no-send: 미리보기만)[/dim]")
