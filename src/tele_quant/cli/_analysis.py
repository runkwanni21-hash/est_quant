from __future__ import annotations

from typing import Annotated

import typer

from tele_quant.cli._app import app
from tele_quant.cli._common import _settings, console


@app.command("stock-snapshot")
def stock_snapshot_cmd(
    symbol: Annotated[str, typer.Argument(help="종목 코드 (예: NVDA, 005930.KS)")],
    market: Annotated[
        str, typer.Option("--market", help="시장 KR | US (생략 시 자동 판별)")
    ] = "",
    detail: Annotated[
        bool, typer.Option("--detail/--basic", help="섹터 분석·스윙 셋업 포함 (기본 포함)")
    ] = True,
    deep: Annotated[
        bool, typer.Option("--deep/--no-deep", help="DB에서 이슈·수혜주 체인 조회")
    ] = False,
) -> None:
    """단일 종목 즉시 분석 스냅샷.

    Example: uv run tele-quant stock-snapshot NVDA
             uv run tele-quant stock-snapshot 005930.KS --market KR
             uv run tele-quant stock-snapshot 128940.KS --deep
    """
    from pathlib import Path as _Path

    from tele_quant.db import Store as _Store
    from tele_quant.stock_snapshot import build_stock_snapshot, format_stock_snapshot

    settings = _settings()
    store = _Store(_Path(settings.sqlite_path)) if deep else None

    console.print(f"[bold]Stock Snapshot[/bold] {symbol} market={market or 'auto'} deep={deep}")

    snap = build_stock_snapshot(symbol, market, store=store, deep=deep)
    output = format_stock_snapshot(snap)

    console.print(output)

    if not detail:
        return

    if snap.swing_grade and snap.swing_grade != "—":
        console.print(f"\n[dim]스윙 등급: {snap.swing_grade} ({snap.swing_score:.0f}점)[/dim]")

    forbidden = [
        "매수 권장", "매도 권장", "확정 수익", "수익 보장",
        "세력 매집 확정", "기관 매집 확정", "수혜 확정", "피해 확정",
        "자동매매", "실계좌 주문", "반드시 상승",
    ]
    found = [w for w in forbidden if w in output]
    if found:
        console.print(f"[red]⚠ 금지 표현 감지: {found}[/red]")
    else:
        console.print("[dim]✓ 금지 표현 없음[/dim]")


@app.command("earnings-snapshot")
def earnings_snapshot_cmd(
    symbol: Annotated[str, typer.Argument(help="종목 코드 (예: NVDA, 005930.KS)")],
    market: Annotated[
        str, typer.Option("--market", help="시장 KR | US (생략 시 자동 판별)")
    ] = "",
) -> None:
    """실적 스냅샷 — EPS·매출·가이던스·다음 실적 발표일.

    Example: uv run tele-quant earnings-snapshot NVDA
             uv run tele-quant earnings-snapshot 005930.KS --market KR
    """
    from tele_quant.earnings_snapshot import fetch_earnings_snapshot, format_earnings_snapshot

    if not market:
        market = "KR" if symbol.endswith(".KS") or symbol.endswith(".KQ") else "US"

    console.print(f"[bold]Earnings Snapshot[/bold] {symbol} market={market}")
    snap = fetch_earnings_snapshot(symbol, market)
    console.print(format_earnings_snapshot(snap))
    console.print("\n⚠ 공개 정보 기반 리서치 보조. 투자 판단 책임은 사용자에게 있음.")


