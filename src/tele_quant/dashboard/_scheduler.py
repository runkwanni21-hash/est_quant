"""4H 브리핑 백그라운드 스케줄러."""

from __future__ import annotations

import logging
import threading
from datetime import UTC, datetime, timedelta
from typing import Any

log = logging.getLogger(__name__)

_lock = threading.Lock()
_thread: threading.Thread | None = None
_stop_event = threading.Event()

_state: dict[str, Any] = {
    "running": False,
    "market": "KR",
    "interval_h": 4,
    "last_run": None,
    "next_run": None,
    "last_result": None,
    "run_count": 0,
}


def get_status() -> dict[str, Any]:
    with _lock:
        return dict(_state)


def start(market: str = "KR", interval_h: int = 4) -> dict[str, Any]:
    """스케줄러 시작."""
    with _lock:
        if _state["running"]:
            return {"ok": False, "message": "이미 실행 중입니다."}
        _state["market"] = market.upper()
        _state["interval_h"] = max(1, interval_h)
        _state["running"] = True
        _state["next_run"] = (datetime.now(UTC) + timedelta(seconds=10)).isoformat()
        _stop_event.clear()

    t = threading.Thread(target=_loop, daemon=True, name="4h-scheduler")
    with _lock:
        global _thread
        _thread = t
    t.start()
    log.info("[scheduler] 시작 market=%s interval=%dh", market, interval_h)
    return {"ok": True, "message": f"{market} 4H 스케줄러 시작"}


def stop() -> dict[str, Any]:
    """스케줄러 중지."""
    with _lock:
        if not _state["running"]:
            return {"ok": False, "message": "실행 중이 아닙니다."}
        _state["running"] = False
    _stop_event.set()
    log.info("[scheduler] 중지 요청")
    return {"ok": True, "message": "스케줄러 중지됨"}


def run_now() -> dict[str, Any]:
    """즉시 한 번 실행 (스케줄과 무관)."""
    t = threading.Thread(target=_run_briefing, daemon=True, name="4h-immediate")
    t.start()
    return {"ok": True, "message": "즉시 실행 시작됨"}


# ── 내부 ─────────────────────────────────────────────────────────────────────

def _loop() -> None:
    interval_sec = _state["interval_h"] * 3600
    # 첫 실행: 10초 대기
    _stop_event.wait(10)
    while not _stop_event.is_set():
        _run_briefing()
        with _lock:
            if not _state["running"]:
                break
            _state["next_run"] = (
                datetime.now(UTC) + timedelta(seconds=interval_sec)
            ).isoformat()
        _stop_event.wait(interval_sec)

    with _lock:
        _state["running"] = False
        _state["next_run"] = None


def _run_briefing() -> None:
    from pathlib import Path as _P

    from tele_quant.db import Store
    from tele_quant.settings import Settings

    market = _state.get("market", "KR")
    started_at = datetime.now(UTC)
    try:
        cfg = Settings()
        store = Store(_P(cfg.sqlite_path))
        use_advisory = getattr(cfg, "advisory_only_mode", True)
        if use_advisory:
            from tele_quant.advisor_4h import run_4h_advisory
            report = run_4h_advisory(market, store, cfg, top_n=5)
        else:
            from tele_quant.briefing import run_4h_briefing
            report = run_4h_briefing(market, store, cfg, top_n=5)

        # 텔레그램 발송 (봇 토큰 있을 때만)
        if report and cfg.telegram_bot_token:
            import asyncio

            from tele_quant.telegram_sender import TelegramSender
            sender = TelegramSender(cfg)
            asyncio.run(sender.send(report))

        result = "success"
        preview = (report or "")[:200]
    except Exception as exc:
        log.warning("[scheduler] briefing failed: %s", exc)
        result = f"error: {exc}"
        preview = ""

    with _lock:
        _state["last_run"] = started_at.isoformat()
        _state["last_result"] = result
        _state["run_count"] = _state.get("run_count", 0) + 1
        if "preview" not in _state:
            _state["preview"] = ""
        _state["preview"] = preview
