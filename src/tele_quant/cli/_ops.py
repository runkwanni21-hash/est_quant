from __future__ import annotations

import asyncio
from typing import Annotated

import typer

from tele_quant.cli._app import app


class _CliProxy:
    """Proxy that delegates attribute access to the named attribute of
    ``tele_quant.cli`` at call time.  This lets unit tests patch
    ``tele_quant.cli.console`` or ``tele_quant.cli._settings`` and have
    the change visible inside this sub-module without circular imports."""

    def __init__(self, attr: str) -> None:
        object.__setattr__(self, "_attr", attr)

    def _target(self):  # type: ignore[return]
        import tele_quant.cli as _m
        return getattr(_m, object.__getattribute__(self, "_attr"))

    def __getattr__(self, name: str):
        return getattr(self._target(), name)

    def __call__(self, *args, **kwargs):
        return self._target()(*args, **kwargs)


# Module-level names - each delegates to the live tele_quant.cli attribute so
# that patch("tele_quant.cli.console") / patch("tele_quant.cli._settings")
# correctly intercept calls made from within this sub-module.
console = _CliProxy("console")


def _settings():  # type: ignore[return]
    import tele_quant.cli as _m
    return _m._settings()


@app.command("ops-doctor")
def ops_doctor() -> None:
    """자동 실행 상태와 DB 최신성을 진단합니다.

    Example: uv run tele-quant ops-doctor
    """
    import shutil
    import subprocess
    from datetime import timedelta
    from pathlib import Path as _Path
    from zoneinfo import ZoneInfo

    from rich.table import Table

    from tele_quant.db import Store
    from tele_quant.models import utc_now

    KST = ZoneInfo("Asia/Seoul")

    def _kst(dt: object) -> str:
        from datetime import datetime as _dt

        if isinstance(dt, _dt):
            return dt.astimezone(KST).strftime("%Y-%m-%d %H:%M KST")
        return str(dt)

    def _run(cmd: list[str]) -> tuple[str, int]:
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            return r.stdout.strip() + r.stderr.strip(), r.returncode
        except Exception as exc:
            return str(exc), -1

    now_kst = _kst(utc_now())
    console.print(f"\n[bold cyan]Tele Quant Ops Doctor[/bold cyan]  {now_kst}\n")

    has_systemd = shutil.which("systemctl") is not None

    # --- Timer status ---
    timer_table = Table(title="systemd Timers")
    timer_table.add_column("Timer")
    timer_table.add_column("Active")
    timer_table.add_column("Enabled")
    timer_table.add_column("Next Trigger")
    timer_table.add_column("Status")

    _TIMERS = [
        "tele-quant-cycle-monday-open.timer",
        "tele-quant-cycle-weekday-4h.timer",
        "tele-quant-cycle-weekend-issue.timer",
        "tele-quant-cycle-sunday-review.timer",
        "tele-quant-cycle-surge-collector.timer",
        "tele-quant-cycle-maintenance.timer",
        "tele-quant-price-alert.timer",
    ]

    timer_ok = True
    for timer in _TIMERS:
        if not has_systemd:
            timer_table.add_row(timer, "N/A", "N/A", "N/A", "[yellow]WARN: systemd 없음[/yellow]")
            timer_ok = False
            continue
        active_out, _ = _run(["systemctl", "--user", "is-active", timer])
        enabled_out, _ = _run(["systemctl", "--user", "is-enabled", timer])
        active = active_out.strip()
        enabled = enabled_out.strip()
        # Next trigger
        next_out, _ = _run(
            ["systemctl", "--user", "show", timer, "--property=NextElapseUSecRealtime"]
        )
        next_str = "알 수 없음"
        for part in next_out.split("=", 1)[1:]:
            val = part.strip()
            if val and val != "0":
                try:
                    import datetime

                    usec = int(val)
                    dt_utc = datetime.datetime(
                        1970, 1, 1, tzinfo=datetime.UTC
                    ) + datetime.timedelta(microseconds=usec)
                    next_str = _kst(dt_utc)
                except Exception:
                    next_str = val

        if active == "active" and enabled == "enabled":
            st = "[green]OK[/green]"
        elif active != "active":
            st = "[red]FAIL: inactive[/red]"
            timer_ok = False
        else:
            st = "[yellow]WARN: not enabled[/yellow]"
            timer_ok = False
        timer_table.add_row(timer, active, enabled, next_str, st)

    console.print(timer_table)

    # --- Recent service log ---
    if has_systemd:
        svc_out, _ = _run(
            ["journalctl", "--user", "-u", "tele-quant-cycle-weekday-4h.service", "-n", "20", "--no-pager"]
        )
        if svc_out:
            console.rule("[dim]최근 cycle-weekday-4h service 로그 (20줄)[/dim]")
            console.print(f"[dim]{svc_out[:2000]}[/dim]")

    # --- DB diagnostics ---
    settings = _settings()
    db_path = settings.sqlite_path
    db_exists = db_path.exists()

    db_table = Table(title="DB 상태")
    db_table.add_column("항목")
    db_table.add_column("값")
    db_table.add_column("판정")

    db_table.add_row(
        "SQLITE_PATH",
        str(db_path),
        "[green]exists[/green]" if db_exists else "[red]FAIL: 없음[/red]",
    )

    env_local = _Path(".env.local")
    db_table.add_row(
        ".env.local",
        "존재함" if env_local.exists() else "없음",
        "[green]OK[/green]" if env_local.exists() else "[yellow]WARN[/yellow]",
    )

    last_run_age_h: float | None = None
    run_report_status = "[red]FAIL: 없음[/red]"
    _pw_unverified: int = 0
    _pw_unverified_oldest_h: float = 0.0
    _sc_age_h: float = 0.0
    _sc_warn_reason: str = ""
    store = None
    if db_exists:
        try:
            store = Store(db_path)
            since = utc_now() - timedelta(hours=168)
            reports = store.recent_run_reports(since=since, limit=5)
            if reports:
                last_rpt = reports[0]
                last_at = last_rpt.created_at
                age_h = (utc_now() - last_at).total_seconds() / 3600
                last_run_age_h = age_h
                age_label = f"{age_h:.1f}h"
                if age_h <= 6:
                    run_report_status = f"[green]OK ({age_label})[/green]"
                elif age_h <= 12:
                    run_report_status = f"[yellow]WARN ({age_label})[/yellow]"
                else:
                    run_report_status = f"[red]FAIL ({age_label})[/red]"
                db_table.add_row("마지막 run_report", _kst(last_at), run_report_status)

                # Recent 5
                for i, rpt in enumerate(reports[:5], 1):
                    db_table.add_row(
                        f"  run_report #{i}",
                        _kst(rpt.created_at),
                        rpt.mode or "unknown",
                    )
            else:
                db_table.add_row("마지막 run_report", "없음", "[red]FAIL[/red]")
        except Exception as exc:
            db_table.add_row("DB 연결", str(exc)[:60], "[red]ERROR[/red]")

        # pair_watch_history latest
        try:
            store2 = Store(db_path)
            pw_rows = store2.recent_pair_watch_signals(since=utc_now() - timedelta(hours=168))
            if pw_rows:
                from tele_quant.models import parse_dt

                pw_last = max(r.get("created_at", "") for r in pw_rows)
                pw_dt = parse_dt(pw_last)
                pw_age = (utc_now() - pw_dt).total_seconds() / 3600 if pw_dt else 999
                db_table.add_row(
                    "pair_watch_history 최근",
                    _kst(pw_dt) if pw_dt else "알 수 없음",
                    f"[dim]{pw_age:.1f}h 전[/dim]",
                )
            else:
                db_table.add_row("pair_watch_history 최근", "없음", "[dim]저장 없음[/dim]")
        except Exception:
            pass

        # pair_watch cleanup state
        try:
            store_pw = Store(db_path)
            pw_stats = store_pw.pair_watch_cleanup_stats()
            _pw_unverified = pw_stats.get("unverified_legacy", 0)
            with store_pw.connect() as _conn:
                _exact = _conn.execute(
                    "SELECT COUNT(*) FROM pair_watch_history"
                    " WHERE backfill_source='exact_date_close'"
                    " AND (archived IS NULL OR archived=0)"
                ).fetchone()[0]
                _nearest = _conn.execute(
                    "SELECT COUNT(*) FROM pair_watch_history"
                    " WHERE backfill_source='nearest_trading_day_close'"
                    " AND (archived IS NULL OR archived=0)"
                ).fetchone()[0]
                _failed = _conn.execute(
                    "SELECT COUNT(*) FROM pair_watch_history"
                    " WHERE backfill_source='failed_no_price'"
                    " AND (archived IS NULL OR archived=0)"
                ).fetchone()[0]
                _archived_cnt = _conn.execute(
                    "SELECT COUNT(*) FROM pair_watch_history WHERE archived=1"
                ).fetchone()[0]
                _oldest_unverified_row = _conn.execute(
                    "SELECT created_at FROM pair_watch_history"
                    " WHERE backfill_status='unverified_legacy_backfill'"
                    " AND (archived IS NULL OR archived=0)"
                    " ORDER BY created_at ASC LIMIT 1"
                ).fetchone()
            if _oldest_unverified_row and _oldest_unverified_row[0]:
                from tele_quant.models import parse_dt as _parse_dt2
                _ov_dt = _parse_dt2(_oldest_unverified_row[0])
                _pw_unverified_oldest_h = (
                    (utc_now() - _ov_dt).total_seconds() / 3600 if _ov_dt else 0.0
                )
            if _pw_unverified == 0:
                pw_cleanup_status = "[green]OK - unverified 0개[/green]"
            elif _pw_unverified_oldest_h <= 24:
                pw_cleanup_status = (
                    f"[yellow]WARN: unverified {_pw_unverified}개"
                    f" (최대 {_pw_unverified_oldest_h:.0f}h) - 장 마감 후 재실행[/yellow]"
                )
            else:
                pw_cleanup_status = (
                    f"[red]FAIL: unverified {_pw_unverified}개"
                    f" ({_pw_unverified_oldest_h:.0f}h 방치)[/red]"
                )
            db_table.add_row(
                "pair-watch cleanup",
                f"exact={_exact} / nearest={_nearest} / failed={_failed}"
                f" / unverified={_pw_unverified} / archived={_archived_cnt}",
                pw_cleanup_status,
            )
        except Exception:
            pass

        # scenario_history latest + 이유 진단 + WARN if stale
        try:
            store3 = Store(db_path)
            sc_rows = store3.recent_scenarios(since=utc_now() - timedelta(hours=168))
            if sc_rows:
                from tele_quant.models import parse_dt

                sc_last = max(r.get("created_at", "") for r in sc_rows)
                sc_dt = parse_dt(sc_last)
                sc_age = (utc_now() - sc_dt).total_seconds() / 3600 if sc_dt else 999
                _sc_age_h = sc_age
                sent_rows = [r for r in sc_rows if r.get("sent") == 1]
                sent_high = [r for r in sent_rows if r.get("score", 0) >= 80]
                sc_note = f"{sc_age:.1f}h 전 (전체 {len(sc_rows)}개"
                if sent_rows:
                    sc_note += f", sent={len(sent_rows)}"
                if sent_high:
                    sc_note += f", 80+ sent={len(sent_high)}"
                sc_note += ")"

                # 판정: sent=1 & 80+ 있으면 OK, 오래됐으면 WARN 이유 표시
                run_rows_24h = store3.recent_run_reports(since=utc_now() - timedelta(hours=24))
                sent_runs_24h = [
                    r for r in run_rows_24h if (getattr(r, "stats", None) or {}).get("sent")
                ]
                if sc_age > 24:
                    if not sent_runs_24h:
                        sc_status = "[dim]OK - no-send/no_llm preview만 실행됨[/dim]"
                    elif not sent_high:
                        _sc_warn_reason = "80점 이상 후보 없음 (sent 실행 있음)"
                        sc_status = f"[yellow]WARN: {sc_age:.0f}h - {_sc_warn_reason}[/yellow]"
                    else:
                        sc_status = f"[dim]{sc_note}[/dim]"
                else:
                    sc_status = f"[green]OK ({sc_age:.1f}h)[/green]"

                db_table.add_row(
                    "scenario_history 최근",
                    _kst(sc_dt) if sc_dt else "알 수 없음",
                    sc_status,
                )
            else:
                # 이유 진단: 왜 비어 있는가?
                run_rows_24h = store3.recent_run_reports(since=utc_now() - timedelta(hours=24))
                sent_runs = [
                    r for r in run_rows_24h if (getattr(r, "stats", None) or {}).get("sent")
                ]
                if not sent_runs:
                    sc_reason = "no-send 모드만 실행됨 (send=false)"
                    sc_status_empty = f"[dim]{sc_reason}[/dim]"
                else:
                    sc_reason = "80점 이상 후보 없음 (sent 실행은 있음)"
                    _sc_warn_reason = sc_reason
                    sc_status_empty = f"[yellow]WARN: {sc_reason}[/yellow]"
                db_table.add_row("scenario_history 최근", "없음", sc_status_empty)
        except Exception:
            pass

    console.print(db_table)

    # --- Recommendations ---
    console.rule("[dim]진단 결과 및 권장 조치[/dim]")
    recs: list[str] = []

    if not timer_ok:
        recs.append(
            "[red]FAIL: timer가 inactive 또는 disabled[/red]\n"
            "  권장 조치:\n"
            "    cp systemd/tele-quant-cycle-*.service systemd/tele-quant-cycle-*.timer ~/.config/systemd/user/\n"
            "    cp systemd/tele-quant-price-alert.* ~/.config/systemd/user/\n"
            "    systemctl --user daemon-reload\n"
            "    systemctl --user enable --now tele-quant-cycle-monday-open.timer\n"
            "    systemctl --user enable --now tele-quant-cycle-weekday-4h.timer\n"
            "    systemctl --user enable --now tele-quant-cycle-weekend-issue.timer\n"
            "    systemctl --user enable --now tele-quant-cycle-sunday-review.timer\n"
            "    systemctl --user enable --now tele-quant-cycle-surge-collector.timer\n"
            "    systemctl --user enable --now tele-quant-cycle-maintenance.timer\n"
            "    systemctl --user enable --now tele-quant-price-alert.timer"
        )

    if _pw_unverified > 0 and _pw_unverified_oldest_h > 24:
        recs.append(
            f"[red]FAIL: pair-watch unverified legacy {_pw_unverified}개"
            f" ({_pw_unverified_oldest_h:.0f}h 방치)[/red]\n"
            "  pair-watch-cleanup --apply를 실행하거나 timer 동작을 확인하세요.\n"
            "  수동 실행: uv run tele-quant pair-watch-cleanup --apply"
        )
    elif _pw_unverified > 0:
        recs.append(
            f"[yellow]WARN: pair-watch unverified {_pw_unverified}개"
            f" - 장 마감 후 자동 정리 예정[/yellow]\n"
            "  장 중이거나 당일 미개장 종목일 수 있음.\n"
            "  즉시 정리: uv run tele-quant pair-watch-cleanup --apply"
        )

    if last_run_age_h is not None and last_run_age_h > 12:
        recs.append(
            "[red]FAIL: 마지막 run_report가 12시간 초과[/red]\n"
            "  수동 실행: DIGEST_MODE=no_llm uv run tele-quant once --no-send\n"
            "  WSL이 꺼져 있었다면 systemd timer missed run 가능성 있음\n"
            "  → WSL을 켜두거나 Persistent=true 확인"
        )
    elif last_run_age_h is not None and last_run_age_h > 6:
        recs.append(
            "[yellow]WARN: 마지막 run_report가 6~12시간 전[/yellow]\n"
            "  정상 범위이나 4H 주기 대비 약간 늦음. timer 상태 확인 권장"
        )

    # scenario_history WARN - sent=True 리포트 있지만 80점 이상 후보 없음이 5일+ 지속
    if _sc_warn_reason and _sc_age_h > 120:
        recs.append(
            f"[yellow]WARN: scenario_history {_sc_age_h:.0f}h ({_sc_warn_reason})[/yellow]\n"
            "  5일 이상 LONG/SHORT 80점 이상 신호 없음 - direct evidence gate 과도 가능성\n"
            "  진단: uv run tele-quant lint-report --hours 24"
        )

    # Sentiment history freshness check
    if store is not None and db_exists:
        try:
            sentiment_rows = store.recent_sentiment_history(since=utc_now() - timedelta(hours=12))
            if not sentiment_rows:
                console.print("- sentiment_history: 최근 12h 없음 (fast/no_llm 미실행 또는 첫 실행)")
            else:
                latest_sent = sentiment_rows[0]
                from tele_quant.models import parse_dt
                sent_dt = parse_dt(latest_sent.get("created_at") or "")
                if sent_dt:
                    sent_age_h = (utc_now() - sent_dt).total_seconds() / 3600
                    sector_counts: dict[str, int] = {}
                    for row in sentiment_rows:
                        sec = row.get("sector") or "Unknown"
                        sector_counts[sec] = sector_counts.get(sec, 0) + 1
                    top_sectors = sorted(sector_counts, key=lambda s: -sector_counts[s])[:3]
                    console.print(
                        f"- sentiment_history: {sent_age_h:.1f}h 전 업데이트 "
                        f"({len(sentiment_rows)}건, 섹터: {', '.join(top_sectors)})"
                    )
                    if sent_age_h > 8:
                        recs.append(
                            f"[yellow]WARN: sentiment_history {sent_age_h:.0f}h 전 (8h 초과)[/yellow]\n"
                            "  fast 모드 리포트가 실행되지 않았을 수 있음"
                        )
        except Exception:
            pass

    # --- External indicators diagnostics ---
    console.rule("[dim]외부 지표 진단[/dim]")
    ext_settings = _settings()
    # FRED API 키
    fred_key = getattr(ext_settings, "fred_api_key", "")
    if fred_key:
        console.print("[green]FRED_API_KEY: 설정됨[/green]")
    else:
        console.print("[yellow]FRED_API_KEY: 미설정 (yfinance fallback 사용 중)[/yellow]")
        recs.append(
            "[yellow]INFO: FRED_API_KEY 미설정[/yellow]\n"
            "  .env.local에 FRED_API_KEY=your_key 추가하면 연준 공식 금리/실업률 데이터 수집\n"
            "  무료 발급: https://fred.stlouisfed.org/docs/api/api_key.html"
        )
    # Fear & Greed 최근 기록
    if db_exists and store is not None:
        try:
            fg_rows = store.recent_fear_greed(since=utc_now() - timedelta(hours=12))
            if fg_rows:
                from tele_quant.models import parse_dt as _parse_dt
                fg_latest_dt = _parse_dt(fg_rows[0].get("created_at") or "")
                fg_age_h = (utc_now() - fg_latest_dt).total_seconds() / 3600 if fg_latest_dt else 999
                fg_score = fg_rows[0].get("score")
                fg_rating = fg_rows[0].get("rating_ko") or fg_rows[0].get("rating") or ""
                console.print(
                    f"Fear&Greed 최근: {fg_score:.0f}/100 [{fg_rating}]"
                    f"  ({fg_age_h:.1f}h 전)"
                )
                if fg_age_h > 8:
                    recs.append(
                        f"[yellow]WARN: Fear&Greed {fg_age_h:.0f}h 전 (8h 초과)[/yellow]\n"
                        "  fear_greed_enabled=false 또는 네트워크 문제일 수 있음"
                    )
            else:
                console.print("[dim]Fear&Greed: 최근 12h 기록 없음 (첫 실행 또는 비활성화)[/dim]")
        except Exception:
            pass
    # EIA 에너지 API 키
    eia_key = getattr(ext_settings, "eia_api_key", "")
    if eia_key:
        console.print("[green]EIA_API_KEY: 설정됨 (WTI/천연가스 실시간 가격)[/green]")
    else:
        console.print("[dim]EIA_API_KEY: 미설정 (에너지 가격 비활성화)[/dim]")

    # ECOS 한국은행 API 키
    ecos_key = getattr(ext_settings, "ecos_api_key", "")
    if ecos_key:
        console.print("[green]ECOS_API_KEY: 설정됨 (한국은행 기준금리/환율)[/green]")
    else:
        console.print(
            "[dim]ECOS_API_KEY: 미설정 (한국은행 데이터 비활성화)\n"
            "  .env.local에 ECOS_API_KEY=your_key 추가 - 무료: https://ecos.bok.or.kr[/dim]"
        )

    # RSS 뉴스
    rss_ok = getattr(ext_settings, "rss_enabled", True)
    _rss_col = "green" if rss_ok else "dim"
    _rss_lbl = "활성화" if rss_ok else "비활성화"
    console.print(
        f"[{_rss_col}]RSS 뉴스: {_rss_lbl}"
        f" (PR Newswire / GlobeNewswire / BusinessWire / Google News)[/{_rss_col}]"
    )

    # SEC EDGAR
    sec_ok = getattr(ext_settings, "sec_enabled", True)
    _sec_col = "green" if sec_ok else "dim"
    _sec_lbl = "활성화" if sec_ok else "비활성화"
    console.print(
        f"[{_sec_col}]SEC EDGAR 8-K: {_sec_lbl} (미국 주식 직접증거)[/{_sec_col}]"
    )

    # ECB / Frankfurter
    ecb_ok = getattr(ext_settings, "ecb_enabled", True)
    fr_ok = getattr(ext_settings, "frankfurter_enabled", True)
    console.print(
        f"ECB 금리: {'[green]활성화[/green]' if ecb_ok else '[dim]비활성화[/dim]'}"
        f"  Frankfurter 환율: {'[green]활성화[/green]' if fr_ok else '[dim]비활성화[/dim]'}"
    )

    # OpenDART
    dart_ok = getattr(ext_settings, "opendart_enabled", True)
    dart_key = bool(getattr(ext_settings, "opendart_api_key", ""))
    if dart_ok and dart_key:
        console.print("[green]OpenDART: 활성화 + API 키 설정됨 (한국 공시)[/green]")
    elif dart_ok:
        console.print("[yellow]OpenDART: 활성화 - API 키 미설정 (OPENDART_API_KEY 필요)[/yellow]")
        recs.append("[yellow]WARN OpenDART: OPENDART_API_KEY 설정 시 한국 공시 수집 가능[/yellow]")
    else:
        console.print("[dim]OpenDART: 비활성화[/dim]")

    # Finnhub
    fh_ok = getattr(ext_settings, "finnhub_enabled", True)
    fh_key = bool(getattr(ext_settings, "finnhub_api_key", ""))
    if fh_ok and fh_key:
        console.print("[green]Finnhub: 활성화 + API 키 설정됨 (미국 뉴스 + 경제 캘린더)[/green]")
    elif fh_ok:
        console.print("[yellow]Finnhub: 활성화 - API 키 미설정 (FINNHUB_API_KEY 필요)[/yellow]")
        recs.append("[yellow]WARN Finnhub: FINNHUB_API_KEY 설정 시 미국 뉴스 + 경제 캘린더 활성화[/yellow]")
    else:
        console.print("[dim]Finnhub: 비활성화[/dim]")

    # pytrends 설치 여부
    try:
        import importlib
        importlib.import_module("pytrends")
        console.print("[green]pytrends: 설치됨 (Google Trends 활성화)[/green]")
    except ImportError:
        console.print("[dim]pytrends: 미설치 (Google Trends 비활성화 - 선택사항)[/dim]")
    # narrative_history 최근 기록
    if db_exists and store is not None:
        try:
            nar_rows = store.recent_narratives(since=utc_now() - timedelta(hours=12))
            if nar_rows:
                from tele_quant.models import parse_dt as _parse_dt2
                nar_dt = _parse_dt2(nar_rows[0].get("created_at") or "")
                nar_age_h = (utc_now() - nar_dt).total_seconds() / 3600 if nar_dt else 999
                console.print(f"narrative_history 최근: {nar_age_h:.1f}h 전 ({len(nar_rows)}건/12h)")
            else:
                console.print("[dim]narrative_history: 최근 12h 없음 (smart_read 미실행)[/dim]")
        except Exception:
            pass

    if not recs:
        console.print("[green]이상 없음 - 자동 실행 정상[/green]")
    else:
        for rec in recs:
            console.print(rec)

    # Relation feed (self-computed)
    console.rule("[dim]relation feed 상태[/dim]")
    try:
        from tele_quant.relation_feed import load_relation_feed

        rf = load_relation_feed(settings)
        if not rf.available:
            console.print("  [dim]relation feed: 없음 (yfinance 오류)[/dim]")
        else:
            fb_count = len(rf.fallback_candidates)
            console.print(
                f"  [green]relation feed: OK - "
                f"스캔={rf.summary.price_rows if rf.summary else 0}개 "
                f"/ movers={len(rf.movers)} / 상관관계 후보={fb_count}[/green]"
            )
    except Exception as _rf_exc:
        console.print(f"  [dim]relation feed 확인 실패: {_rf_exc}[/dim]")

    # Alias book summary
    console.rule("[dim]alias book 상태[/dim]")
    try:
        from tele_quant.alias_audit import run_audit as _alias_run_audit
        from tele_quant.analysis.aliases import load_alias_config as _load_ac

        _book = _load_ac()
        _total_syms = len(_book.all_symbols)
        _audit_entries = _alias_run_audit()
        _high_cnt = sum(1 for e in _audit_entries if e.severity == "HIGH")
        _med_cnt = sum(1 for e in _audit_entries if e.severity == "MEDIUM")
        if _high_cnt > 0:
            console.print(
                f"  [red]WARN: alias HIGH 이슈 {_high_cnt}건[/red]"
                f" (총 {_total_syms}개 심볼)"
                " - alias-audit 명령으로 확인"
            )
        elif _med_cnt > 10:
            console.print(
                f"  [yellow]alias MEDIUM 이슈 {_med_cnt}건[/yellow]"
                f" (총 {_total_syms}개 심볼)"
            )
        else:
            console.print(f"  [green]alias book OK: {_total_syms}개 심볼, HIGH 이슈 없음[/green]")
    except Exception as _al_exc:
        console.print(f"  [dim]alias book 확인 실패: {_al_exc}[/dim]")

    console.print()
    console.print("[dim]WARN: WSL/Ubuntu가 꺼져 있으면 systemd user timer도 실행되지 않습니다.[/dim]")
    console.print(
        "[dim]  Persistent=true는 missed run을 보완하지만, WSL이 시작되어야 동작합니다.[/dim]"
    )
    console.print(
        "[dim]  7시 리포트를 반드시 받으려면 WSL을 켜두거나 Windows Task Scheduler로 WSL을 깨워야 합니다.[/dim]"
    )


