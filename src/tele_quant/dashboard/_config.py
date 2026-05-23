"""대시보드 설정 관리 — .env.local 읽기/쓰기."""

from __future__ import annotations

from pathlib import Path
from typing import Any

_ENV_FILE = Path(".env.local")
_TEMPLATE_FILE = Path("env.example")

# 브라우저에 절대 노출하지 않는 키 (값 마스킹)
_MASKED = {
    "telegram_bot_token", "telegram_api_hash", "telegram_inbound_bot_token",
    "opendart_api_key", "finnhub_api_key", "fred_api_key", "ecos_api_key",
    "naver_client_secret", "alphavantage_api_key", "newsapi_key",
    "fmp_api_key", "polygon_api_key", "tiingo_api_key", "twelvedata_api_key",
    "kis_app_key", "kis_app_secret", "dart_api_key", "ncbi_api_key",
    "guardian_api_key", "newsdata_api_key", "marketaux_api_token",
    "nyc_api_key", "eia_api_key", "bea_api_key", "bls_api_key",
    "census_api_key", "data_go_kr_service_key", "samgov_api_key",
    "openfda_api_key", "krx_openapi_auth_key",
}


def _parse_env(path: Path) -> dict[str, str]:
    """key=value 형태로 파싱 (주석·빈 줄 무시)."""
    result: dict[str, str] = {}
    if not path.exists():
        return result
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, _, val = line.partition("=")
            result[key.strip()] = val.strip()
    return result


def read_config(mask_secrets: bool = True) -> dict[str, Any]:
    """현재 .env.local 값을 반환. 민감 키는 마스킹."""
    raw = _parse_env(_ENV_FILE)
    result: dict[str, Any] = {}
    for k, v in raw.items():
        key_lower = k.lower()
        if mask_secrets and key_lower in _MASKED and v:
            result[k] = "●●●●●●●●"
        else:
            result[k] = v
    return result


def update_config(updates: dict[str, str]) -> None:
    """지정된 키만 .env.local 에 업데이트 (없으면 파일 끝에 추가)."""
    path = _ENV_FILE
    if path.exists():
        content = path.read_text(encoding="utf-8")
    elif _TEMPLATE_FILE.exists():
        content = _TEMPLATE_FILE.read_text(encoding="utf-8")
    else:
        content = ""

    lines = content.splitlines(keepends=True)
    remaining = dict(updates)

    new_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#") or not stripped:
            new_lines.append(line)
            continue
        if "=" in stripped:
            key = stripped.split("=", 1)[0].strip()
            if key in remaining:
                eol = "\r\n" if line.endswith("\r\n") else "\n"
                new_lines.append(f"{key}={remaining.pop(key)}{eol}")
                continue
        new_lines.append(line)

    # 파일에 없던 키 추가
    if remaining:
        if new_lines and not new_lines[-1].endswith("\n"):
            new_lines.append("\n")
        new_lines.append("\n# [대시보드에서 추가]\n")
        for k, v in remaining.items():
            new_lines.append(f"{k}={v}\n")

    path.write_text("".join(new_lines), encoding="utf-8")


def get_bool(key: str, default: bool = False) -> bool:
    raw = _parse_env(_ENV_FILE)
    return raw.get(key, str(default)).lower() in ("true", "1", "yes")


def get_str(key: str, default: str = "") -> str:
    return _parse_env(_ENV_FILE).get(key, default)


async def test_telegram(bot_token: str, chat_id: str) -> dict[str, Any]:
    """텔레그램 봇 테스트 발송."""
    try:
        import httpx
        msg = "✅ Tele Quant 대시보드 연결 테스트 성공!"
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        async with httpx.AsyncClient(timeout=8) as client:
            r = await client.post(url, json={"chat_id": chat_id, "text": msg})
        if r.status_code == 200:
            return {"ok": True, "message": "테스트 메시지 전송 성공"}
        return {"ok": False, "message": r.json().get("description", r.text)}
    except Exception as exc:
        return {"ok": False, "message": str(exc)}


async def test_ollama(host: str, model: str) -> dict[str, Any]:
    """Ollama 연결 테스트."""
    try:
        import httpx
        url = host.rstrip("/") + "/api/tags"
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(url)
        if r.status_code == 200:
            models = [m.get("name", "") for m in r.json().get("models", [])]
            has_model = any(m.startswith(model.split(":")[0]) for m in models)
            return {
                "ok": True,
                "models": models,
                "has_target": has_model,
                "message": f"연결 성공 (모델 {len(models)}개)",
            }
        return {"ok": False, "message": f"HTTP {r.status_code}"}
    except Exception as exc:
        return {"ok": False, "message": f"연결 실패: {exc}"}