@app.command("clinical-pipeline")
def clinical_pipeline_cmd(
    symbol: Annotated[str, typer.Argument(help="종목 코드 (예: 128940.KS, MRNA)")],
    name: Annotated[str, typer.Option("--name", help="회사명 (ClinicalTrials.gov 검색어)")] = "",
    market: Annotated[
        str, typer.Option("--market", help="시장 KR | US (생략 시 자동 판별)")
    ] = "",
) -> None:
    """바이오/제약 임상 파이프라인 조회 (ClinicalTrials.gov 공개 API).

    Example: uv run tele-quant clinical-pipeline 128940.KS --name 한미약품
             uv run tele-quant clinical-pipeline MRNA
    """
    from tele_quant.clinical_pipeline import fetch_clinical_pipeline, format_clinical_pipeline

    if not market:
        market = "KR" if symbol.endswith(".KS") or symbol.endswith(".KQ") else "US"

    console.print(f"[bold]Clinical Pipeline[/bold] {symbol} name={name or '(symbol)'} market={market}")
    result = fetch_clinical_pipeline(symbol, name=name, market=market)
    console.print(format_clinical_pipeline(result))
    console.print("\n⚠ 공개 정보 기반 리서치 보조. 투자 판단 책임은 사용자에게 있음.")


@app.command("sector-intel")
def sector_intel_cmd(
    symbol: Annotated[str, typer.Argument(help="종목 코드")],
    sector_id: Annotated[
        str, typer.Option("--sector", help="섹터 ID (생략 시 자동 감지)")
    ] = "",
    name: Annotated[str, typer.Option("--name", help="종목명")] = "",
    market: Annotated[
        str, typer.Option("--market", help="시장 KR | US")
    ] = "",
    deep: Annotated[
        bool, typer.Option("--deep/--no-deep", help="DB에서 이슈·특수 모듈 조회")
    ] = False,
) -> None:
    """섹터별 심층 인텔리전스 — 촉매·리스크·스윙·EXIT 체크포인트.

    Example: uv run tele-quant sector-intel NVDA --sector ai_semiconductor_hbm_foundry
             uv run tele-quant sector-intel 128940.KS --name 한미약품 --market KR --deep
    """
    from pathlib import Path as _Path

    from tele_quant.db import Store as _Store
    from tele_quant.sector_intelligence import build_sector_intelligence, format_sector_intelligence
    from tele_quant.sector_macro import detect_seed_sector, guess_sector_id

    if not market:
        market = "KR" if symbol.endswith(".KS") or symbol.endswith(".KQ") else "US"

    settings = _settings()
    store = _Store(_Path(settings.sqlite_path)) if deep else None

    _sid = sector_id
    if not _sid:
        if store is not None:
            try:
                _sid = detect_seed_sector(symbol, store) or ""
            except Exception:
                _sid = ""
        if not _sid:
            try:
                import yfinance as _yf
                _info = _yf.Ticker(symbol).info
                _sector_str = _info.get("sector") or _info.get("industry") or ""
                _sid = guess_sector_id(_sector_str) or ""
            except Exception:
                _sid = ""

    console.print(f"[bold]Sector Intel[/bold] {symbol} sector={_sid or '(none)'} deep={deep}")

    if not _sid:
        console.print("[yellow]섹터 ID를 감지할 수 없음. --sector 옵션으로 직접 지정하세요.[/yellow]")
        return

    intel = build_sector_intelligence(
        symbol=symbol,
        name=name,
        market=market,
        sector_id=_sid,
        store=store,
        deep=deep,
    )
    if intel is None:
        console.print(f"[yellow]섹터 '{_sid}' 플레이북 없음.[/yellow]")
        return

    console.print(format_sector_intelligence(intel))
    console.print("\n⚠ 공개 정보 기반 리서치 보조. 투자 판단 책임은 사용자에게 있음.")


