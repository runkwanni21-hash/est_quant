# Tele Quant — 한국·미국 주식 AI 분석 대시보드

한국(KRX/KOSDAQ) 및 미국 주식을 대상으로 기술적·펀더멘탈·모멘텀 분석을 통합 제공하는
로컬 웹 대시보드입니다. Windows 10/11 + WSL2 환경에서 동작하며,
브라우저 하나로 전 기능을 사용할 수 있습니다.

---

## 1. 프로젝트 개요

### 커버리지

워치리스트 기본 종목 **177종목** (중복 제외), **16개 그룹**:

| 그룹 | 설명 | 종목 수 |
|------|------|---------|
| `core_kr` | 국내 핵심 대형주 (KOSPI 대표) | 17 |
| `kr_semiconductor` | 국내 반도체/HBM/장비/소재 | 9 |
| `kr_growth` | 국내 성장/테마 (방산·조선·바이오) | 13 |
| `kr_defense` | 국내 방산/우주 | 6 |
| `kr_finance` | 국내 금융 (은행·보험·증권) | 10 |
| `kr_bio` | 국내 바이오/헬스케어 | 9 |
| `kr_energy_material` | 국내 에너지/소재/2차전지 | 10 |
| `us_ai_bigtech` | 미국 AI/빅테크 (Mag7 등) | 24 |
| `us_semiconductor` | 미국 반도체 장비/소재 | 10 |
| `us_healthcare` | 미국 헬스케어/제약/바이오 | 11 |
| `us_consumer` | 미국 소비/유통/레저 | 14 |
| `us_finance` | 미국 금융 (대형은행·핀테크) | 12 |
| `us_energy_industrial` | 미국 에너지/방산/물류 | 11 |
| `us_ev_energy_transition` | 미국 EV/에너지전환 | 5 |
| `macro_etf` | 매크로/ETF 관찰 (SPY, QQQ 등) | 18 |
| `kr_etf` | 국내 ETF/지수 | 6 |

> yfinance 직접 입력으로 전 세계 **10만 개+** 티커 분석 가능.
> 예: `AAPL`, `NVDA`, `삼성전자`, `005930.KS`, `TSLA`, `000660.KS`

---

## 2. 빠른 시작 (Windows 10/11)

### 사전 조건

- Windows 10 (21H2+) 또는 Windows 11
- 인터넷 연결

### Step 1 — WSL2 설치

관리자 PowerShell을 열고 실행:

```powershell
wsl --install
```

재부팅 후 Ubuntu 초기 사용자 이름·비밀번호를 설정합니다.

> 이미 WSL2 + Ubuntu가 설치되어 있으면 Step 1을 건너뜁니다.

### Step 2 — 프로젝트 클론

Windows 탐색기에서 원하는 위치로 이동한 후, WSL Ubuntu 터미널에서:

```bash
git clone https://github.com/runkwanni21-hash/est_quant
```

또는 GitHub에서 ZIP으로 다운로드 후 압축 해제해도 됩니다.

### Step 3 — setup.bat 실행

압축 해제한 폴더에서 `setup.bat`을 더블클릭합니다.

자동으로 진행되는 작업:
- WSL2 Ubuntu 연결 확인
- WSL 사용자명 및 프로젝트 경로 자동 감지
- 심볼릭 링크 `~/tq` 생성
- `uv` (패키지 관리자) 설치
- Python 패키지 설치 (최초 3~5분 소요)
- `.env.local` 파일 생성 (env.template 복사)
- `.env.local` 메모장 자동 오픈

### Step 4 — API 키 입력

메모장으로 열린 `.env.local`에서 원하는 API 키를 입력합니다.

