# AGENTS.md — modoo (tele_quant) 프로젝트 지시서

> Codex가 이 프로젝트를 열 때 **반드시 가장 먼저 이 파일을 읽어라.**  
> 작성일: 2026-05-19 | 브랜치: `integration/rebuild-modoo-advisor` | 테스트: 2361개

---

## 프로젝트 목표

**한국·미국 주식 대상 4시간 단위 매매 어드바이징 시스템.**

- 텔레그램 `/분석 [종목]` → 기술·펀더멘탈·모멘텀·DCF·EPS서프라이즈·투자스코어카드 통합 분석
- 4시간마다 단 한 번의 텔레그램 브리핑으로 통합 전달 (8개 섹션)
- 잦은 알림(surge·price alert)은 score<90이면 4H 브리핑 안으로 흡수
- 이슈 선반영 여부 판단 → 수혜주 자동 라우팅
- 자기개선 루프 (추천 후 성과 추적 → 가중치 점진 조정)

---

## 절대 금지 사항

| 금지 항목 | 이유 |
|-----------|------|
| `git reset --hard` | 데이터 손실 위험 |
| `.env.local` / `data/` / `*.db` / `*.session` 커밋 | 보안 유출 |
| API 키·봇 토큰 출력·로그 기록 | 보안 유출 |
| 실계좌·브로커 주문 코드 작성 | 프로젝트 범위 외 |
| "매수 권장" / "매도 권장" / "확정 수익" / "자동매매" 표현 | 투자자 보호 |
| 테스트 깨지는 변경 커밋 | CI 정책 |

---

## 보안 규칙

### .gitignore 필수 항목 (이미 적용됨)

```
.env / .env.local / .env.*
*.session / *.session-journal
data/private/
data/*.db / data/*.sqlite
*.log / logs/
```

### 민감 파일 위치 (로컬 전용, Git 절대 불가)

```
data/private/tele_quant.sqlite
data/private/tele_quant.session
data/private/event_price_1000d.csv
data/private/stock_correlation_1000d.csv
.env.local
```

### 환경변수 (.env.local에만)

```
SQLITE_PATH=./data/private/tele_quant.sqlite
TELEGRAM_BOT_TOKEN=7xxx...
TELEGRAM_INBOUND_BOT_TOKEN=7yyy...
TELEGRAM_INBOUND_ALLOWED_IDS=879...,-1003...
OPENDART_API_KEY=...
FINNHUB_API_KEY=...
ECOS_API_KEY=...
```

---

## 4H Advisory-Only 운영 방향

### 알림 정책 (AdvisoryPolicy)

- **score ≥ 90 + direct_evidence**: 즉시 발송 (URGENT)
- **score ≥ 70**: 4H 브리핑에 포함 (ACTION / WATCH)
- **나머지**: 무시 또는 다음 4H 브리핑으로 지연

### 흡수 대상 (4H 브리핑 안으로)

- surge-scan 30분 알림 → score<90이면 4H 브리핑 섹션5(수혜주 체인)로 통합
- price-alert 30분 알림 → score<90이면 4H 브리핑 섹션6(포트폴리오)으로 통합
- daily-alpha 별도 발송 → 4H 브리핑 섹션3·4(LONG/SHORT)로 통합
- pre-market 별도 발송 → 새벽 4H 브리핑 첫 번째 발송으로 통합

### 4H 브리핑 8개 섹션 구조

```
① 시장 온도 (위험선호/중립/위험회피 + 매크로 수치)
② 리스크 노출 (Risk Mode + Gross Exposure + KR/US 비중 힌트)
③ LONG 관찰 후보 Top 3
④ SHORT/회피 후보 Top 1
⑤ 수혜주 라우팅 (급등 후 tier-2 수혜주)
⑥ 모의 포트폴리오 P&L
⑦ 다음 4H 체크포인트
⑧ 면책 문구 (필수)
```

---

## 핵심 모듈 현황 (2026-05-19 기준)

### `/분석` 파이프라인 (stock_snapshot.py 오케스트레이션)

| 파일 | 역할 |
|------|------|
| `stock_snapshot.py` | 단일 종목 분석 최종 엔진 |
| `stock_data_provider.py` | **yfinance 캐시 (TTL 5분)** — 모든 yfinance 호출 경유 필수 |
| `fundamentals.py` | PER·PBR·ROE + 심화 18개 지표 |
| `financial_quality.py` | Piotroski F-Score·Altman Z·ROIC·CAGR |
| `dcf_estimator.py` | 2단계 DCF 내재가치 (CAPM) |
| `earnings_history.py` | 5년 연간 실적 히스토리 |
| `earnings_surprise.py` | 4분기 EPS 서프라이즈·비트율·트렌드 |
| `momentum_signals.py` | SPY RS·거래량 서지·52주 돌파·Short DTC·순현금 |
| `investment_scorecard.py` | 5차원 스코어카드 (STRONG_WATCH/WATCH/NEUTRAL/AVOID) |
| `ticker_resolver.py` | 전 US 티커 지원·cap bucket·OTC·IPO·SEC EDGAR fallback |
| `tradingview.py` | TradingView 차트 URL (KRX/KOSDAQ/US) |
| `sector_intelligence.py` | 20개 섹터 심층 분석 |