@app.command("lint-report")
def lint_report(
    hours: Annotated[
        float, typer.Option("--hours", help="최근 몇 시간치 DB 리포트를 검사할지")
    ] = 4.0,
    limit: Annotated[int, typer.Option("--limit", help="최대 검사 리포트 수")] = 10,
) -> None:
    """최근 리포트의 품질 문제를 검사합니다 (브로커명 유출·근거 오류·SHORT 게이트 위반 등).

    Example: uv run tele-quant lint-report --hours 4
    """
    import re as _re
    from datetime import datetime as _datetime
    from datetime import timedelta

    from rich.markup import escape

    from tele_quant.db import Store
    from tele_quant.headline_cleaner import (
        apply_final_report_cleaner,
        is_broker_header_only,
        is_low_quality_headline,
    )
    from tele_quant.models import utc_now

    def _read_report_field(row: object, name: str, default: str = "") -> str:
        val = row.get(name, default) if isinstance(row, dict) else getattr(row, name, default)  # type: ignore[union-attr]
        if val is None:
            return default
        if isinstance(val, _datetime):
            return val.strftime("%Y-%m-%d %H:%M")
        return str(val) if val else default

    _BROKER_HEADER_RES = [
        _re.compile(
            r"\b(?:Hana\s+Global\s+Guru\s+Eye|유안타\s*리서치센터|"
            r"하나증권\s*해외주식분석|키움증권\s*미국\s*주식\s*박기현|"
            r"연합인포맥스|ShowHashtag|S&P\s*500\s*map|"
            r"모닝\s*브리핑|프리마켓\s*뉴스|ShowBotCommand)\b",
            _re.IGNORECASE,
        ),
    ]
    # Expanded forbidden patterns: additional noise patterns from Telegram export
    _EXTRA_NOISE_RES = [
        _re.compile(r"\btel:\s*\+?\d", _re.IGNORECASE),
        _re.compile(r"\bhref\s*=", _re.IGNORECASE),
        _re.compile(r"제목\s*:", _re.IGNORECASE),
        _re.compile(r"카테고리\s*:", _re.IGNORECASE),
        _re.compile(r"증권사\s*/?\s*출처\s*:", _re.IGNORECASE),
        _re.compile(r"원문\s*/?\s*목록\s*텍스트\s*:", _re.IGNORECASE),
    ]
    # Broker false-positive: broker name appearing as stock candidate (not as source)
    # These appear when broker name leaks into LONG/SHORT section header/reasons
    _BROKER_AS_CANDIDATE_RE = _re.compile(
        r"(?:JPMorgan\s*(?:Chase)?|Goldman\s*Sachs|Morgan\s*Stanley|"
        r"JP모건|제이피모건|골드만삭스|모건스탠리|씨티|뱅크오브아메리카|BofA|Wedbush|"
        r"Piper\s+Sandler|Jefferies|HSBC)\s*/\s*(?:JPM|GS|MS|C|BAC|DB)",
        _re.IGNORECASE,
    )
    # Broker name raw leak in digest/analysis (report body should not name brokers directly).
    # Exclude legitimate stock listings: "Morgan Stanley (MS)" or broker prefix "JP모건)" patterns.
    _BROKER_NAME_LEAK_RE = _re.compile(
        r"\b(?:JPMorgan(?:\s+Chase)?|Goldman\s+Sachs|Morgan\s+Stanley|"
        r"JP모건|제이피모건|골드만삭스|모건스탠리|뱅크오브아메리카|BofA|"
        r"Wedbush|Piper\s+Sandler|Jefferies)"
        r"(?!\s*\([A-Z]{1,5}\))"  # NOT followed by "(TICKER)" - that's a legitimate stock listing
        r"(?!\))",                 # NOT followed by ")" - that's a broker-prefix tag (already handled)
        _re.IGNORECASE,
    )
    _FORBIDDEN_WORDS = [
        "ACTION_READY",
        "LIVE_READY",
        "무조건 매수",
        "매수 권장",
        "매도 권장",
        "반드시 상승",
        "확정 수익",
        "자동매매",
        "실계좌 주문",
        "수혜 확정",
        "피해 확정",
    ]
    _NOISE_PATTERNS = [
        _re.compile(r"tel:|href=|ShowHashtag|연합인포맥스", _re.IGNORECASE),
        _re.compile(r"\d{2,3}[-–]\d{3,4}[-–]\d{4}"),  # phone numbers  # noqa: RUF001
    ]

    settings = _settings()
    store = Store(settings.sqlite_path)
    since = utc_now() - timedelta(hours=hours)
    reports = store.recent_run_reports(since=since, limit=limit)

    global_issues: list[str] = []

    # DB freshness check
    all_recent = store.recent_run_reports(since=utc_now() - timedelta(hours=12), limit=1)
    if not all_recent:
        global_issues.append(
            "[red]FAIL: 최근 12시간 run_report 없음[/red] - timer 실패 또는 WSL 재시작 필요"
        )

    # pair_watch_history check
    pw_rows = store.recent_pair_watch_signals(since=utc_now() - timedelta(hours=24))
    if not pw_rows:
        global_issues.append("[yellow]WARN: 최근 24시간 pair_watch_history 저장 없음[/yellow]")

    # pair_watch cleanup state check
    try:
        _pw_stats = store.pair_watch_cleanup_stats()
        _pw_unverified_lint = _pw_stats.get("unverified_legacy", 0)
        if _pw_unverified_lint > 0:
            global_issues.append(
                f"[yellow]WARN: pair_watch unverified legacy {_pw_unverified_lint}개[/yellow]"
                " - 장 마감 후 pair-watch-cleanup --apply 실행 필요"
            )
        with store.connect() as _lc:
            _pw_failed_lint = _lc.execute(
                "SELECT COUNT(*) FROM pair_watch_history"
                " WHERE backfill_source='failed_no_price'"
                " AND (archived IS NULL OR archived=0)"
            ).fetchone()[0]
        if _pw_failed_lint > 0:
            global_issues.append(
                f"[yellow]WARN: pair_watch failed_no_price {_pw_failed_lint}개[/yellow]"
                " - yfinance 조회 실패. pair-watch-cleanup --apply 재실행 또는 네트워크 확인"
            )
    except Exception:
        pass

    # scenario_history check (most recent) with reason diagnosis
    sc_rows_recent = store.recent_scenarios(since=utc_now() - timedelta(hours=24))
    if not sc_rows_recent:
        run_rows_sent = store.recent_run_reports(since=utc_now() - timedelta(hours=24))
        sent_runs = [r for r in run_rows_sent if (getattr(r, "stats", None) or {}).get("sent")]
        if not sent_runs:
            sc_reason = "no-send 모드만 실행됨 - 실제 전송 시에만 저장"
        else:
            sc_reason = "80점 이상 후보 없음 (sent 실행은 있음)"
        global_issues.append(
            f"[yellow]WARN: 최근 24시간 scenario_history 저장 없음[/yellow] ({sc_reason})"
        )

    if global_issues:
        console.rule("[bold red]DB 상태 경보[/bold red]")
        for gi in global_issues:
            console.print(f"  {gi}")

    if not reports:
        console.print(f"[yellow]검사할 리포트 없음 (최근 {hours}h)[/yellow]")
        if global_issues:
            raise SystemExit(1)
        return

    console.print(f"[bold]lint-report: {len(reports)}개 리포트 검사[/bold] (최근 {hours}h)")

    # Check scenario_history for LONG ≥ 80 coverage
    scenario_rows = store.recent_scenarios(since=since, side="LONG", min_score=80)
    long80_saved = len(scenario_rows)
    long80_with_price = sum(1 for r in scenario_rows if r.get("close_price_at_report") is not None)

    total_issues = 0
    for row in reports:
        digest_raw = _read_report_field(row, "digest") or _read_report_field(row, "digest_text")
        analysis_raw = _read_report_field(row, "analysis") or _read_report_field(
            row, "analysis_text"
        )
        created_raw = _read_report_field(row, "created_at")
        created = created_raw[:16] if created_raw else "unknown"
        # Apply cleaner before checking: only patterns that BYPASS the cleaner are real bugs
        digest = apply_final_report_cleaner(digest_raw)
        analysis = apply_final_report_cleaner(analysis_raw)
        full_text = digest + "\n" + analysis

        row_issues: list[str] = []

        # 1. Noise header residuals
        for pat in _BROKER_HEADER_RES:
            for m in pat.finditer(full_text):
                ctx_s = max(0, m.start() - 30)
                ctx_e = min(len(full_text), m.end() + 30)
                snippet = full_text[ctx_s:ctx_e].replace("\n", " ").strip()
                row_issues.append(f"[yellow]노이즈헤더 잔류:[/yellow] ...{escape(snippet[:80])}...")
                break

        # 2. Broker as stock candidate false-positive
        if analysis and _BROKER_AS_CANDIDATE_RE.search(analysis):
            m2 = _BROKER_AS_CANDIDATE_RE.search(analysis)
            assert m2
            row_issues.append(
                f"[red]브로커 종목 오인:[/red] {escape(m2.group())} - 브로커명이 종목 후보로 표시됨"
            )

        # 2b. Broker name raw leak in report body
        m_broker = _BROKER_NAME_LEAK_RE.search(full_text)
        if m_broker:
            row_issues.append(
                f"[yellow]브로커명 잔류:[/yellow] '{escape(m_broker.group())}' - 리포트 본문에 브로커명 직접 노출"
            )

        # 3. Broker-header-only lines
        for line in full_text.splitlines():
            line = line.strip()
            if len(line) > 3 and is_broker_header_only(line):
                row_issues.append(f"[yellow]브로커헤더 잔류:[/yellow] {escape(line[:80])}")
            elif len(line) > 3 and is_low_quality_headline(line):
                row_issues.append(f"[dim]저품질 라인:[/dim] {escape(line[:80])}")

        # 4. Forbidden expressions
        for fw in _FORBIDDEN_WORDS:
            if fw in full_text:
                row_issues.append(f"[red]금지표현:[/red] '{fw}'")

        # 5. Metadata residuals
        for pat_str in [r"^link\s*:", r"^카테고리\s*:", r"^출처\s*:"]:
            if _re.search(pat_str, full_text, _re.IGNORECASE | _re.MULTILINE):
                row_issues.append(f"[yellow]메타데이터 잔류:[/yellow] {pat_str[:20]}")

        # 6. Phone / link noise in analysis reasons
        if analysis:
            for npat in _NOISE_PATTERNS:
                m3 = npat.search(analysis)
                if m3:
                    ctx_s = max(0, m3.start() - 20)
                    ctx_e = min(len(analysis), m3.end() + 20)
                    snippet = analysis[ctx_s:ctx_e].replace("\n", " ")
                    row_issues.append(f"[yellow]노이즈 문장:[/yellow] {escape(snippet[:80])}")
                    break

        # 7. SHORT gate violation: check for 상승 추세 + OBV 상승 near SHORT section
        if analysis:
            short_section = _re.search(r"🔴\s*숏.+?(?=🟡|🟢|─|$)", analysis, _re.DOTALL)
            if short_section:
                sblock = short_section.group()
                if "상승 추세" in sblock and "OBV: 상승" in sblock:
                    row_issues.append(
                        "[red]SHORT 게이트 위반:[/red] 상승 추세 + OBV 상승인데 숏 후보 표시"
                    )

        # 8. Extra noise patterns (제목:, 카테고리:, tel:, href=, etc.)
        for npat in _EXTRA_NOISE_RES:
            m_ex = npat.search(full_text)
            if m_ex:
                ctx_s = max(0, m_ex.start() - 10)
                ctx_e = min(len(full_text), m_ex.end() + 30)
                snippet = full_text[ctx_s:ctx_e].replace("\n", " ").strip()
                row_issues.append(f"[yellow]확장 노이즈:[/yellow] {escape(snippet[:80])}")
                break

        if row_issues:
            total_issues += 1
            console.rule(f"[bold]{created}[/bold]")
            for issue in row_issues[:12]:
                console.print(f"  {issue}")

    # Candidate scoring diagnosis - no candidates above min score 상황 진단
    console.rule("[dim]후보 점수 진단[/dim]")
    all_sc = store.recent_scenarios(since=since)
    sc_all_count = len(all_sc)
    sc_above_50 = sum(1 for r in all_sc if (r.get("score") or 0) >= 50)
    sc_above_80 = sum(1 for r in all_sc if (r.get("score") or 0) >= 80)
    sc_max_score = max((r.get("score") or 0) for r in all_sc) if all_sc else 0
    console.print(f"  기간 내 전체 후보: {sc_all_count}개")
    console.print(f"  점수 ≥50: {sc_above_50}개 / 점수 ≥80: {sc_above_80}개")
    console.print(f"  최고 점수: {sc_max_score:.0f}점")
    if sc_all_count > 0 and sc_above_50 == 0:
        console.print(
            "  [yellow]WARN: 50점 이상 후보 없음 - direct evidence gate 과도 가능성[/yellow]"
        )
        # 분류 이유 추정
        no_price = sum(
            1
            for r in all_sc
            if r.get("signal_price") is None and r.get("close_price_at_report") is None
        )
        low_evidence = sum(1 for r in all_sc if (r.get("direct_evidence_count") or 0) == 0)
        if low_evidence > 0:
            console.print(
                f"  → direct_evidence_count=0인 후보: {low_evidence}개"
                " (broker/header 제거로 직접 근거 없는 후보)"
            )
        if no_price > 0:
            console.print(f"  → 가격 없는 후보: {no_price}개")
    # score=44 전수 진단 (direct evidence gate 완전 차단 시 발생)
    sc_score_44 = sum(1 for r in all_sc if 43 <= (r.get("score") or 0) <= 45)
    if sc_all_count > 0 and sc_score_44 == sc_all_count:
        console.print(
            f"  [red]WARN: 전 후보 점수=44 ({sc_score_44}개) - direct evidence gate 완전 차단[/red]"
        )
        console.print(
            "  → ticker symbol(Pass 3) 또는 $TICKER(Pass 4) 검색 결과 확인 필요"
        )
    elif sc_above_50 == 0 and sc_all_count == 0:
        console.print("  [dim]해당 기간 scenario_history 저장 없음[/dim]")
    else:
        console.print("  [green]후보 점수 분포 정상[/green]")

    # Scenario history coverage check
    console.rule("[dim]scenario_history 커버리지[/dim]")
    console.print(f"  LONG ≥80 저장: {long80_saved}개 (가격 있음: {long80_with_price}개)")
    # Count how many reports have analysis with LONG section
    reports_with_long = sum(
        1 for r in reports if ("🟢 롱 관심 후보" in (_read_report_field(r, "analysis") or ""))
    )
    if reports_with_long > 0 and long80_saved == 0:
        console.print(
            f"  [red]WARN: LONG 섹션이 있는 리포트 {reports_with_long}개인데 scenario_history 저장 0[/red]"
        )
        console.print("  권장 조치: pipeline의 save_scenarios 호출 경로 확인")
    elif long80_saved > 0 and long80_with_price == 0:
        console.print(
            "  [yellow]WARN: 저장됐지만 가격 없음 → weekly 성과 리뷰 비어 있을 수 있음[/yellow]"
        )
    else:
        console.print("  [green]scenario_history OK[/green]")

    # Sentiment history diagnosis
    console.rule("[dim]감성 히스토리 진단[/dim]")
    try:
        sentiment_rows = store.recent_sentiment_history(since=since)
        if not sentiment_rows:
            console.print("  [dim]sentiment_history: 기간 내 없음 (fast 모드 미실행 가능성)[/dim]")
        else:
            sector_avg: dict[str, list[float]] = {}
            for sr in sentiment_rows:
                sec = sr.get("sector") or "Unknown"
                sc_val = float(sr.get("sentiment_score") or 50.0)
                sector_avg.setdefault(sec, []).append(sc_val)
            console.print(f"  sentiment_history: {len(sentiment_rows)}건")
            for sec, vals in sorted(sector_avg.items()):
                avg = sum(vals) / len(vals)
                icon = "⬆" if avg >= 60 else "⬇" if avg <= 40 else "➡"
                console.print(f"  {icon} {sec}: 평균 {avg:.0f}/100 ({len(vals)}건)")
    except Exception as _sh_exc:
        console.print(f"  [dim]sentiment_history 조회 실패: {_sh_exc}[/dim]")

    # Relation feed (self-computed)
    console.rule("[dim]relation feed 상태[/dim]")
    try:
        from tele_quant.relation_feed import load_relation_feed

        rf = load_relation_feed(settings)
        if not rf.available:
            console.print("  [dim]relation feed: 없음 (yfinance 오류)[/dim]")
        else:
            fb_count = len(rf.fallback_candidates)
            console.print(
                f"  [green]relation feed: OK - "
                f"스캔={rf.summary.price_rows if rf.summary else 0}개 "
                f"/ movers={len(rf.movers)} / 상관관계 후보={fb_count}[/green]"
            )
    except Exception as _rf_exc:
        console.print(f"  [dim]relation feed 확인 실패: {_rf_exc}[/dim]")

    # Alias book summary
    console.rule("[dim]alias book 상태[/dim]")
    try:
        from tele_quant.alias_audit import run_audit
        from tele_quant.analysis.aliases import load_alias_config

        book = load_alias_config()
        total_syms = len(book.all_symbols)
        audit_entries = run_audit()
        high_cnt_alias = sum(1 for e in audit_entries if e.severity == "HIGH")
        med_cnt_alias = sum(1 for e in audit_entries if e.severity == "MEDIUM")
        if high_cnt_alias > 0:
            console.print(
                f"  [red]WARN: alias HIGH 이슈 {high_cnt_alias}건[/red]"
                f" (총 {total_syms}개 심볼)"
                " - alias-audit 명령으로 확인"
            )
        elif med_cnt_alias > 10:
            console.print(
                f"  [yellow]alias MEDIUM 이슈 {med_cnt_alias}건[/yellow]"
                f" (총 {total_syms}개 심볼)"
            )
        else:
            console.print(f"  [green]alias book OK: {total_syms}개 심볼, HIGH 이슈 없음[/green]")
    except Exception as _al_exc:
        console.print(f"  [dim]alias book 확인 실패: {_al_exc}[/dim]")

    has_failures = total_issues > 0 or bool(global_issues)

    if total_issues == 0:
        console.print("[green]품질 이슈 없음 (문제 없음)[/green]")
    else:
        console.print(f"[bold red]{total_issues}/{len(reports)} 리포트에 품질 이슈[/bold red]")

    if has_failures:
        raise SystemExit(1)


