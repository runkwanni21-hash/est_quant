"""OpenDART 한국 공시 수집 모듈.

금융감독원 DART API에서 주요 공시(8-K 상당)를 수집해 RawItem으로 반환한다.
API 키 없으면 조용히 빈 리스트 반환.
"""
from __future__ import annotations

import hashlib
import io
import json
import logging
import time
import xml.etree.ElementTree as ET
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx

from tele_quant.models import RawItem

log = logging.getLogger(__name__)

_BASE = "https://opendart.fss.or.kr/api"

# 주요 공시 타입 코드 → 의미
_REPORT_TYPES = {
    "A001": "공시정정",
    "B001": "정기공시",
    "C001": "주요사항보고",
    "D001": "외부감사관련",
    "E001": "펀드공시",
    "F001": "자산유동화",
    "G001": "거래소공시",
    "H001": "공정위공시",
    "I001": "증권신고(지분증권)",
}

# ── corp_code 조회 (corpCode.xml 일괄 다운로드 기반) ─────────────────────────
# stock_code(6자리) → {"corp_code": ..., "corp_name": ...}
_CORP_CODE_MAP: dict[str, dict[str, str]] = {}
_CORP_CODE_MAP_TS: float = 0.0
_CORP_CODE_CACHE_TTL = 86400.0  # 1일
_CORP_CODE_CACHE_FILE = Path("data/private/dart_corp_codes.json")

# 회사별 반복 조회 방지용 캐시 (stock_code → corp_code)
_corp_code_cache: dict[str, str] = {}


def _ensure_corp_code_map(api_key: str, timeout: float = 30.0) -> None:
    """전체 corpCode 맵을 메모리에 로드. 일 1회 갱신."""
    global _CORP_CODE_MAP, _CORP_CODE_MAP_TS
    now = time.time()
    if _CORP_CODE_MAP and now - _CORP_CODE_MAP_TS < _CORP_CODE_CACHE_TTL:
        return

    # 디스크 캐시 시도
    try:
        if _CORP_CODE_CACHE_FILE.exists():
            mtime = _CORP_CODE_CACHE_FILE.stat().st_mtime
            if now - mtime < _CORP_CODE_CACHE_TTL:
                with open(_CORP_CODE_CACHE_FILE, encoding="utf-8") as f:
                    _CORP_CODE_MAP = json.load(f)
                _CORP_CODE_MAP_TS = now
                log.debug("[opendart] corp_code map loaded from disk (%d entries)", len(_CORP_CODE_MAP))
                return
    except Exception:
        pass

    # DART corpCode.xml 다운로드 (약 3.5MB ZIP)
    try:
        resp = httpx.get(f"{_BASE}/corpCode.xml", params={"crtfc_key": api_key}, timeout=timeout)
        resp.raise_for_status()
        zf = zipfile.ZipFile(io.BytesIO(resp.content))
        xml_bytes = zf.read("CORPCODE.xml")
        tree = ET.fromstring(xml_bytes)
        new_map: dict[str, dict[str, str]] = {}
        for item in tree.findall("list"):
            stock = (item.findtext("stock_code") or "").strip()
            corp = (item.findtext("corp_code") or "").strip()
            name = (item.findtext("corp_name") or "").strip()
            if stock and corp:
                new_map[stock] = {"corp_code": corp, "corp_name": name}
        _CORP_CODE_MAP = new_map
        _CORP_CODE_MAP_TS = now
        log.info("[opendart] corp_code map 갱신 완료 (%d개 종목)", len(new_map))
        # 디스크 저장
        try:
            _CORP_CODE_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(_CORP_CODE_CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(new_map, f, ensure_ascii=False)
        except Exception as exc:
            log.debug("[opendart] corp_code 캐시 저장 실패: %s", exc)
    except Exception as exc:
        log.warning("[opendart] corp_code map 다운로드 실패: %s", exc)


def _lookup_corp_code(stock_code: str, api_key: str, timeout: float) -> str | None:
    """주식 종목코드(6자리)로 DART corpCode 조회 (corpCode.xml 기반)."""
    if stock_code in _corp_code_cache:
        return _corp_code_cache[stock_code]
    if not api_key:
        return None
    _ensure_corp_code_map(api_key, min(timeout, 30.0))
    info = _CORP_CODE_MAP.get(stock_code)
    if info:
        corp_code = info["corp_code"]
        _corp_code_cache[stock_code] = corp_code
        return corp_code
    return None


def fetch_dart_corp_name(stock_code: str, api_key: str) -> str | None:
    """DART에서 한국 법인명 조회 (6자리 KRX 코드 입력)."""
    if not api_key or not stock_code.isdigit() or len(stock_code) != 6:
        return None
    _ensure_corp_code_map(api_key)
    info = _CORP_CODE_MAP.get(stock_code)
    return info["corp_name"] if info else None


def _raw_item_from_dart(item: dict[str, Any], symbol: str) -> RawItem:
    """DART 공시 dict → RawItem."""
    corp_name = item.get("corp_name", symbol)
    report_nm = item.get("report_nm", "공시")
    rcept_dt = item.get("rcept_dt", "")  # YYYYMMDD
    rcept_no = item.get("rcept_no", "")

    try:
        pub_dt = datetime.strptime(rcept_dt, "%Y%m%d").replace(tzinfo=UTC)
    except Exception:
        pub_dt = datetime.now(UTC)

    url = f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcept_no}" if rcept_no else ""

    title = f"[DART] {corp_name} — {report_nm} ({rcept_dt})"
    text = title
    ext_id = hashlib.sha1(f"dart:{rcept_no or title}".encode()).hexdigest()[:16]

    return RawItem(
        source_type="sec_edgar",  # type: ignore[arg-type]  # 기존 타입 재활용
        source_name="OpenDART",
        external_id=ext_id,
        published_at=pub_dt,
        text=text,
        title=title,
        url=url or None,
    )