- **필수 없음**: 키 없이도 yfinance 기반 분석은 전부 동작합니다.
- **텔레그램 알림** 사용 시: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_BOT_TARGET_CHAT_ID`
- 각 키 발급 방법은 [3. 환경변수 상세 설명](#3-환경변수-상세-설명) 참조

### Step 5 — 대시보드 실행

`run_dashboard.bat` (또는 `실행.bat`)을 더블클릭하면:
- WSL에서 FastAPI 서버가 시작됩니다.
- 8초 후 브라우저에서 http://localhost:8765 가 자동으로 열립니다.
- 창을 닫거나 `Ctrl+C`를 누르면 서버가 종료됩니다.

---

## 3. 환경변수 상세 설명

`.env.local` 파일에서 설정합니다. `[선택]` 항목은 없어도 기본 동작합니다.

### 대시보드 접근 제어

| 변수 | 필수 | 설명 |
|------|------|------|
| `DASHBOARD_MASTER_KEY` | 선택 | 소유자용 키, 세션 만료 없음. 미설정 시 인증 없이 누구나 접근 |
| `DASHBOARD_PASSWORD` | 선택 | 일반 사용자용 비밀번호, 24시간 세션 |

> 집 내부 PC 단독 사용 시 두 항목 모두 비워도 됩니다.

### 텔레그램 발신 봇

| 변수 | 필수 | 설명 | 발급 |
|------|------|------|------|
| `TELEGRAM_BOT_TOKEN` | 선택 | 4H 브리핑·급등 알림 발송 봇 토큰 | [BotFather](https://t.me/BotFather) → `/newbot` |
| `TELEGRAM_BOT_TARGET_CHAT_ID` | 선택 | 알림 수신 채팅 ID | [@userinfobot](https://t.me/userinfobot) |

### 텔레그램 사용자 API (증권사 채널 수집)

| 변수 | 필수 | 설명 | 발급 |
|------|------|------|------|
| `TELEGRAM_API_ID` | 선택 | Telegram 앱 ID (숫자) | [my.telegram.org/apps](https://my.telegram.org/apps) |
| `TELEGRAM_API_HASH` | 선택 | Telegram 앱 Hash (32자리) | 동일 |
| `TELEGRAM_PHONE` | 선택 | 로그인 전화번호 (+8210...) | 동일 |

> 없으면 yfinance + 뉴스 API만으로 동작합니다.

### 데이터 소스 API 키

| 변수 | 필수 | 활성화 기능 | 발급 |
|------|------|------------|------|
| `YFINANCE_ENABLED=true` | 기본값 | 주가 OHLCV, PER/PBR/ROE, 재무제표 (항상 활성) | 불필요 |
| `FINNHUB_API_KEY` | 선택 | 미국 기업 뉴스 건수 + EPS 서프라이즈 | [finnhub.io](https://finnhub.io) (무료) |
| `OPENDART_API_KEY` | 선택 | 한국 전자공시 (수주/자사주/실적) | [opendart.fss.or.kr](https://opendart.fss.or.kr) (1~2일 소요) |
| `NAVER_CLIENT_ID` + `NAVER_CLIENT_SECRET` | 선택 | 국내 뉴스 검색 + 증권 리포트 링크 | [developers.naver.com](https://developers.naver.com) |
| `FRED_API_KEY` | 선택 | 미국 연준 매크로 지표 (금리·실업률·CPI) | [fred.stlouisfed.org](https://fred.stlouisfed.org/docs/api) (무료) |
| `ECOS_API_KEY` | 선택 | 한국은행 경제통계 (기준금리·통화량·환율) | [ecos.bok.or.kr](https://ecos.bok.or.kr) (무료) |
| `ALPHAVANTAGE_API_KEY` | 선택 | 기술지표 보완 | [alphavantage.co](https://www.alphavantage.co/support/#api-key) (무료) |
| `NEWSAPI_KEY` | 선택 | 영어 뉴스 헤드라인 | [newsapi.org](https://newsapi.org/register) (무료 100req/일) |
| `FMP_API_KEY` | 선택 | EV/EBITDA, FCF, 실적 캘린더 | [financialmodelingprep.com](https://site.financialmodelingprep.com) |
| `OLLAMA_HOST` | 선택 | 로컬 AI 모델 연동 (없으면 규칙 기반 동작) | [ollama.com](https://ollama.com) 로컬 설치 |

---

## 4. 대시보드 기능 (8개 탭)

브라우저에서 http://localhost:8765 접속 후 상단 탭으로 이동합니다.

### 홈 / 워치리스트

- 워치리스트 177종목 실시간 주가·등락률 표시
- RSI, 볼린저밴드%, 거래량비율 기반 간이 등급 표시
- 관심 종목 즐겨찾기 기능

### 스크리너

- 전체 177종목 병렬 스캔 (약 30초 소요)
- 종합 점수 기준 정렬 — ★★★ / ★★ / ★ / 중립 등급
- 섹터·시가총액·RSI 범위 필터

### 종목 분석

- 한글명(`삼성전자`), 티커(`NVDA`), 종목코드(`005930.KS`) 모두 입력 가능
- 출력 내용:
  - 기술적 분석 (RSI, OBV, 볼린저밴드, 거래량)
  - 펀더멘탈 (PER, PBR, ROE, 52주 위치)
  - 재무 품질 (Piotroski F-Score, Altman Z-Score, ROIC, CAGR)
  - DCF 내재가치 (2단계 성장모델)
  - EPS 서프라이즈 (4분기 비트율·트렌드)
  - 투자 스코어카드 (5차원 종합 점수)
  - TradingView 차트 링크

### 4H 브리핑

- KR / US 시장별 4시간 단위 매크로 + 섹터 리포트
- 8개 섹션: 시장온도, 리스크노출, LONG후보 Top3, SHORT/회피후보, 수혜주 체인, 모의포트폴리오 P&L, 다음 체크포인트, 면책고지
- `--no-send` 플래그로 터미널 미리보기 가능

### 텔레그램 설정

- 봇 토큰, 채팅 ID를 브라우저에서 직접 설정·저장
- 테스트 메시지 발송 확인 기능

### 4H 스케줄러

- 자동 브리핑 발송 주기 설정 (4시간 기본)
- KR/US 시장별 독립 스케줄 설정 가능
- 다음 발송 예정 시간 표시

### 데이터 소스

- 각 API 키 활성화/비활성화 상태 시각화
- API 응답 상태 실시간 확인

### Ollama AI

- 로컬 LLM 모델 설정 (기본: `qwen3:8b`)
- 뉴스 감성 심화 분석, 브리핑 자연어 다듬기 기능

---

## 5. 데이터 수집 방법 (14개 소스)

| 소스 | 수집 내용 | 방식 | 비고 |
|------|----------|------|------|
| Yahoo Finance (yfinance) | OHLCV, PER/PBR/ROE, 재무제표, 애널리스트 의견 | Python 라이브러리 | TTL 5분 캐시, API 키 불필요 |
| OpenDART | 수주계약, 자사주매입, 실적공시 | REST API | 한국 전자공시 |
| SEC EDGAR | 미국 8-K 공시 원문 파싱 | REST API | 무료·공개 |
| FRED | 금리, 실업률, CPI, M2 | REST API | 무료, 즉시 발급 |
| ECOS | 한국은행 기준금리, 통화량, 환율 | REST API | 무료 |
| Finnhub | 뉴스 건수, EPS 실제치 vs 예상치 | REST API | 무료 플랜 즉시 발급 |
| NewsAPI | 영어 뉴스 헤드라인 | REST API | 무료 100req/일 |
| FMP | EV/EBITDA, FCF, 실적 캘린더 | REST API | 무료 플랜 가능 |
| Naver Open API | 국내 뉴스, 증권사 리포트 링크 | REST API | 검색 API 신청 필요 |
| Telegram 채널 | 증권사 리포트 텍스트 자동 수집 | Telethon (MTProto) | API ID/Hash 필요 |
| RSS | PR Newswire, Globe Newswire, BusinessWire | RSS 파싱 | API 키 불필요 |
| EIA | 원유 재고, 생산량 | REST API | 무료 |
| pykrx | KRX 시가총액, 외국인·기관 순매수 | Python 라이브러리 | API 키 불필요 |
| Alpha Vantage | 기술지표 보완 (EMA, MACD) | REST API | 무료 플랜 |

---

## 6. 분석 방법론

### 4H 기술 분석

- **RSI(14)**: 과매도(< 30) / 중립(30-70) / 과열(> 70)
- **OBV 트렌드**: 20봉 선형회귀 기울기로 수급 방향 판단
- **볼린저밴드%**: `(종가 - 하단) / (상단 - 하단)` — 0.2 이하 = 하단 근접
- **거래량비율**: 20일 평균 대비 현재 거래량 비율 (2x 이상 = 서지)

### 펀더멘탈 분석

- PER, PBR, ROE (yfinance 제공값)
- 52주 위치: `(현재가 - 52주저가) / (52주고가 - 52주저가)`
- 시가총액 구간별 기관 사각지대 가산점 (중형주)

### 재무 품질 분석

- **Piotroski F-Score** (0-9): 수익성(4) + 레버리지(3) + 효율성(2) 9개 지표
- **Altman Z-Score**: Z > 2.99 안전, 1.81-2.99 회색지대, < 1.81 위험
- **ROIC**: `영업이익(1-세율) / 투하자본`
- **매출 CAGR**: 3년 연평균 성장률

### DCF 내재가치

2단계 성장 모델:
1. 고성장 기간 (5년): EPS 성장률 적용
2. 영구 성장 기간: 터미널 성장률 적용
- 할인율: CAPM (`Rf + 베타 x ERP`)

### EPS 서프라이즈

- 4분기 실제치 vs. 컨센서스 비교
- 비트율(%), 서프라이즈 크기, 상승/하락 트렌드 판단

### 모멘텀 분석

- **SPY 상대강도(RS)**: `(종목 수익률 - SPY 수익률)` 60일
- **52주 돌파**: 신고가 근접 여부
- **Short Float**: 공매도 비율 (높을수록 숏스퀴즈 가능성)

### 매크로 레짐 판단

VIX, 10Y 금리(bp 단위), USD-KRW, WTI 원유 조합으로:
- **Risk-On**: VIX < 20, 금리 안정, 달러 약세
- **Neutral**: 혼재 신호
- **Risk-Off**: VIX > 30, 금리 급등, 달러 강세

---

## 7. 종합 점수 계산

### 점수 공식

```
total_score = min(tech_score/40 x 50 + val_score/100 x 50, 100)
```

### 기술 점수 (tech_score, 0-40)

| 조건 | 점수 |
|------|------|
| RSI < 30 (과매도) | +15 |
| RSI 30-70 (중립) | +8 |
| RSI > 70 (과열) | -5 |
| OBV 상승 트렌드 | +10 |
| 볼린저밴드% < 0.2 (하단 근접) | +8 |
| 거래량 서지 (> 2x 평균) | +7 |

### 가치 점수 (val_score, 0-100)

| 조건 | 점수 |
|------|------|
| PER < 10 | +30 |
| PER 10-20 | +20 |
| PER 20-30 | +10 |
| PBR < 1 | +20 |
| PBR 1-2 | +15 |
| PBR 2-3 | +8 |
| ROE > 20% | +25 |
| ROE 10-20% | +15 |
| ROE 5-10% | +8 |
| 52주 위치 < 30% (저가 구간) | +8 |
| 52주 위치 > 85% (고가 구간) | -5 |
| 기관 사각지대 (중형주) | +5 |

### 등급

| 점수 | 등급 | 의미 |
|------|------|------|
| 80점 이상 | ★★★ | 강력 관찰 (STRONG_WATCH) |
| 65점 이상 | ★★  | 관찰 (WATCH) |
| 50점 이상 | ★   | 약한 관찰 (NEUTRAL) |
| 50점 미만 | -   | 회피 (AVOID) |

> **면책 고지**: 모든 점수는 공개 데이터 기반 알고리즘 참고값이며,
> 투자 판단의 최종 책임은 사용자에게 있습니다.

---

## 8. 백엔드 구조

| 항목 | 상세 |
|------|------|
| 언어 | Python 3.11+ |
| 패키지 관리 | [uv](https://github.com/astral-sh/uv) (Astral) |
| 웹 프레임워크 | FastAPI + Uvicorn |
| 설정 관리 | Pydantic Settings (`.env.local`) |
| 데이터베이스 | SQLite (aiosqlite) |
| 스케줄링 | systemd timer (WSL) + APScheduler (in-process) |

### 핵심 모듈

| 파일 | 역할 |
|------|------|
| `stock_snapshot.py` | 단일 종목 분석 오케스트레이터 |
| `stock_data_provider.py` | yfinance 캐시 레이어 (TTL 5분) |
| `fundamentals.py` | PER/PBR/ROE + 심화 18개 지표 |
| `financial_quality.py` | Piotroski F-Score, Altman Z, ROIC, CAGR |
| `dcf_estimator.py` | 2단계 DCF 내재가치 (CAPM 할인율) |
| `earnings_history.py` | 5년 연간 실적 히스토리 |
| `earnings_surprise.py` | 4분기 EPS 서프라이즈·비트율·트렌드 |
| `momentum_signals.py` | SPY RS, 거래량 서지, 52주 돌파, Short Float |
| `investment_scorecard.py` | 5차원 종합 스코어카드 |
| `sector_intelligence.py` | 20개 섹터 심층 분석 |
| `advisor_4h.py` | 4H 어드바이징 파이프라인 오케스트레이터 |
| `briefing.py` | 4H 통합 브리핑 생성 |
| `risk_advisor.py` | 매크로 기반 리스크 노출 판단 |
| `ticker_resolver.py` | 전 US 티커 지원, SEC EDGAR fallback |
| `advisory_policy.py` | 알림 심각도·발송 정책 중앙 관리 |

---

## 9. 프론트엔드 구조

| 항목 | 상세 |
|------|------|
| 기술 스택 | 순수 HTML / CSS / JavaScript (외부 프레임워크 없음) |
| 구조 | 단일 파일 SPA — `src/tele_quant/dashboard/app.py` 내 HTML 인라인 |
| 테마 | 다크 테마 기본 |
| 탭 구성 | 8개 탭 (상단 네비게이션) |
| API 통신 | `fetch()` → FastAPI JSON 응답 |
| 가격 표시 | KRW → 원화(W), USD → 달러($) 자동 포맷 |

---

## 10. 트러블슈팅

### WSL2가 설치되어 있지 않음

```powershell
# 관리자 PowerShell에서 실행
wsl --install
# 재부팅 후 Ubuntu 초기 설정 진행
```

### 포트 8765 충돌

```bash
# WSL Ubuntu 터미널에서 실행
fuser -k 8765/tcp
```

### "사이트에 연결할 수 없음" 오류

1. `run_dashboard.bat` 창이 열려 있는지 확인 (서버 실행 중이어야 함)
2. `_launch.sh`가 `--host 0.0.0.0`으로 실행되는지 확인
3. WSL IP 확인: `wsl hostname -I`

### yfinance 데이터가 없거나 오래됨

- TTL 캐시: 동일 종목은 5분 내 재호출 시 캐시 반환됩니다. 5분 후 재시도하세요.
- `.env.local`에서 `OFFLINE_MODE=false` 확인

### 한글 입력·출력 오류

```cmd
chcp 65001
```

CMD 창에서 UTF-8 코드 페이지를 활성화합니다.

### setup.bat을 재실행하고 싶을 때

프로젝트 폴더에서 `.setup_done` 파일을 삭제한 후 `setup.bat`을 다시 실행합니다.

### uv 명령을 찾을 수 없음 (WSL)

```bash
# WSL Ubuntu 터미널에서 직접 설치
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.bashrc
```

---

## 11. 라이선스 및 면책

이 소프트웨어는 공개 데이터 기반 **개인 리서치 보조 도구**입니다.

- 매수·매도 추천이 아닙니다.
- 과거 데이터 기반 분석이며 미래 수익을 보장하지 않습니다.
- 투자 판단의 최종 책임은 사용자에게 있습니다.
- 실계좌 자동 매매 기능은 포함되어 있지 않습니다.
