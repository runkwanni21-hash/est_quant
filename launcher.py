#!/usr/bin/env python3
"""Tele Quant Dashboard 실행기.

사용법:
  uv run python launcher.py               # 기본 (8765 포트)
  uv run python launcher.py --port 9000   # 포트 지정
  uv run python launcher.py --no-browser  # 브라우저 자동 실행 안 함
"""

from __future__ import annotations

import argparse
import contextlib
import importlib.util
import platform
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

# Windows 콘솔 UTF-8 강제 설정 (이모지 등 비-ASCII 문자 인코딩 오류 방지)
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    with contextlib.suppress(Exception):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    with contextlib.suppress(Exception):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

PROJECT_DIR = Path(__file__).resolve().parent
DEFAULT_PORT = 8765


# ── 유틸 ─────────────────────────────────────────────────────────────────────

def _is_port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) != 0


def _wait_for_server(port: int, timeout: float = 20.0) -> bool:
    """서버가 올라올 때까지 대기. 성공하면 True."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            if s.connect_ex(("127.0.0.1", port)) == 0:
                return True
        time.sleep(0.4)
    return False


def _open_browser(url: str, delay: float = 0.5) -> None:
    """별도 스레드에서 서버 준비 후 브라우저 열기."""
    def _run() -> None:
        time.sleep(delay)
        # WSL에서 Windows 기본 브라우저 열기 시도
        if platform.system() == "Linux" and Path("/proc/version").exists():
            try:
                with open("/proc/version") as f:
                    if "microsoft" in f.read().lower():
                        subprocess.Popen(
                            ["explorer.exe", url],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                        )
                        return
            except Exception:
                pass
        webbrowser.open(url)

    t = threading.Thread(target=_run, daemon=True)
    t.start()


def _check_deps() -> bool:
    """fastapi / uvicorn 설치 여부 확인."""
    missing = [
        pkg for pkg in ("fastapi", "uvicorn")
        if importlib.util.find_spec(pkg) is None
    ]
    if missing:
        print(f"[오류] 필요한 패키지가 없습니다: {', '.join(missing)}")
        print("  설치 명령: uv add fastapi 'uvicorn[standard]'")
        return False
    return True


# ── 메인 ─────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Tele Quant Dashboard 실행기",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="포트 번호 (기본 8765)")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="바인딩 주소")
    parser.add_argument("--no-browser", action="store_true", help="브라우저 자동 실행 안 함")
    args = parser.parse_args()

    # .env.local 로드 (프로젝트 루트 기준)
    env_file = PROJECT_DIR / ".env.local"
    if env_file.exists():
        try:
            from dotenv import load_dotenv
            load_dotenv(env_file, override=False)
        except ImportError:
            pass

    # sys.path에 src 추가 (패키지 설치 없이 실행 가능하도록)
    src = PROJECT_DIR / "src"
    if src.exists() and str(src) not in sys.path:
        sys.path.insert(0, str(src))

    print()
    print("  ============================================")
    print("   [Tele Quant Dashboard]")
    print("  ============================================")

    if not _check_deps():
        input("\n  [Enter] 키를 누르면 종료됩니다...")
        sys.exit(1)

    port = args.port
    if not _is_port_free(port):
        # 포트 충돌 시 빈 포트 자동 탐색
        for p in range(port + 1, port + 20):
            if _is_port_free(p):
                print(f"  [경고] {port} 포트 사용 중 → {p} 포트로 변경")
                port = p
                break
        else:
            print(f"  [오류] {port}~{port+19} 포트 모두 사용 중입니다.")
            input("\n  [Enter] 키를 누르면 종료됩니다...")
            sys.exit(1)

    url = f"http://{args.host}:{port}"
    print(f"   브라우저 주소: {url}")
    print("   종료: Ctrl+C")
    print("  ============================================")
    print()

    # 서버가 뜨면 브라우저 열기
    if not args.no_browser:
        def _browser_opener() -> None:
            if _wait_for_server(port, timeout=25.0):
                _open_browser(url)
        threading.Thread(target=_browser_opener, daemon=True).start()

    # 대시보드 앱 시작
    try:
        import uvicorn

        from tele_quant.dashboard.app import create_app
        app = create_app()
        uvicorn.run(app, host=args.host, port=port, log_level="warning")
    except KeyboardInterrupt:
        print("\n  서버를 종료합니다.")
    except Exception as exc:
        import traceback
        print(f"\n  [오류] {exc}")
        print("\n  상세 오류:")
        traceback.print_exc()
        input("\n  [Enter] 키를 누르면 종료됩니다...")
        sys.exit(1)


if __name__ == "__main__":
    main()