### 자동화 파이프라인

| 파일 | 역할 |
|------|------|
| `advisory_policy.py` | 알림 심각도·발송 정책 중앙 관리 |
| `risk_advisor.py` | 매크로 기반 리스크 노출 판단 (김승환 전략 통합) |
| `advisor_4h.py` | 4H 어드바이징 파이프라인 오케스트레이터 |
| `daily_alpha.py` | KR/US LONG/SHORT 후보 스크리닝 |
| `supply_chain_alpha.py` | 수급 체인 스필오버 (29개 체인 규칙) |
| `briefing.py` | 4H 통합 브리핑 |
| `inbound_bot.py` | 텔레그램 수신봇 |

---

## 개발 규칙 (반드시 준수)

### yfinance 호출 규칙

```python
# ❌ 직접 호출 금지
import yfinance as yf
yf.Ticker("NVDA").info

# ✅ 캐시 경유 필수 (TTL 5분, 중복 네트워크 요청 차단)
from tele_quant.stock_data_provider import get_ticker_info
info = get_ticker_info("NVDA")
```

### inbound_bot blocking I/O 규칙

```python
# ❌ 이벤트 루프 블로킹
result = analyze_single(symbol)

# ✅ run_in_executor 필수
loop = asyncio.get_event_loop()
result = await loop.run_in_executor(None, analyze_single, symbol, market)
```

### 테스트에서 yfinance 패치 규칙

```python
# ❌ 모듈 수준 캐시가 채워져 있으면 무시됨
with patch("yfinance.Ticker", return_value=mock):

# ✅ stock_data_provider 함수를 직접 패치
with patch("tele_quant.stock_data_provider.get_income_stmt", return_value=df):
```

---

## 코딩 스타일

- Python 3.11+ 스타일, type hints 적극 사용
- `dataclass` / `pathlib` / `pydantic settings` 활용
- 작은 순수 함수 우선, side effect 최소화
- 예외는 `log.warning` 또는 `log.debug`로 남기기 (삼키지 말 것)
- `ruff check .` 통과 필수
- `pytest -q` 전량 통과 필수 (현재 2361개)
- 면책 문구 없이 종목 추천 텍스트 발송 금지
- 10Y 금리 변화는 반드시 **bp(베이시스포인트)** 단위

---

## Windows/WSL 운영 주의사항

- 개발: Windows Codex 앱에서 WSL 경로로 프로젝트 열기
- systemd 타이머 (45개 파일): WSL Ubuntu 내에서만 동작
- `.env.local`은 WSL 경로(`/home/kwanni/projects/...`)에 보관
- 데이터 파일은 `data/private/`에 보관, Git 절대 금지
- 자세한 내용: `docs/RUNBOOK_WINDOWS.md` 참조

---

## 테스트 명령

```bash
uv run ruff check .                                    # 린트
uv run pytest -q                                       # 전체 테스트 (2361개)
uv run tele-quant briefing --market KR --no-send       # KR 브리핑 미리보기
uv run tele-quant briefing --market US --no-send       # US 브리핑 미리보기
uv run tele-quant ops-doctor                           # 시스템 진단
uv run tele-quant inbound-bot -v                       # 수신봇 디버그 모드
```

---

## 다음 우선 작업 (AI에게)

1. **🔴 P1**: 이슈-주가 선반영 감지기 (`mispricing_detector.py`) — 급등 후 반영 여부 자동 판단
2. **🔴 P1**: 수혜주 자동 라우팅 강화 — `supply_chain_alpha.py` 확장, tier-2 저평가 종목 자동 발굴
3. **🟡 P2**: M&A / 자사주 공시 감시 (`corporate_action_watcher.py`) — DART "자사주매입" → LONG +15점
4. **🟡 P2**: 자기개선 가중치 조정 (`weight_optimizer.py`) — 주간 성과 데이터로 scoring 가중치 점진 조정
5. **🟠 P3**: 섹터별 가치평가 강화 — 반도체=수주잔고 35%, 바이오=임상 40%, 은행=NIM·NPL 50%

---

## 참고 문서

- `ONBOARDING.md` — AI 온보딩 퀵스타트 (텔레그램 명령·점수 구조·개발 규칙)
- `docs/HANDOVER.md` — 모듈별 상세 설명 + 아키텍처 흐름도
- `docs/PROJECT_STATE.md` — 현재 구현 상태 전체 목록
- `docs/MODERNIZATION_PLAN.md` — 단계별 개선 계획
- `docs/DATA_MIGRATION.md` — 데이터 이전 가이드
- `docs/RUNBOOK_WINDOWS.md` — Windows/WSL 운영 가이드
- `docs/SEUNGHWAN_STRATEGY.md` — 김승환 전략 통합 방향
