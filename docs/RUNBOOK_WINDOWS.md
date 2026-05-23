# RUNBOOK_WINDOWS.md — Windows 운영 가이드

> Windows + WSL 환경에서 est_quant(tele_quant) 프로젝트를 운영하는 방법  
> 대시보드 및 간단한 작업은 Windows에서 직접 실행하고, 24시간 자동화는 WSL systemd를 활용합니다.

---

## 1. Windows에서 직접 실행 (권장/간편)

개발자가 아니거나 단순 대시보드 확인용인 경우 WSL 설치 없이 Windows Python만으로도 충분합니다.

### 1-1. 사전 준비
1. [Python 3.11+](https://www.python.org/downloads/) 설치
2. [uv](https://astral.sh/) 설치 (PowerShell에서 아래 명령어 실행)
   ```powershell
   powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
   ```

### 1-2. 프로젝트 실행
1. `install.bat` 더블 클릭 (의존성 설치)
2. `env.example`을 복사하여 `.env.local` 생성 후 메모장으로 API 키 입력
3. `auth_telegram.bat` 더블 클릭 (텔레그램 인증)
4. `run.bat` 더블 클릭 (대시보드 실행)

---

## 2. WSL2 환경 설정 (고급/자동화용)

24시간 서버 운영이나 systemd 타이머를 사용하려면 WSL2가 필요합니다.

### 2-1. WSL2 설치 (이미 설치된 경우 생략)

Windows PowerShell (관리자):

```powershell
wsl --install -d Ubuntu-22.04
wsl --set-default-version 2
```

### 2-2. Python + uv 설치 (WSL Ubuntu 내)

```bash
# uv 설치
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.bashrc
```

### 2-3. 프로젝트 클론 (WSL 내)

```bash
cd ~/projects
git clone https://github.com/runkwanni21-hash/est_quant.git
cd est_quant
uv sync
```

### 2-4. .env.local 작성

```bash
cp env.example .env.local
nano .env.local
```

최소 필수 항목:

```bash
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_BOT_TARGET_CHAT_ID=your_chat_id
OPENDART_API_KEY=your_dart_key
```

### 2-5. 첫 텔레그램 인증 (1회)

```bash
uv run tele-quant auth
```

---

## 3. 동작 확인

```bash
# 시스템 자가 진단
uv run tele-quant ops-doctor

# KR 브리핑 미리보기 (발송 없음)
uv run tele-quant briefing --market KR --no-send
```

---

## 4. 자동 실행 설정 (WSL systemd)

WSL2 systemd가 활성화된 경우 (24시간 안정적 운영):

```bash
# 타이머 설치
cp systemd/*.service ~/.config/systemd/user/
cp systemd/*.timer   ~/.config/systemd/user/
systemctl --user daemon-reload

# 4H 브리핑 타이머 활성화
systemctl --user enable --now tele-quant-briefing-kr.timer
systemctl --user enable --now tele-quant-briefing-us.timer

# 수신 봇 상시 실행
systemctl --user enable --now tele-quant-inbound-bot.service
```

---

## 5. Windows Task Scheduler (WSL systemd 미사용 시)

작업 스케줄러에서 다음 작업을 4시간마다 실행하도록 설정할 수 있습니다.

**배치 스크립트 예시 (`C:\scripts\tele_quant_4h.bat`)**

```bat
@echo off
wsl -e bash -ic "cd /home/kwanni/projects/est_quant && uv run tele-quant briefing --market ALL --send >> /tmp/tele_quant.log 2>&1"
```

---

## 6. 트러블슈팅

| 오류 | 원인 | 해결 |
|------|------|------|
| `OPENDART_API_KEY MISSING` | `.env.local` 누락 | `env.example`을 참고하여 `.env.local`에 입력 |
| `FloodWait` | 채널 너무 많음 | `MAX_MESSAGES_PER_CHAT=60`으로 줄이기 |
| `systemd not found` | WSL systemd 비활성 | `/etc/wsl.conf`에 `systemd=true` 설정 필요 |
| yfinance 데이터 없음 | 주말·휴장 | 정상 (최신 영업일 데이터 사용) |