@app.command("report")
def report_cmd(
    symbol: Annotated[str, typer.Argument(help="종목 코드 (예: NVDA, 005930.KS)")],
    market: Annotated[
        str, typer.Option("--market", help="시장 KR | US (생략 시 자동 판별)")
    ] = "",
    deep: Annotated[
        bool, typer.Option("--deep/--no-deep", help="DART/SEC 공시 포함 심층 모드")
    ] = False,
) -> None:
    """기관식 스윙 리포트 (1D~1M 보유 관점).

    Example: uv run tele-quant report NVDA --deep
             uv run tele-quant report 005930.KS --market KR
    """
    from pathlib import Path as _Path

    from tele_quant.analysis.report_builder import build_institutional_report
    from tele_quant.analysis.report_formatter import _check_forbidden, format_institutional_report
    from tele_quant.db import Store as _Store

    if not market:
        market = "KR" if symbol.endswith(".KS") or symbol.endswith(".KQ") else "US"

    settings = _settings()
    store = _Store(_Path(settings.sqlite_path))

    console.print(f"[bold]Institutional Report[/bold] {symbol} market={market} deep={deep}")
    rpt = build_institutional_report(symbol, market, store, settings, deep=deep)
    chunks = format_institutional_report(rpt)
    for chunk in chunks:
        console.print(chunk)

    found = _check_forbidden("\n".join(chunks))
    if found:
        console.print(f"[red]⚠ 금지 표현 감지: {found}[/red]")
    else:
        console.print("[dim]✓ 금지 표현 없음[/dim]")

    if rpt.error:
        console.print(f"[yellow]부분 오류: {rpt.error}[/yellow]")


@app.command("chain")
def chain_cmd(
    symbol: Annotated[str, typer.Argument(help="종목 코드 (예: NVDA, 005930.KS)")],
    market: Annotated[
        str, typer.Option("--market", help="시장 KR | US (생략 시 자동 판별)")
    ] = "",
) -> None:
    """관계 체인 후보 — 수혜 가능성 / 상대적 부담 / 피어.

    Example: uv run tele-quant chain NVDA
             uv run tele-quant chain 005930.KS --market KR
    """
    from pathlib import Path as _Path

    from tele_quant.analysis.chain_recommendation_engine import build_chain_candidates
    from tele_quant.analysis.report_formatter import format_chain_candidates
    from tele_quant.db import Store as _Store
    from tele_quant.relation_feed import _NAME_MAP

    if not market:
        market = "KR" if symbol.endswith(".KS") or symbol.endswith(".KQ") else "US"

    settings = _settings()
    store = _Store(_Path(settings.sqlite_path))
    name = _NAME_MAP.get(symbol, symbol)

    console.print(f"[bold]Chain Analysis[/bold] {symbol} ({name}) market={market}")
    bens, burdens, peers = build_chain_candidates(symbol, market, store, max_per_type=3)
    output = format_chain_candidates(symbol, name, bens, burdens, peers)
    console.print(output)


@app.command("institutional-flow")
def institutional_flow_cmd(
    symbol: Annotated[str, typer.Argument(help="종목 코드 (예: 005930.KS, NVDA)")],
    market: Annotated[
        str, typer.Option("--market", help="시장 KR | US (생략 시 자동 판별)")
    ] = "",
) -> None:
    """기관/외국인 수급집중 가능성 분석.

    Example: uv run tele-quant institutional-flow 005930.KS
             uv run tele-quant institutional-flow NVDA
    """
    from tele_quant.analysis.institutional_flow import compute_institutional_flow
    from tele_quant.analysis.report_formatter import format_institutional_flow
    from tele_quant.analysis.technical_signal_engine import compute_technical_accumulation_signal
    from tele_quant.relation_feed import _NAME_MAP

    if not market:
        market = "KR" if symbol.endswith(".KS") or symbol.endswith(".KQ") else "US"

    name = _NAME_MAP.get(symbol, symbol)
    console.print(f"[bold]Institutional Flow[/bold] {symbol} ({name}) market={market}")

    tech = compute_technical_accumulation_signal(symbol)
    flow = compute_institutional_flow(
        symbol,
        rsi=tech.rsi_1d,
        ret_20d=tech.ret_20d,
        vol_ratio=tech.vol_ratio_20d,
        bb_pct=tech.bb_pct,
    )
    output = format_institutional_flow(symbol, name, flow, tech)
    console.print(output)


