# RUNBOOK_WINDOWS.md - Windows 운영 가이드

> Windows에서 est_quant(tele_quant)를 실행하고, 필요하면 WSL systemd 또는 Windows Task Scheduler로 자동 운영하는 방법입니다.

---

## 1. 일반 Windows 실행

일반 사용자는 `실행.bat`만 사용합니다. `run_dashboard.bat`는 WSL용 보조 스크립트이므로 초보자용 진입점으로 쓰지 않습니다.

### 1-1. 첫 실행

1. GitHub에서 `runkwanni21-hash/est_quant`를 `clone`하거나 ZIP으로 내려받습니다.
2. 저장소 폴더에서 `실행.bat`을 더블클릭합니다.
3. 첫 실행이면 `data/private/`, `logs/`, `.env.local`이 자동 생성됩니다.
4. 메모장이 열리면 필요한 환경변수만 입력하고 저장합니다.
5. 창 안내대로 종료한 뒤 `실행.bat`을 다시 더블클릭합니다.

`실행.bat`은 Python 3.11+, uv, 패키지 설치를 확인하고 `launcher.py`를 실행합니다. 브라우저 주소는 `launcher.py`가 실제 열린 포트 기준으로 표시하고 엽니다.

### 1-2. 환경변수

`.env.local`은 `env.example`에서 만들어집니다. `env.example`이 없으면 호환용 `env.template`을 사용합니다.

대시보드와 기본 분석은 Telegram 키 없이도 실행할 수 있습니다.

```env
# 텔레그램 발송을 쓸 때만 입력
TELEGRAM_BOT_TOKEN=
TELEGRAM_BOT_TARGET_CHAT_ID=

# 텔레그램 채널 수집을 쓸 때만 입력
TELEGRAM_API_ID=
TELEGRAM_API_HASH=
TELEGRAM_PHONE=

# 한국 전자공시 OpenDART
# DART_API_KEY가 아니라 OPENDART_API_KEY를 사용합니다.
OPENDART_ENABLED=false
OPENDART_API_KEY=

# 로컬 private 데이터
SQLITE_PATH=./data/private/tele_quant.sqlite
TELEGRAM_SESSION_PATH=./data/private/tele_quant.session
EVENT_PRICE_CSV_PATH=./data/private/event_price_1000d.csv
CORRELATION_CSV_PATH=./data/private/stock_correlation_1000d.csv

# 보안 잠금
ORDER_ENABLED=false
REAL_TRADING_ENABLED=false
KIS_ORDER_ENABLED=false
KIS_REAL_ORDER_ENABLED=false
```

### 1-3. 포트 충돌

기본 포트는 `8765`입니다. 이미 사용 중이면 `launcher.py`가 `8766`, `8767`처럼 빈 포트를 찾아 실제 주소를 콘솔에 표시하고 브라우저를 엽니다.

---

## 2. Windows 수동 실행

PowerShell에서 직접 실행할 때:

```powershell
uv sync --link-mode copy
copy env.example .env.local
notepad .env.local
uv run python launcher.py
```

검증 명령:

```powershell
uv run tele-quant ops-doctor
uv run tele-quant briefing --market KR --no-send
uv run tele-quant briefing --market US --no-send
uv run tele-quant stock-snapshot NVDA --market US
```

---

## 3. WSL 운영

WSL은 systemd 타이머나 장시간 자동 실행이 필요할 때만 사용합니다.

### 3-1. WSL2 설치

Windows PowerShell 관리자:

```powershell
wsl --install -d Ubuntu-22.04
wsl --set-default-version 2
```

Ubuntu 터미널:

```bash
sudo apt update
sudo apt install -y git python3.12 python3.12-venv
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.bashrc
```

### 3-2. 클론과 설정

```bash
mkdir -p ~/projects
cd ~/projects
git clone https://github.com/runkwanni21-hash/est_quant.git
cd est_quant
uv sync
cp env.example .env.local
nano .env.local
mkdir -p data/private/backups logs
```

### 3-3. WSL에서 동작 확인