@app.command("output-lint")
def output_lint_cmd(
    file: Annotated[
        str, typer.Option("--file", help="검사할 리포트 파일 경로 (없으면 stdin 대기)")
    ] = "",
    html: Annotated[
        str, typer.Option("--html", help="Telegram export HTML 파일 경로")
    ] = "",
    fail_on_high: Annotated[
        bool, typer.Option("--fail-on-high", help="HIGH 이슈 발견 시 exit-code 1")
    ] = False,
    last: Annotated[
        int, typer.Option("--last", help="HTML 모드에서 최근 N개 메시지만 검사 (0=전체)")
    ] = 0,
) -> None:
    """Daily Alpha / 4H 브리핑 리포트 출력 품질 검사.

    Example: uv run tele-quant output-lint --file /tmp/daily_alpha.log
             uv run tele-quant output-lint --html /path/to/messages.html --last 20
             uv run tele-quant daily-alpha --market KR --no-send | uv run tele-quant output-lint --file /dev/stdin
    """
    import re as _re
    from pathlib import Path as _Path

    from rich.table import Table

    # ── HTML 모드: Telegram export HTML 파싱 ──────────────────────────────────
    if html:
        try:
            html_content = _Path(html).read_text(encoding="utf-8", errors="ignore")
        except FileNotFoundError:
            console.print(f"[red]HTML 파일 없음: {html}[/red]")
            raise SystemExit(1) from None

        # Extract message text from Telegram HTML export
        # Format: <div class="text">...</div> or <div class="body">...</div>
        msg_texts: list[tuple[str, str]] = []  # (msg_id_or_ts, text)
        _msg_id_re = _re.compile(r'<div class="message[^"]*"\s+id="message(\d+)"', _re.IGNORECASE)
        _text_re = _re.compile(r'<div class="text">(.*?)</div>', _re.IGNORECASE | _re.DOTALL)
        _date_re = _re.compile(r'<div class="date[^"]*"[^>]*title="([^"]+)"', _re.IGNORECASE)
        _tag_re = _re.compile(r"<[^>]+>")

        # Split by message blocks
        msg_blocks = _re.split(r'(?=<div class="message)', html_content)
        for block in msg_blocks:
            mid_m = _msg_id_re.search(block)
            msg_id = mid_m.group(1) if mid_m else "?"
            date_m = _date_re.search(block)
            ts = date_m.group(1) if date_m else ""
            text_m = _text_re.search(block)
            if text_m:
                raw = text_m.group(1)
                clean = _tag_re.sub("", raw).strip()
                if clean:
                    msg_texts.append((f"msg#{msg_id}({ts})", clean))

        if last > 0:
            msg_texts = msg_texts[-last:]

        if not msg_texts:
            console.print("[yellow]HTML에서 메시지 텍스트를 찾지 못했습니다.[/yellow]")
            return

        console.print(f"[dim]HTML 모드: {len(msg_texts)}개 메시지 검사[/dim]")
        text = "\n".join(t for _, t in msg_texts)
    elif file:
        # 검사 대상 텍스트 로드
        try:
            text = _Path(file).read_text(encoding="utf-8", errors="ignore")
        except FileNotFoundError:
            console.print(f"[red]파일 없음: {file}[/red]")
            raise SystemExit(1) from None
    else:
        import sys
        text = sys.stdin.read()

    lines_raw = text.splitlines()

    # ── 검사 규칙 ──────────────────────────────────────────────────────────────
    issues: list[dict[str, str]] = []

    def _check(severity: str, pattern: str, message: str, *, regex: bool = False) -> None:
        for ln, line in enumerate(lines_raw, 1):
            hit = (
                _re.search(pattern, line, _re.IGNORECASE)
                if regex else pattern in line
            )
            if hit:
                issues.append({
                    "severity": severity, "line": str(ln),
                    "pattern": pattern, "message": message,
                    "excerpt": line.strip()[:80],
                })

    # HIGH: 절대 출력 금지 메타 노이즈
    _check("HIGH", "Web발신", "Web발신 노이즈 잔류")
    _check("HIGH", "보고서링크:", "보고서링크 메타 잔류")
    _check("HIGH", "국장 마이너리티 리포트", "채널명 헤더 잔류")
    _check("HIGH", "안녕하세요", "브로커 인사말 잔류")
    _check("HIGH", r"IB\s*투자의견", "IB 투자의견 헤더 잔류", regex=True)
    _check("HIGH", r"글로벌\s*투자\s*구루\s*일일\s*브리핑", "글로벌 투자 구루 채널 헤더 잔류", regex=True)
    _check("HIGH", r"월가\s*주요\s*뉴스", "월가 주요 뉴스 헤더 잔류", regex=True)
    _check("HIGH", r"이익동향\s*\(\d+월\s*\d+주차\)", "이익동향 메타 헤더 잔류", regex=True)
    _check("HIGH", r"^   왜 지금: (?:치 |드 |이를 )", "왜지금 문장 조각", regex=True)
    # 줄 시작 조각 문장 - headline_cleaner를 우회한 fragment
    _check("HIGH", r"^치 후 |^드 플|^이를 정당화", "줄 시작 조각 문장 잔류", regex=True)
    # 잘못된 섹션 표기
    _check("HIGH", "숏/매도 경계", "숏/매도 경계 표기 잔류 - SHORT 관찰 경계로 교체 필요")
    _check("HIGH", "현재가 확인 불가", "현재가 확인 불가 텍스트 직접 노출 - 접힘 처리 누락")
    # unknown_price_only source가 연결고리 생성에 쓰인 경우
    _check(
        "HIGH",
        r"가격만 움직임\(이유 불명\).*연결고리",
        "unknown_price_only source가 연결고리 생성에 사용됨",
        regex=True,
    )
    # 라이브 확인 미실행 상세 반복 (2회 이상 = 접힘 처리 누락)
    _live_unconf_lines = [
        ln for ln, line_txt in enumerate(lines_raw, 1)
        if (
            "라이브 확인 미실행 - 통계만 참고" in line_txt
            or "라이브 확인 미실행 — 통계만 참고" in line_txt
        )
    ]
    if len(_live_unconf_lines) >= 2:
        issues.append({
            "severity": "HIGH",
            "line": str(_live_unconf_lines[1]),
            "pattern": "라이브 확인 미실행 상세 반복",
            "message": f"라이브 확인 미실행 - 통계만 참고 {len(_live_unconf_lines)}회 반복 - 접힘 처리 누락",
            "excerpt": lines_raw[_live_unconf_lines[1] - 1].strip()[:80],
        })

    # HIGH: KR 현재가 비정상 스케일 (삼성전자 ~55K~80K, SK하이닉스 ~180K~250K 정상)
    for suspicious_bb in ["BB.*311,0", "BB.*2,160,", "BB.*755,6", "BB.*1,715,"]:
        _check("HIGH", suspicious_bb, "기술지표 가격 스케일 이상 (미분할 추정)", regex=True)
    # 현재가 직접 스케일 이상 탐지 (1,000,000원 이상만 HIGH - 일반 고가주 오탐 방지)
    _check("HIGH", r"현재가.*[1-9],[0-9]{3},[0-9]{3}원",
           "KR 현재가 1,000,000원 이상 - 비정상 스케일 (yfinance 오류 가능성)", regex=True)
    # HIGH: bare 1~5자리 KR 티커 출력
    _check("HIGH", r"\([0-9]{1,5}\)", "1~5자리 bare 숫자 티커 출력 - zero-padding 누락", regex=True)
    # HIGH: 금지 표현
    _check("HIGH", "4H 매매 어드바이징", "4H 매매 어드바이징 표현 - '4H 퀀터멘탈 관찰 브리핑'으로 교체")
    _check("HIGH", "매수 권장", "매수 권장 금지 표현")
    _check("HIGH", "매도 권장", "매도 권장 금지 표현")
    _check("HIGH", "확정 수익", "확정 수익 금지 표현")
    _check("HIGH", "수익 보장", "수익 보장 금지 표현")
    _check("HIGH", "반드시 상승", "반드시 상승 금지 표현")
    _check("HIGH", "세력 매집 확정", "세력 매집 확정 금지 표현")
    _check("HIGH", "기관 매집 확정", "기관 매집 확정 금지 표현")
    # MEDIUM: 재무 이상치 무고지
    _check("MEDIUM", r"배당\s+\d{2,3}\.\d{1,2}%",
           "배당수익률 20%+ 출력에 이상치 경고 없음 - 데이터 확인 필요", regex=True)
    _check("MEDIUM", r"임상\s*(?:성공|완치|완전|반드시)",
           "임상 성공 단정 표현 금지", regex=True)

    # HIGH: pair-watch 방향 불일치
    _check("HIGH", r"4H -[1-9]\d?\.\d%.*급등 후", "음수 source에 급등 후 표현", regex=True)
    _check("HIGH", r"1D -[1-9]\d?\.\d%.*급등 후", "음수 1D source에 급등 후 표현", regex=True)
    _check("HIGH", r"4H \+[1-9]\d?\.\d%.*급락 후", "양수 source에 급락 후 표현", regex=True)
    _check("HIGH", r"1D \+[1-9]\d?\.\d%.*급락 후", "양수 1D source에 급락 후 표현", regex=True)

    # MEDIUM: 점수 구간 혼란 - 관망/추적 후보가 정식 후보 섹션에 없어야 함
    in_main_section = False
    for ln, line in enumerate(lines_raw, 1):
        if "LONG 관찰 후보" in line or "SHORT 관찰 후보" in line:
            in_main_section = True
        if "관망/추적 후보" in line or "⚠" in line:
            in_main_section = False
        if in_main_section:
            m = _re.search(r"최종점수:\s*(5\d+\.\d)", line)
            if m:
                issues.append({
                    "severity": "MEDIUM", "line": str(ln),
                    "pattern": "50점대 정식 후보",
                    "message": f"50점대({m.group(1)}) 후보가 정식 관찰 후보 섹션에 있음",
                    "excerpt": line.strip()[:80],
                })
            m2 = _re.search(r"최종점수:\s*6[0-9]\.\d", line)
            if m2:
                issues.append({
                    "severity": "MEDIUM", "line": str(ln),
                    "pattern": "60점대 정식 후보",
                    "message": "60점대 후보가 정식 관찰 후보 섹션에 있음 - 추적 후보여야 함",
                    "excerpt": line.strip()[:80],
                })

    # MEDIUM: 가격 스케일 불일치 후보가 정식 후보 섹션에 표시되는 경우
    _check("MEDIUM", "기술데이터 스케일 불일치", "가격 스케일 불일치 후보 출력 중", regex=False)

    # MEDIUM: 원/달러 환율 중복
    krw_lines = [ln for ln, line_text in enumerate(lines_raw, 1) if "원/달러" in line_text]
    if len(krw_lines) >= 2:
        issues.append({
            "severity": "MEDIUM", "line": str(krw_lines[1]),
            "pattern": "원/달러 환율 중복",
            "message": f"원/달러 환율 {len(krw_lines)}회 출력 - 중복 제거 필요",
            "excerpt": lines_raw[krw_lines[1] - 1].strip()[:80],
        })

    # LOW: 기타 노이즈
    _check("LOW", r"^   왜 지금: .*Report\s*\)", "Report) 메타 태그 왜지금에 잔류", regex=True)
    _check("LOW", r"근거: 약함", "증거 품질 WEAK 후보 출력 중", regex=True)
    _check("LOW", r"근거: 제거", "증거 품질 REJECT 후보 출력 중", regex=True)

    # HIGH: 수주잔고 허위/과장 표현 금지
    _check("HIGH", r"수주\s*확정\s*수혜", "수주 확정 수혜 - 계약=수익 단정 표현 금지", regex=True)
    _check("HIGH", r"계약\s*=\s*매출\s*확정", "계약=매출 확정 단정 표현 금지", regex=True)
    _check("HIGH", r"수주잔고.*반드시\s*상승", "수주잔고→상승 단정 표현 금지", regex=True)
    # 정적 레지스트리 항목을 신규 공시로 오해할 수 있는 표현 금지
    _check("HIGH", r"정적\s*레지스트리.*신규\s*수주", "정적 레지스트리를 신규 수주 공시로 표기 금지", regex=True)
    _check("HIGH", r"신규\s*수주.*정적\s*참고치.*공시", "정적 참고치를 신규 공시로 표기 금지", regex=True)
    # 해지/취소 공시를 호재로 표현하는 경우 금지
    _check("HIGH", r"해지.*호재|취소.*호재|해지.*긍정|취소.*긍정", "해지·취소 공시를 호재로 표현 금지", regex=True)

    # ── 결과 출력 ──────────────────────────────────────────────────────────────
    if not issues:
        console.print("[green]output-lint: 이슈 없음[/green]")
        return

    table = Table(title="output-lint 결과", show_lines=True)
    table.add_column("심각도", style="bold", min_width=6)
    table.add_column("라인", min_width=5)
    table.add_column("메시지", min_width=25)
    table.add_column("발췌", min_width=40)

    _colors = {"HIGH": "red", "MEDIUM": "yellow", "LOW": "cyan"}
    for row in sorted(issues, key=lambda x: (x["severity"], int(x["line"]))):
        color = _colors.get(row["severity"], "white")
        table.add_row(
            f"[{color}]{row['severity']}[/{color}]",
            row["line"], row["message"], row["excerpt"],
        )
    console.print(table)

    high_count = sum(1 for i in issues if i["severity"] == "HIGH")
    console.print(f"총 이슈: {len(issues)}개 (HIGH {high_count}개)")
    if fail_on_high and high_count > 0:
        raise SystemExit(1)


