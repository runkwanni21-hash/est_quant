from __future__ import annotations

from typing import Annotated

import typer

from tele_quant.cli._app import app
from tele_quant.cli._common import _settings, console


@app.command("theme-board")
def theme_board_cmd(
    market: Annotated[
        str, typer.Option("--market", help="KR 또는 US")
    ] = "KR",
    no_send: Annotated[
        bool, typer.Option("--no-send/--send", help="전송 없이 출력만")
    ] = True,
) -> None:
    """퀀터멘탈 테마 보드 — 급등/급락/수혜/피해/주도주/후발/과열 분류.

    Example: uv run tele-quant theme-board --market KR --no-send
             uv run tele-quant theme-board --market US --no-send
    """
    from tele_quant.db import Store
    from tele_quant.theme_board import build_theme_board

    settings = _settings()
    store = Store(settings.sqlite_path)
    report = build_theme_board(market.upper(), store, settings)
    console.print(report)

    if not no_send:
        import asyncio

        from tele_quant.telegram_client import TelegramGateway
        from tele_quant.telegram_sender import TelegramSender

        async def _send() -> None:
            async with TelegramGateway(settings) as gateway:
                sender = TelegramSender(settings, gateway=gateway)
                await sender.send(report)

        asyncio.run(_send())
        console.print("[green]theme-board 전송 완료[/green]")


@app.command("sector-cycle")
def sector_cycle_cmd(
    market: Annotated[
        str, typer.Option("--market", help="KR 또는 US")
    ] = "KR",
    no_send: Annotated[
        bool, typer.Option("--no-send/--send", help="전송 없이 출력만")
    ] = True,
) -> None:
    """Sector Cycle Rulebook v2 — 시장 자금 흐름 사이클 분석.

    Example: uv run tele-quant sector-cycle --market KR --no-send
             uv run tele-quant sector-cycle --market US --no-send
    """
    from tele_quant.db import Store
    from tele_quant.sector_cycle import build_sector_cycle_section

    settings = _settings()
    store = Store(settings.sqlite_path)
    report = build_sector_cycle_section(market.upper(), store, settings)
    console.print(report)

    if not no_send:
        import asyncio

        from tele_quant.telegram_client import TelegramGateway
        from tele_quant.telegram_sender import TelegramSender

        async def _send() -> None:
            async with TelegramGateway(settings) as gateway:
                sender = TelegramSender(settings, gateway=gateway)
                await sender.send(report)

        asyncio.run(_send())
        console.print("[green]sector-cycle 전송 완료[/green]")


@app.command("sector-cycle-audit")
def sector_cycle_audit_cmd(
    fail_on_high: Annotated[
        bool, typer.Option("--fail-on-high", help="HIGH 심각도 이슈 발견 시 exit-code 1")
    ] = False,
) -> None:
    """sector_cycle_rules.yml 심볼/이름 유효성 감사.

    Example: uv run tele-quant sector-cycle-audit
             uv run tele-quant sector-cycle-audit --fail-on-high
    """
    import csv
    import re
    from pathlib import Path as _Path

    from rich.table import Table

    from tele_quant.sector_cycle import load_sector_cycle_rules

    rules = load_sector_cycle_rules()

    # Build flat list: (cycle_id, stage, symbol, name)
    # source_symbols: [{symbol, name}, ...]
    # beneficiaries/victims: [{sector, connection, symbols: [{symbol, name}]}, ...]
    _flat_keys = [("source_symbols", "SOURCE")]
    _nested_keys = [
        ("first_order_beneficiaries", "FIRST"),
        ("second_order_beneficiaries", "SECOND"),
        ("third_order_beneficiaries", "THIRD"),
        ("victims", "VICTIM"),
    ]
    entries: list[tuple[str, str, str, str]] = []
    for rule in rules:
        cid = rule.get("cycle_id", "")
        for key, stage in _flat_keys:
            for item in rule.get(key, []):
                entries.append((cid, stage, item.get("symbol", ""), item.get("name", "")))
        for key, stage in _nested_keys:
            for sector_group in rule.get(key, []):
                for item in sector_group.get("symbols", []):
                    entries.append((cid, stage, item.get("symbol", ""), item.get("name", "")))

    # Validation passes
    issues: list[dict[str, str]] = []
    _kr_pattern = re.compile(r"^\d{6}\.(KS|KQ)$")
    _us_pattern = re.compile(r"^[A-Z]{1,5}$")

    # Track (symbol, name) mapping for duplicate-name-mismatch detection
    sym_names: dict[str, set[str]] = {}
    for _cid, _stage, sym, name in entries:
        if sym:
            sym_names.setdefault(sym, set()).add(name)

    for cid, stage, sym, name in entries:
        if not sym:
            issues.append({"severity": "HIGH", "cycle_id": cid, "stage": stage,
                           "symbol": sym, "name": name, "issue": "symbol 비어있음"})
            continue
        if not name:
            issues.append({"severity": "MEDIUM", "cycle_id": cid, "stage": stage,
                           "symbol": sym, "name": name, "issue": "name 비어있음"})

        is_kr = sym.endswith((".KS", ".KQ"))
        is_us = _us_pattern.match(sym) is not None
        if not is_kr and not is_us:
            issues.append({"severity": "HIGH", "cycle_id": cid, "stage": stage,
                           "symbol": sym, "name": name, "issue": "심볼 형식 오류 (KR: 6자리.KS/.KQ, US: 대문자)"})
        elif is_kr and not _kr_pattern.match(sym):
            issues.append({"severity": "HIGH", "cycle_id": cid, "stage": stage,
                           "symbol": sym, "name": name, "issue": "KR 심볼 6자리 아님"})

        names_for_sym = sym_names.get(sym, set())
        if len(names_for_sym) > 1:
            issues.append({"severity": "MEDIUM", "cycle_id": cid, "stage": stage,
                           "symbol": sym, "name": name,
                           "issue": f"같은 심볼에 다른 이름: {', '.join(sorted(names_for_sym))}"})

    # Display
    if not issues:
        console.print("[green]sector-cycle-audit: 이슈 없음[/green]")
        return

    table = Table(title="sector-cycle-audit 결과", show_lines=True)
    table.add_column("심각도", style="bold", min_width=6)
    table.add_column("cycle_id", min_width=20)
    table.add_column("stage", min_width=8)
    table.add_column("symbol", min_width=14)
    table.add_column("name", min_width=16)
    table.add_column("이슈", min_width=30)

    _colors = {"HIGH": "red", "MEDIUM": "yellow", "LOW": "cyan"}
    for row in sorted(issues, key=lambda x: (x["severity"], x["cycle_id"])):
        color = _colors.get(row["severity"], "white")
        table.add_row(
            f"[{color}]{row['severity']}[/{color}]",
            row["cycle_id"], row["stage"], row["symbol"], row["name"], row["issue"],
        )
    console.print(table)

    # CSV output
    out_dir = _Path("data/diagnostics")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "sector_cycle_audit_latest.csv"
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["severity", "cycle_id", "stage", "symbol", "name", "issue"])
        writer.writeheader()
        writer.writerows(issues)
    console.print(f"[dim]CSV 저장: {out_path}[/dim]")

    high_count = sum(1 for i in issues if i["severity"] == "HIGH")
    console.print(f"총 이슈: {len(issues)}개 (HIGH {high_count}개)")
    if fail_on_high and high_count > 0:
        raise SystemExit(1)