@app.command("calendar-policy")
def calendar_policy_cmd(
    now_iso: Annotated[
        str, typer.Option("--now", help="현재 시각 ISO 문자열 (기본: 시스템 KST 현재)")
    ] = "",
) -> None:
    """현재 캘린더 정책 확인 — 월요일 LONG 엄격 / 금요일 EXIT 점검.

    Example: uv run tele-quant calendar-policy
             uv run tele-quant calendar-policy --now 2026-05-19T09:00:00+09:00
    """
    from datetime import datetime, timedelta, timezone

    from tele_quant.calendar_score_policy import (
        format_policy_note,
        get_current_policy,
    )

    _KST = timezone(timedelta(hours=9))
    if now_iso:
        now = datetime.fromisoformat(now_iso)
        if now.tzinfo is None:
            now = now.replace(tzinfo=_KST)
    else:
        now = datetime.now(_KST)

    adj = get_current_policy(now=now)
    note = format_policy_note(now=now)

    console.print(f"[bold]Calendar Policy[/bold] — {now.strftime('%Y-%m-%d %H:%M %Z')}")
    console.print(f"모드: [bold]{adj.mode.value}[/bold]  활성: {adj.active}")
    if adj.active:
        console.print(f"LONG 패널티: {adj.long_penalty:+.1f}점  EXIT 부스트: {adj.exit_boost:+.1f}점")
        if adj.min_score_for_action:
            console.print(f"최소 행동 점수: {adj.min_score_for_action:.0f}점")
        if adj.require_direct_evidence:
            console.print("직접 증거 필수: YES")
    if note:
        console.print(f"\n정책 노트:\n{note}")
    else:
        console.print("[dim]정책 노트 없음 (일반 모드)[/dim]")


@app.command("build-universe")
def build_universe_cmd(
    market: Annotated[
        str, typer.Option("--market", "-m", help="KR / US / ALL (기본: ALL)")
    ] = "ALL",
    include_etf: Annotated[
        bool, typer.Option("--include-etf", help="ETF 포함 여부")
    ] = False,
) -> None:
    """KR/US 5000+ 종목 메타데이터를 DB에 저장.

    Example: uv run tele-quant build-universe
             uv run tele-quant build-universe --market KR
             uv run tele-quant build-universe --market US --include-etf
    """
    from pathlib import Path as _Path

    from tele_quant.cli._common import _settings
    from tele_quant.db import Store as _Store
    from tele_quant.ticker_universe import build_universe

    settings = _settings()
    store = _Store(_Path(settings.sqlite_path))
    console.print(f"[bold]Universe 빌드[/bold] — market={market} ETF포함={include_etf}")
    console.print("[dim]KR: pykrx (KOSPI+KOSDAQ+KONEX) | US: NASDAQ Trader (NASDAQ+NYSE)[/dim]\n")

    counts = build_universe(market=market, store=store, include_etf=include_etf)
    console.print(f"[green]완료:[/green] KR={counts.get('KR', 0):,}  US={counts.get('US', 0):,}  총={counts.get('total', 0):,}종목 DB 저장")


@app.command("bulk-refresh")
def bulk_refresh_cmd(
    market: Annotated[
        str, typer.Option("--market", "-m", help="KR / US / ALL (기본: ALL)")
    ] = "ALL",
    limit: Annotated[
        int, typer.Option("--limit", "-n", help="갱신 종목 수 (기본: 500)")
    ] = 500,
) -> None:
    """universe 상위 N종목 섹터·시총 자동 갱신.

    Example: uv run tele-quant bulk-refresh
             uv run tele-quant bulk-refresh --market US --limit 200
    """
    from pathlib import Path as _Path

    from tele_quant.bulk_refresher import run_bulk_refresh
    from tele_quant.cli._common import _settings
    from tele_quant.db import Store as _Store

    settings = _settings()
    store = _Store(_Path(settings.sqlite_path))
    finnhub_key = getattr(settings, "finnhub_api_key", "") or ""

    console.print(f"[bold]Bulk Refresh[/bold] — market={market} limit={limit}")
    result = run_bulk_refresh(store, market=market, limit=limit, finnhub_api_key=finnhub_key)
    console.print(f"[green]완료:[/green] updated={result['updated']:,}  failed={result['failed']:,}")