@app.command("universe-audit")
def universe_audit_cmd(
    fail_on_high: Annotated[
        bool,
        typer.Option("--fail-on-high/--no-fail-on-high", help="HIGH 이슈 존재 시 exit(1)"),
    ] = False,
    high_only: Annotated[
        bool, typer.Option("--high-only", help="HIGH 심각도 이슈만 표시"),
    ] = False,
) -> None:
    """Universe / pair-watch / supply-chain 데이터 정합성 감사.

    Example: uv run tele-quant universe-audit
             uv run tele-quant universe-audit --fail-on-high
    """
    from tele_quant.universe_audit import audit_summary, run_universe_audit

    entries = run_universe_audit()
    if high_only:
        entries = [e for e in entries if e.severity == "HIGH"]

    summary = audit_summary(entries)
    high_cnt = summary.get("HIGH", 0)
    med_cnt = summary.get("MEDIUM", 0)
    low_cnt = summary.get("LOW", 0)
    color = "red" if high_cnt else ("yellow" if med_cnt else "green")
    console.print(
        f"\n[{color}]Universe Audit - HIGH:{high_cnt} / MEDIUM:{med_cnt} / LOW:{low_cnt}[/{color}]\n"
    )

    if entries:
        from rich.table import Table as _Table

        tbl = _Table(title=f"Universe Audit ({len(entries)}건)", show_lines=True)
        tbl.add_column("심각도", style="bold", width=8)
        tbl.add_column("check", width=22)
        tbl.add_column("대상", width=24)
        tbl.add_column("상세")
        _SEV_STYLE = {"HIGH": "red", "MEDIUM": "yellow", "LOW": "dim"}
        for e in entries[:80]:
            tbl.add_row(
                f"[{_SEV_STYLE.get(e.severity, '')}]{e.severity}[/]",
                e.check,
                e.target,
                e.detail,
            )
        console.print(tbl)
        if len(entries) > 80:
            console.print(f"  ... 및 {len(entries) - 80}건 더")
    else:
        console.print("[green]이슈 없음[/green]")

    if fail_on_high and high_cnt > 0:
        raise SystemExit(1)