def fetch_dart_disclosures(
    stock_codes: list[str],
    api_key: str,
    lookback_days: int = 3,
    max_per_symbol: int = 3,
    timeout: float = 10.0,
    rate_limit_per_sec: int = 5,
) -> list[RawItem]:
    """종목코드 리스트의 최근 공시를 수집."""
    if not api_key or not stock_codes:
        return []

    start_dt = (datetime.now(UTC) - timedelta(days=lookback_days)).strftime("%Y%m%d")
    end_dt = datetime.now(UTC).strftime("%Y%m%d")
    results: list[RawItem] = []
    sleep_sec = 1.0 / rate_limit_per_sec

    for code in stock_codes:
        # 6자리 KRX 코드만 처리 (종목코드 .KS/.KQ에서 추출)
        krx = code.replace(".KS", "").replace(".KQ", "")
        if not krx.isdigit() or len(krx) != 6:
            continue

        corp_code = _lookup_corp_code(krx, api_key, timeout)
        if not corp_code:
            time.sleep(sleep_sec)
            continue

        try:
            with httpx.Client(timeout=timeout) as client:
                resp = client.get(
                    f"{_BASE}/list.json",
                    params={
                        "crtfc_key": api_key,
                        "corp_code": corp_code,
                        "bgn_de": start_dt,
                        "end_de": end_dt,
                        "pblntf_ty": "C",  # 주요사항보고
                        "page_count": max_per_symbol,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:
            log.debug("[opendart] 공시 조회 실패 %s: %s", code, exc)
            time.sleep(sleep_sec)
            continue

        if data.get("status") == "000":
            for item in (data.get("list") or [])[:max_per_symbol]:
                results.append(_raw_item_from_dart(item, code))

        time.sleep(sleep_sec)

    log.info("[opendart] 수집 %d건 (종목 %d개)", len(results), len(stock_codes))
    return results


def fetch_dart_dividend(
    symbol: str,
    api_key: str,
    bsns_year: int | None = None,
    timeout: float = 10.0,
) -> float | None:
    """DART 사업보고서에서 현금배당수익률(%) 조회.

    반환: 배당수익률(%) float 또는 None (조회 실패 / 미배당).
    """
    if not api_key:
        return None

    krx = symbol.replace(".KS", "").replace(".KQ", "").replace(".KN", "")
    if not krx.isdigit() or len(krx) != 6:
        return None

    corp_code = _lookup_corp_code(krx, api_key, timeout)
    if not corp_code:
        return None

    import datetime as _dt
    year = bsns_year or (_dt.datetime.now(_dt.UTC).year - 1)

    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.get(
                f"{_BASE}/alotMatter.json",
                params={
                    "crtfc_key": api_key,
                    "corp_code": corp_code,
                    "bsns_year": str(year),
                    "reprt_code": "11014",  # 사업보고서
                },
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:
        log.debug("[opendart] dividend 조회 실패 %s: %s", symbol, exc)
        return None

    if data.get("status") != "000":
        # 이전 연도로 재시도
        try:
            with httpx.Client(timeout=timeout) as client:
                resp = client.get(
                    f"{_BASE}/alotMatter.json",
                    params={
                        "crtfc_key": api_key,
                        "corp_code": corp_code,
                        "bsns_year": str(year - 1),
                        "reprt_code": "11014",
                    },
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception:
            return None

    for row in data.get("list") or []:
        se = (row.get("se") or "").strip()
        if "현금배당수익률" in se or "배당수익률" in se:
            # DART alotMatter.json uses "thstrm" (당기), not "thstrm_amount"
            raw = (row.get("thstrm") or row.get("thstrm_amount") or "").replace(",", "").replace("%", "").strip()
            try:
                val = float(raw)
                if 0 < val < 50:   # 50% 이상은 데이터 오류
                    return val
            except (ValueError, TypeError):
                pass
    return None


def fetch_dart_for_watchlist(settings: Any, watchlist_cfg: Any = None) -> list[RawItem]:
    """watchlist에서 한국 종목 추출 후 DART 공시 수집."""
    api_key = getattr(settings, "opendart_api_key", "") or ""
    if not api_key or not getattr(settings, "opendart_enabled", True):
        return []

    kr_codes: list[str] = []
    if watchlist_cfg is not None:
        try:
            for grp in watchlist_cfg.groups.values():
                for sym in grp.symbols:
                    if sym.endswith((".KS", ".KQ")):
                        kr_codes.append(sym)
        except Exception:
            pass

    if not kr_codes:
        return []

    return fetch_dart_disclosures(
        stock_codes=kr_codes,
        api_key=api_key,
        lookback_days=getattr(settings, "opendart_lookback_days", 3),
        max_per_symbol=getattr(settings, "opendart_max_per_symbol", 3),
        timeout=getattr(settings, "opendart_timeout_seconds", 10.0),
        rate_limit_per_sec=getattr(settings, "opendart_rate_limit_per_sec", 5),
    )