```bash
uv run tele-quant ops-doctor
uv run tele-quant briefing --market KR --no-send
uv run tele-quant briefing --market US --no-send
uv run ruff check .
uv run pytest -q
```

---

## 4. WSL systemd 타이머

WSL2 systemd가 활성화된 경우:

```bash
cat /etc/wsl.conf | grep systemd
# [boot]
# systemd=true
```

타이머 설치:

```bash
mkdir -p ~/.config/systemd/user
cp systemd/*.service ~/.config/systemd/user/
cp systemd/*.timer   ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now tele-quant-briefing-kr.timer
systemctl --user enable --now tele-quant-briefing-us.timer
systemctl --user list-timers --no-pager
```

수신 봇을 상시 실행할 때:

```bash
systemctl --user enable --now tele-quant-inbound-bot.service
```

---

## 5. Windows Task Scheduler

WSL systemd를 쓰지 않을 때 Windows 작업 스케줄러에서 WSL 명령을 실행할 수 있습니다.

작업 스케줄러 프로그램:

```text
wsl.exe
```

인수 예시:

```text
-e bash -ic "cd /home/kwanni/projects/est_quant && uv run tele-quant briefing --market ALL --top-n 3 --send"
```

배치 파일 예시:

```bat
@echo off
wsl -e bash -ic "cd /home/kwanni/projects/est_quant && uv run tele-quant briefing --market ALL --top-n 3 --send >> /tmp/tele_quant.log 2>&1"
```

---

## 6. run_dashboard.bat 용도

`run_dashboard.bat`는 Windows 폴더를 WSL 경로로 변환한 뒤 Ubuntu 안에서 `uv run tele-quant dashboard`를 실행하는 WSL 전용 보조 스크립트입니다.

일반 Windows 사용자는 `run_dashboard.bat`가 아니라 `실행.bat`을 사용하세요.

---

## 7. 데이터와 보안

```bash
# WSL
ls -la data/private/
git status
grep "private" .gitignore
```

민감 파일은 Git에 올리지 않습니다.

- `.env.local`
- `data/private/tele_quant.sqlite`
- `data/private/tele_quant.session`
- `data/private/event_price_1000d.csv`
- `data/private/stock_correlation_1000d.csv`
- `logs/`

실제 주문, 자동매매, 브로커 연동, 실계좌 매매 기능은 포함하지 않습니다.

---

## 8. 트러블슈팅

| 오류 | 원인 | 해결 |
|------|------|------|
| `TELEGRAM_API_ID MISSING` | 텔레그램 채널 수집 키 미입력 | 채널 수집을 쓸 때만 `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, `TELEGRAM_PHONE` 입력 |
| Telegram 발송 실패 | 봇 토큰 또는 chat_id 미입력 | `TELEGRAM_BOT_TOKEN`, `TELEGRAM_BOT_TARGET_CHAT_ID` 확인 |
| OpenDART 수집 안 됨 | 키 미입력 또는 이름 오류 | `OPENDART_API_KEY` 사용, `DART_API_KEY` 아님 |
| `uv: command not found` | uv 미설치 | `실행.bat` 재실행 또는 `pip install uv` |
| 포트 8765 오류 | 이미 사용 중 | `launcher.py`가 자동으로 다음 포트를 사용 |
| systemd not found | WSL systemd 비활성 | `/etc/wsl.conf`에 `[boot]\nsystemd=true` 추가 후 WSL 재시작 |
| Task Scheduler 미실행 | WSL이 꺼져 있음 | `wsl --start` 트리거 작업 추가 |
| yfinance 데이터 없음 | 주말·휴장 또는 야후 지연 | 최신 영업일 데이터 사용 여부 확인 |
| SQLite 잠금 오류 | 동일 DB 동시 쓰기 | 같은 `.env.local` DB를 여러 프로세스가 쓰는지 확인 |

---

## 9. 로그 확인

```bash
# WSL systemd 로그
journalctl --user -u tele-quant-briefing-kr.service -f
journalctl --user -u tele-quant-briefing-kr.service -n 100 --no-pager

# WSL Task Scheduler 방식 로그
tail -f /tmp/tele_quant.log
```