@app.command("alias-audit")
def alias_audit_cmd(
    save: Annotated[
        bool, typer.Option("--save/--no-save", help="결과를 CSV로 저장할지 여부")
    ] = True,
    high_only: Annotated[
        bool, typer.Option("--high-only", help="HIGH 심각도 이슈만 표시"),
    ] = False,
    fail_on_high: Annotated[
        bool,
        typer.Option("--fail-on-high/--no-fail-on-high", help="HIGH 이슈 존재 시 exit(1)"),
    ] = False,
) -> None:
    """전체 alias 오탐 방지 품질 감사 (HIGH/MEDIUM/LOW 이슈 분류).

    Example: uv run tele-quant alias-audit
             uv run tele-quant alias-audit --high-only --fail-on-high
    """
    from pathlib import Path as _Path

    from tele_quant.alias_audit import audit_summary, run_audit, save_audit_csv

    entries = run_audit()

    if high_only:
        entries = [e for e in entries if e.severity == "HIGH"]

    summary = audit_summary(entries)
    console.print(f"\n{summary}\n")

    if entries:
        from rich.table import Table as _Table

        tbl = _Table(title=f"Alias Audit ({len(entries)}건)")
        tbl.add_column("심각도", style="bold")
        tbl.add_column("symbol")
        tbl.add_column("name")
        tbl.add_column("alias")
        tbl.add_column("이슈")

        _SEV_STYLE = {"HIGH": "red", "MEDIUM": "yellow", "LOW": "dim"}
        for e in entries[:50]:  # cap display
            tbl.add_row(
                f"[{_SEV_STYLE.get(e.severity, '')}]{e.severity}[/]",
                e.symbol,
                e.name,
                e.alias,
                e.issue,
            )
        console.print(tbl)
        if len(entries) > 50:
            console.print(f"  ... 및 {len(entries) - 50}건 더 (CSV 확인)")

    if save:
        out = _Path("data/diagnostics/alias_audit_latest.csv")
        save_audit_csv(entries, out)
        console.print(f"[dim]CSV 저장: {out}[/dim]")

    high_cnt = sum(1 for e in entries if e.severity == "HIGH")
    if fail_on_high and high_cnt > 0:
        raise SystemExit(1)


@app.command("inbound-bot")
def inbound_bot_cmd(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="DEBUG 로그 출력"),
) -> None:
    """텔레그램 수신 봇 - 사용자 명령(/분석·/브리핑·/포트·/매크로·/수혜주)에 즉시 응답.

    .env.local 에 TELEGRAM_BOT_TOKEN 이 있어야 합니다.
    TELEGRAM_INBOUND_ALLOWED_IDS 로 허용할 chat_id 를 콤마 구분으로 지정하세요.
    미설정 시 TELEGRAM_BOT_TARGET_CHAT_ID 로 자동 fallback.

    Example:
        uv run tele-quant inbound-bot
        uv run tele-quant inbound-bot --verbose
    """
    import logging as _logging
    from pathlib import Path as _Path

    from tele_quant.db import Store as _Store
    from tele_quant.inbound_bot import run_inbound_bot

    if verbose:
        _logging.getLogger("tele_quant").setLevel(_logging.DEBUG)

    settings = _settings()
    store = _Store(_Path(settings.sqlite_path))

    console.print("[bold cyan]tele-quant 수신 봇 시작[/bold cyan]")
    console.print("종료: Ctrl-C\n")

    try:
        asyncio.run(run_inbound_bot(settings, store))
    except KeyboardInterrupt:
        console.print("\n[dim]봇 종료[/dim]")

