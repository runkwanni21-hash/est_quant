# Tele Quant — 한국·미국 주식 AI 분석 대시보드

한국(KRX/KOSDAQ) 및 미국 주식을 대상으로 기술적·펀더멘탈·모멘텀·DCF·EPS 서프라이즈·수급 분석을 통합 제공하는
로컬 웹 대시보드 + 텔레그램 4H 자동 브리핑 시스템입니다.
Windows 10/11 + WSL2 환경에서 브라우저 하나로 전 기능을 사용할 수 있습니다.

---

## 목차

1. [프로젝트 개요 · 분석 대상 종목](#1-프로젝트-개요--분석-대상-종목)
2. [빠른 시작 (Windows 10/11)](#2-빠른-시작-windows-1011)
3. [환경변수 설정](#3-환경변수-설정)
4. [디렉터리 구조](#4-디렉터리-구조)
5. [백엔드 아키텍처 · 코딩 원칙](#5-백엔드-아키텍처--코딩-원칙)
6. [매집 평가 방법론](#6-매집-평가-방법론-accumulation-detector)
7. [주식 점수 계산 방법론](#7-주식-점수-계산-방법론)
8. [데이터 수집 파이프라인](#8-데이터-수집-파이프라인)
9. [대시보드 기능 (8개 탭)](#9-대시보드-기능-8개-탭)
10. [기술 스택](#10-기술-스택)
11. [트러블슈팅](#11-트러블슈팅)
12. [개발자·학부생 Q&A 30선](#12-개발자학부생-qa-30선)
13. [라이선스 및 면책](#13-라이선스-및-면책)

---

## 1. 프로젝트 개요 · 분석 대상 종목

### 무엇을 하는 프로그램인가

한국·미국 주식에 대해 4시간 단위로 아래 분석을 자동 수행합니다:

- **기술적 분석**: RSI, OBV, 볼린저밴드, 거래량 서지
- **펀더멘탈 분석**: PER, PBR, ROE + 심화 18개 지표
- **재무 품질**: Piotroski F-Score (9점), Altman Z-Score, ROIC, 매출 CAGR
- **DCF 내재가치**: 2단계 성장 모델 (CAPM 할인율)
- **EPS 서프라이즈**: 최근 4분기 비트율·서프라이즈 크기·추세
- **모멘텀**: SPY 상대강도, 52주 돌파, Short Float, 수급 방향
- **매집 탐지**: Wyckoff 이론 기반 7구성요소 복합 신호
- **기관/외국인 수급**: pykrx KRX 순매수 데이터 + OBV proxy
- **매크로 레짐**: VIX, 10Y 금리(bp), USD, WTI 조합으로 Risk-On/Off 판정

분석 결과는 **로컬 웹 대시보드** 또는 **텔레그램 4H 브리핑**으로 확인합니다.

### 기본 워치리스트 177종목 (16개 그룹)

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

### 임의 종목 분석

워치리스트 외에도 아래 형식으로 **전 세계 10만 개+ 티커**를 분석할 수 있습니다:

| 입력 형식 | 예시 |
|-----------|------|
| 미국 티커 | `AAPL`, `NVDA`, `TSLA` |
| 한글 회사명 | `삼성전자`, `SK하이닉스`, `카카오` |
| KRX 코드 | `005930.KS`, `000660.KS` |
| KOSDAQ 코드 | `035720.KQ`, `247540.KQ` |

한글 회사명 → 티커 매핑은 `config/ticker_aliases.yml`에 정의된 **14,495개 별명 테이블**을 사용하며,
없는 경우 SEC EDGAR 검색으로 자동 fallback합니다.

---

## 2. 빠른 시작 (Windows 10/11)

### 사전 조건

- Windows 10 (21H2+) 또는 Windows 11
- 인터넷 연결

### Step 1 — WSL2 설치

관리자 PowerShell에서:

```powershell
wsl --install
```

재부팅 후 Ubuntu 초기 사용자 이름·비밀번호를 설정합니다.
이미 WSL2 + Ubuntu가 설치되어 있으면 Step 1을 건너뜁니다.

### Step 2 — 프로젝트 다운로드

GitHub에서 ZIP으로 다운로드 후 압축 해제하거나:

```bash
git clone https://github.com/runkwanni21-hash/est_quant
```

### Step 3 — setup.bat 실행

압축 해제한 폴더에서 `setup.bat`을 더블클릭합니다.

| 단계 | 내용 |
|------|------|
| [0/5] | WSL2 Ubuntu 연결 확인 |
| [1/5] | 이미 설정된 경우 건너뜀 (`.setup_done` 체크) |
| [2/5] | WSL 사용자명 자동 감지 + 프로젝트 경로 변환 |
| [3/5] | 심볼릭 링크 `~/tq` 생성 |
| [4/5] | `uv` (패키지 관리자) 설치 |
| [5/5] | Python 패키지 설치 (최초 3~5분 소요) |
| 완료 | `.env.local` 생성 후 메모장 자동 오픈 |

### Step 4 — API 키 입력 (선택)

메모장으로 열린 `.env.local`에 원하는 API 키를 입력합니다.
키 없이도 yfinance 기반 분석(기술·펀더멘탈·재무품질·DCF·EPS)은 **전부 동작**합니다.

### Step 5 — 대시보드 실행

`실행.bat`(또는 `run_dashboard.bat`)을 더블클릭하면:

1. WSL에서 FastAPI 서버가 포트 8765에서 시작됩니다.
2. 8초 후 브라우저에서 `http://localhost:8765`가 자동으로 열립니다.
3. 창을 닫거나 `Ctrl+C`를 누르면 서버가 종료됩니다.

---

## 3. 환경변수 설정

`.env.local` 파일에서 설정합니다. `[선택]` 항목은 없어도 기본 기능이 동작합니다.

### 대시보드 접근 제어

| 변수 | 필수 | 설명 |
|------|------|------|
| `DASHBOARD_MASTER_KEY` | 선택 | 소유자용 키, 세션 만료 없음 |
| `DASHBOARD_PASSWORD` | 선택 | 일반 사용자용 비밀번호, 24시간 세션 |

### 텔레그램 발신 봇

| 변수 | 설명 | 발급 |
|------|------|------|
| `TELEGRAM_BOT_TOKEN` | 4H 브리핑·급등 알림 발송 봇 | [BotFather](https://t.me/BotFather) → `/newbot` |
| `TELEGRAM_BOT_TARGET_CHAT_ID` | 알림 수신 채팅 ID | [@userinfobot](https://t.me/userinfobot) |

### 텔레그램 사용자 API (증권사 채널 수집)

| 변수 | 설명 | 발급 |
|------|------|------|
| `TELEGRAM_API_ID` | Telegram 앱 ID | [my.telegram.org/apps](https://my.telegram.org/apps) |
| `TELEGRAM_API_HASH` | Telegram 앱 Hash (32자리) | 동일 |
| `TELEGRAM_PHONE` | 로그인 전화번호 (+8210...) | 동일 |

### KRX 기관/외국인 수급 데이터

| 변수 | 설명 | 발급 |
|------|------|------|
| `KRX_ID` | KRX InfoData 아이디 | [data.krx.co.kr](https://data.krx.co.kr) 무료 회원가입 |
| `KRX_PW` | KRX InfoData 비밀번호 | 동일 |

> 미설정 시 기관/외국인 순매수 섹션이 공란으로 표시됩니다. 나머지 분석은 정상 동작합니다.

### 데이터 소스 API 키

| 변수 | 활성화 기능 | 발급 |
|------|------------|------|
| `FINNHUB_API_KEY` | 미국 기업 뉴스 건수 + EPS 서프라이즈 | [finnhub.io](https://finnhub.io) |
| `OPENDART_API_KEY` | 한국 전자공시 (수주/자사주/실적) | [opendart.fss.or.kr](https://opendart.fss.or.kr) |
| `NAVER_CLIENT_ID` / `NAVER_CLIENT_SECRET` | 국내 뉴스·증권 리포트 링크 | [developers.naver.com](https://developers.naver.com) |
| `FRED_API_KEY` | 미국 연준 매크로 (금리·실업률·CPI) | [fred.stlouisfed.org](https://fred.stlouisfed.org/docs/api) |
| `ECOS_API_KEY` | 한국은행 통계 (기준금리·환율·M2) | [ecos.bok.or.kr](https://ecos.bok.or.kr) |
| `ALPHAVANTAGE_API_KEY` | 기술지표 보완 (EMA, MACD) | [alphavantage.co](https://www.alphavantage.co/support/#api-key) |
| `NEWSAPI_KEY` | 영어 뉴스 헤드라인 | [newsapi.org](https://newsapi.org/register) |
| `FMP_API_KEY` | EV/EBITDA, FCF, 실적 캘린더 | [financialmodelingprep.com](https://site.financialmodelingprep.com) |

---

## 4. 디렉터리 구조

```
est_quant-main_tele/
├── setup.bat                        # 최초 1회 실행 — uv 설치·패키지 동기화
├── 실행.bat                          # 대시보드 실행 진입점 (더블클릭)
├── run_dashboard.bat                 # 실행.bat 동일 기능 (영문 파일명 버전)
├── .setup_done                      # setup.bat 완료 표시 파일 (자동 생성)
├── .env.local                       # 로컬 환경변수 (Git 미포함, 반드시 보안 유지)
├── pyproject.toml                   # uv/Python 프로젝트 설정 + 패키지 의존성
├── CLAUDE.md                        # AI 어시스턴트 지시서 (코딩 규칙·금지사항)
│
├── config/
│   ├── watchlist.yml                # 177종목 워치리스트 (16개 그룹)
│   ├── ticker_aliases.yml           # 한글명 → 티커 매핑 14,495개
│   └── supply_chain_rules.yml      # 수급 체인 29개 규칙
│
├── src/tele_quant/                  # 핵심 Python 패키지
│   │
│   ├── settings.py                  # Pydantic Settings — .env.local 파싱 단일 창구
│   ├── db.py                        # SQLite 스키마·CRUD (2,392줄, 최대 모듈)
│   ├── stock_data_provider.py       # ★ yfinance TTL-5분 캐시 허브 — 전 호출 경유
│   ├── stock_snapshot.py            # ★ 단일 종목 분석 오케스트레이터 (1,432줄)
│   │
│   ├── analysis/                    # 분석 서브모듈
│   │   ├── scoring.py               # RSI/OBV/볼린저 → tech_score / val_score / 별점
│   │   ├── fundamentals.py          # PER·PBR·ROE + 심화 18개 지표
│   │   ├── financial_quality.py     # Piotroski F-Score · Altman Z-Score · ROIC · CAGR
│   │   ├── dcf_estimator.py         # 2단계 DCF 내재가치 (CAPM 할인율)
│   │   ├── earnings_history.py      # 5년 연간 실적 히스토리
│   │   ├── earnings_surprise.py     # 4분기 EPS 서프라이즈·비트율·추세
│   │   ├── momentum_signals.py      # SPY RS · 거래량 서지 · 52주 돌파 · Short DTC
│   │   ├── investment_scorecard.py  # 5차원 투자 스코어카드 (STRONG_WATCH~AVOID)
│   │   ├── accumulation_detector.py # Wyckoff 기반 7구성요소 매집 탐지 (0~100점)
│   │   ├── institutional_flow.py    # pykrx 기관/외국인 순매수 + OBV proxy
│   │   ├── sector_intelligence.py   # 20개 섹터 심층 분석
│   │   └── report_models.py         # 분석 결과 dataclass 모음
│   │
│   ├── advisor_4h.py                # ★ 4H 어드바이징 파이프라인 오케스트레이터
│   ├── briefing.py                  # 4H 통합 브리핑 8섹션 생성
│   ├── daily_alpha.py               # KR/US LONG/SHORT 후보 스크리닝 (1,600줄)
│   ├── risk_advisor.py              # 매크로 기반 리스크 노출 판단
│   ├── advisory_policy.py           # 알림 심각도·발송 정책 중앙 관리
│   ├── supply_chain_alpha.py        # 수급 체인 스필오버 (29개 체인 규칙)
│   ├── sector_rotation.py           # 섹터 로테이션 탐지
│   ├── macro_pulse.py               # VIX·금리·달러·원유 → 매크로 레짐 판정
│   ├── top_mover_miner.py           # 최근 3개월 급등주 자동 선별 엔진
│   │
│   ├── ticker_resolver.py           # 티커 유효성·OTC·IPO·SEC EDGAR fallback
│   ├── ticker_universe.py           # KR/US 전체 상장 종목 목록 조회
│   ├── tradingview.py               # TradingView 차트 URL 생성
│   │
│   ├── fetchers/                    # 외부 데이터 수집기
│   │   ├── finnhub_client.py        # Finnhub EPS + 뉴스
│   │   ├── opendart_client.py       # DART 공시 파서
│   │   ├── naver_client.py          # 네이버 뉴스·리포트
│   │   ├── fred_client.py           # FRED 매크로 지표
│   │   ├── ecos_client.py           # 한국은행 ECOS
│   │   ├── fmp_client.py            # FMP 재무 데이터
│   │   ├── newsapi_client.py        # NewsAPI 영어 뉴스
│   │   └── sec_edgar_client.py      # SEC 8-K 공시 파서
│   │
│   ├── inbound_bot.py               # 텔레그램 수신봇 (/분석 처리, asyncio)
│   ├── relation_feed.py             # 종목 관계 그래프 + 수혜주 체인
│   │
│   ├── dashboard/
│   │   └── app.py                   # FastAPI + 인라인 SPA HTML (단일 파일)
│   │
│   └── cli/
│       ├── __main__.py              # `uv run tele-quant` 진입점
│       ├── _briefing.py             # briefing CLI 서브커맨드
│       ├── _dashboard.py            # dashboard CLI 서브커맨드 (로깅 필터 포함)
│       └── _ops_doctor.py           # ops-doctor 시스템 진단
│
├── tests/                           # pytest 테스트 스위트 (2,477개)
│   ├── test_scoring.py
│   ├── test_financial_quality.py
│   ├── test_dcf_estimator.py
│   ├── test_earnings_surprise.py
│   ├── test_accumulation_detector.py
│   └── ...
│
├── data/                            # 로컬 전용 데이터 (Git 미포함)
│   ├── tele_quant.sqlite            # SQLite DB
│   └── *.session                    # Telegram MTProto 세션
│
└── docs/
    ├── HANDOVER.md                  # 모듈별 상세 설명 + 아키텍처 흐름도
    ├── RUNBOOK_WINDOWS.md           # Windows/WSL 운영 가이드
    └── SEUNGHWAN_STRATEGY.md        # 전략 통합 방향
```

---

## 5. 백엔드 아키텍처 · 코딩 원칙

### 프로세스 흐름

```
브라우저 요청
    │
    ▼
FastAPI (dashboard/app.py, port 8765)
    │  ├─ GET /api/analyze/{symbol}      asyncio → run_in_executor
    │  ├─ GET /api/screener              ThreadPoolExecutor (병렬)
    │  ├─ POST /api/briefing             4H 브리핑 JSON
    │  └─ GET|POST /api/settings        .env.local 읽기/쓰기
    │
    ▼
stock_snapshot.py   ←  오케스트레이터 (~10초/종목)
    │
    ├─ stock_data_provider.py  ←  TTL 5분 메모리 캐시
    │      │
    │      └─ yfinance / pykrx / REST APIs
    │
    ├─ analysis/scoring.py           기술·가치 점수 → 별점
    ├─ analysis/fundamentals.py      PER/PBR/ROE 심화
    ├─ analysis/financial_quality.py Piotroski / Altman Z / ROIC
    ├─ analysis/dcf_estimator.py     2단계 DCF
    ├─ analysis/earnings_surprise.py EPS 서프라이즈
    ├─ analysis/momentum_signals.py  RS / 거래량 / 52W
    ├─ analysis/investment_scorecard.py 5차원 스코어카드
    ├─ analysis/accumulation_detector.py Wyckoff 매집 탐지
    └─ analysis/institutional_flow.py   기관/외국인 수급
```

### 핵심 설계 원칙 4가지

#### 원칙 1 — 캐시 허브 패턴

yfinance는 요청당 수백 ms ~ 수 초가 걸리며, 스크리너(177종목 병렬)나 브리핑에서
동일 종목에 대한 중복 호출이 발생합니다. 모든 yfinance 호출을 `stock_data_provider.py`
한 파일에 집중시키고 TTL 5분 인메모리 캐시를 적용합니다.

```python
# ❌ 금지 — 직접 호출
import yfinance as yf
yf.Ticker("NVDA").info

# ✅ 필수 — 캐시 경유
from tele_quant.stock_data_provider import get_ticker_info
info = get_ticker_info("NVDA")
```

#### 원칙 2 — 순수 함수 우선

분석 함수들(DCF, Piotroski, EPS 서프라이즈 등)은 모두 `dict → float | str | dataclass` 형태의
순수 함수입니다. 네트워크 I/O를 직접 수행하지 않으며, `stock_data_provider`에서
가져온 데이터를 받아 계산만 합니다. 이로 인해 `pytest`에서 dict mock만으로 전 로직을
테스트할 수 있습니다.

#### 원칙 3 — asyncio 블로킹 격리

FastAPI는 비동기 서버이므로, 동기 I/O가 포함된 분석 함수가 이벤트 루프를 블로킹하면
서버 전체가 멈춥니다. 무거운 분석 작업은 반드시 `run_in_executor`로 스레드 풀에
위임합니다.

```python
# inbound_bot.py 내부 패턴
loop = asyncio.get_event_loop()
result = await loop.run_in_executor(None, build_stock_snapshot, symbol, market)
```

#### 원칙 4 — Graceful Degradation

API 키 없음, 네트워크 오류, 데이터 없음 — 어떤 상황에서도 서버가 에러 페이지를
반환하지 않고 `None` 또는 빈 섹션으로 부분 결과를 반환합니다. 각 분석 서브모듈은
독립적으로 `try/except`로 보호되어 있고, 실패 시 `log.warning()`만 남기고
기본값을 반환합니다.

### 알림 발송 정책 (advisory_policy.py)

| 조건 | 처리 방식 |
|------|-----------|
| 스코어 ≥ 90 + 직접 증거 | 즉시 발송 (URGENT) |
| 스코어 ≥ 70 | 4H 브리핑에 포함 (ACTION / WATCH) |
| 스코어 < 70 | 무시 또는 4H 브리핑으로 흡수 |

4H 브리핑 8개 섹션 구조:

```
① 시장 온도     — Risk-On/Off + 매크로 수치
② 리스크 노출   — Gross Exposure + KR/US 비중 힌트
③ LONG 후보    — Top 3
④ SHORT 후보   — Top 1
⑤ 수혜주 체인  — 급등 후 tier-2 수혜주
⑥ 모의 P&L    — 포트폴리오 가상 수익률
⑦ 다음 체크포인트
⑧ 면책 문구    — 필수
```

---

## 6. 매집 평가 방법론 (accumulation_detector.py)

### 배경: Wyckoff 이론

Richard Wyckoff(1873~1934)가 정립한 시장 사이클 이론입니다.
세력(Composite Man)이 저가에 매집 → 가격 상승(Markup) → 고가에 분산 → 가격 하락(Markdown)의
4단계를 반복한다는 전제에서, **매집 국면을 조기에 탐지**하는 것이 목표입니다.

### 7구성요소 복합 채점 (0~100점)

각 구성요소를 독립적으로 채점한 후 가중 합산합니다.

#### 구성요소 1 — 가격 위치 (Price Position, 최대 15점)

52주 중 현재 가격이 어느 구간에 있는지 확인합니다.
매집은 저가권에서 일어나므로 52주 하위 30% 이하에 가중치를 줍니다.

| 52주 위치 | 점수 |
|-----------|------|
| ≤ 20% (극저가) | 15점 |
| ≤ 30% | 12점 |
| ≤ 45% | 7점 |
| ≤ 60% | 3점 |
| > 60% | 0점 |

#### 구성요소 2 — 지지선 테스트 (Support Testing, 최대 20점)

`Last Support` = 최근 60일 저점.
현재 가격이 지지선에서 얼마나 가까운지를 측정합니다.

```
지지선 근접도 = (현재가 - 지지선) / 지지선
```

| 근접도 | 의미 | 점수 |
|--------|------|------|
| ≤ 3% | 지지선 위 3% (매집 구간) | 20점 |
| ≤ 7% | 지지선 근접 | 15점 |
| ≤ 15% | 다소 상회 | 8점 |
| > 15% | 지지선과 멀리 떨어짐 | 0점 |

#### 구성요소 3 — 거래량 패턴 (Volume Pattern, 최대 20점)

Wyckoff 매집의 핵심 신호: **하락 시 거래량 감소 + 상승 시 거래량 증가**.

```python
down_days = 가격 하락 일수 (최근 20일)
up_days   = 가격 상승 일수

down_vol_avg = 하락일 평균 거래량
up_vol_avg   = 상승일 평균 거래량

vol_ratio = down_vol_avg / (up_vol_avg + ε)
```

| vol_ratio (하락 거래량 / 상승 거래량) | 해석 | 점수 |
|---------------------------------------|------|------|
| < 0.5 | 하락 시 거래량 절반 이하 → 강한 매집 신호 | 20점 |
| < 0.7 | 하락 거래량 감소 추세 | 14점 |
| < 0.9 | 약한 신호 | 7점 |
| ≥ 0.9 | 신호 없음 | 0점 |

추가: OBV(On-Balance Volume) 20일 선형회귀 기울기가 양수이면 +5점 보너스

#### 구성요소 4 — 매도 소화 (Selling Climax / Absorption, 최대 20점)

큰 하락 후 매도 물량이 소화(흡수)되었는지 판단합니다.

- **Selling Climax 탐지**: 최근 60일 중 `Close < Open` (음봉) + `거래량 > 2×20일 평균` 인 날 존재 여부
- **반등 확인**: Selling Climax 이후 현재 가격이 해당 저점보다 높은지
- **가격 안정화**: 최근 5일 고가 - 저가 범위가 20일 평균 범위의 60% 이하

| 조건 충족 개수 | 점수 |
|---------------|------|
| 3개 모두 | 20점 |
| 2개 | 13점 |
| 1개 | 6점 |
| 0개 | 0점 |

#### 구성요소 5 — 스프링 신호 (Spring, 최대 15점)

Wyckoff의 "Spring": 지지선을 잠깐 하향 돌파 후 바로 반등하는 패턴입니다.
세력이 마지막 손절을 유도해 물량을 취득하는 구간입니다.

```python
최근 60일 중:
  spring 조건 = (당일 저점 < 이전 지지선) AND (당일 종가 > 이전 지지선)
```

| spring 발생 후 경과 | 점수 |
|--------------------|------|
| 5일 이내 | 15점 |
| 10일 이내 | 10점 |
| 20일 이내 | 5점 |
| 없음 | 0점 |

#### 구성요소 6 — 돌파 조짐 (Markup Sign, 최대 5점)

MA20 상방 돌파 후 재테스트 성공 시 +5점.
이는 Wyckoff의 "Sign of Strength(SOS)" 전 단계입니다.

#### 구성요소 7 — 수급 흐름 (Flow Convergence, 최대 5점)

`institutional_flow.py`의 `flow_score`와 연계됩니다:

| flow_score | 추가점 |
|------------|--------|
| ≥ 65 (HIGH) | +5점 |
| ≥ 45 (MEDIUM) | +3점 |
| < 45 (LOW) | 0점 |

### 리스크 패널티

매집 신호가 있어도 다음 조건 시 총점에서 감점합니다:

| 조건 | 패널티 |
|------|--------|
| 1개월 수익률 > +30% (이미 급등) | −15점 |
| RSI > 70 (과열 구간) | −10점 |
| 거래량 5배 이상 폭발 후 거래량 급감 | −10점 |
| Altman Z-Score < 1.81 (부도 위험) | −8점 |
| Piotroski F-Score ≤ 2 (재무 취약) | −5점 |

### 최종 판정

```
accumulation_score = min(max(구성요소 합산 - 패널티, 0), 100)
```

| 점수 | 레벨 | 의미 |
|------|------|------|
| ≥ 70 | HIGH | 매집 가능성 높음 |
| ≥ 45 | MEDIUM | 매집 가능성 중간 |
| < 45 | LOW | 매집 신호 약함 |

> **주의**: 이 점수는 "매집 가능성"이며 "매집 확정"이 아닙니다.
> 공개 데이터 기반 통계적 추정이며 실제 기관 동향과 다를 수 있습니다.

---

## 7. 주식 점수 계산 방법론

종목 분석은 **세 가지 독립 점수**를 병렬로 계산합니다:

| 시스템 | 출력 | 구성 요소 |
|--------|------|-----------|
| 종합 등급 (snap.grade) | ★★★ / ★★ / ★ / — | 기술점수 50% + 가치점수 50% |
| 별점 (star_rating) | ★★★★★ ~ ★☆☆☆☆ | 기술 40% + 가치 30% + 스윙 30% |
| 투자 스코어카드 (tier) | STRONG_WATCH / WATCH / NEUTRAL / AVOID | 5차원 가중 평균 |

---

### 7-1. 기술 점수 (tech_score, 0~40)

일봉·주봉 데이터를 기반으로 아래 신호를 합산합니다:

| 조건 | 점수 |
|------|------|
| RSI < 30 (과매도, 반등 가능성) | +15 |
| RSI 30~70 (중립) | +8 |
| RSI > 70 (과열) | −5 |
| OBV 20봉 선형회귀 기울기 > 0 (수급 유입) | +10 |
| 볼린저밴드% < 0.2 (하단 근접, 지지권) | +8 |
| 거래량 > 2× 20일 평균 (서지) | +7 |

최대 합산: **40점**

---

### 7-2. 가치 점수 (val_score, 0~100)

| 조건 | 점수 |
|------|------|
| PER < 10 | +30 |
| PER 10~20 | +20 |
| PER 20~30 | +10 |
| PBR < 1 | +20 |
| PBR 1~2 | +15 |
| PBR 2~3 | +8 |
| ROE > 20% | +25 |
| ROE 10~20% | +15 |
| ROE 5~10% | +8 |
| 52주 위치 < 30% | +8 |
| 52주 위치 > 85% | −5 |
| 시가총액 중형주 (기관 사각지대) | +5 |

---

### 7-3. 종합 등급

```
total_score = tech_score / 40 × 50 + val_score / 100 × 50
```

| total_score | 등급 |
|-------------|------|
| ≥ 80 | ★★★ |
| ≥ 65 | ★★ |
| ≥ 50 | ★ |
| < 50 | — |

---

### 7-4. 별점 (star_rating)

```
composite = (tech_score / 40 × 100) × 0.40
          + val_score × 0.30
          + swing_score × 0.30
```

`swing_score`는 거래량·OBV·단기 모멘텀 복합 지표입니다.

| composite | 별점 |
|-----------|------|
| ≥ 82 | ★★★★★ |
| ≥ 70 | ★★★★☆ |
| ≥ 55 | ★★★☆☆ |
| ≥ 40 | ★★☆☆☆ |
| < 40 | ★☆☆☆☆ |

---

### 7-5. 투자 스코어카드 (5차원 모델)

단기 공격적 투자 적합도를 5개 차원으로 평가합니다.
각 차원은 기본값 50점에서 출발해 조건에 따라 가산·감산합니다.

| 차원 | 가중치 | 주요 입력값 |
|------|--------|------------|
| 기술 모멘텀 | **25%** | SPY 상대강도(RS 3개월), 52주 위치%, 거래량 서지비율, 52주 신고가 돌파, Short DTC |
| 펀더멘탈 | **20%** | Piotroski F-Score, ROIC, 매출총이익률, 유동비율, 순현금 여부 |
| 성장 가속도 | **25%** | 매출 CAGR 3년, 이익 성장률, EPS 비트율%, 평균 서프라이즈%, 서프라이즈 추세 |
| 실적 신뢰도 | **20%** | Piotroski 통과 항목 수, Altman Z-Score, 기관 보유비율%, Short Float% |
| 밸류에이션 | **10%** | PEG 비율, DCF 업사이드%, FCF 수익률, 애널리스트 목표가 상승여력% |

```
scorecard_total = Σ (각 차원 점수 × 가중치)
```

| scorecard_total | 티어 |
|-----------------|------|
| ≥ 75 | 🔥 STRONG_WATCH |
| ≥ 60 | 👀 WATCH |
| ≥ 45 | ⚖️ NEUTRAL |
| < 45 | ⛔ AVOID |

---

### 7-6. Piotroski F-Score (0~9점)

9개 항목을 각 1점으로 채점하는 재무 우량도 지표입니다:

| 카테고리 | 항목 (조건 충족 시 +1점) |
|----------|------------------------|
| 수익성 (최대 4점) | ROA > 0, 영업현금흐름 > 0, ROA 전년 대비 증가, 발생액(Accrual) < 영업현금흐름 |
| 레버리지 (최대 3점) | 부채비율 감소, 유동비율 증가, 전년 대비 주식 발행 없음 |
| 효율성 (최대 2점) | 매출총이익률 증가, 자산회전율 증가 |

- **8~9점**: 재무 우량 (Strong)
- **5~7점**: 보통 (Average)
- **0~4점**: 재무 취약 (Weak)

---

### 7-7. Altman Z-Score (파산 예측 지수)

```
Z = 1.2 × (유동자산 - 유동부채) / 총자산
  + 1.4 × (이익잉여금 / 총자산)
  + 3.3 × (EBIT / 총자산)
  + 0.6 × (시가총액 / 총부채)
  + 1.0 × (매출 / 총자산)
```

| Z-Score | 판정 |
|---------|------|
| > 2.99 | 안전 (Safe Zone) |
| 1.81 ~ 2.99 | 회색지대 (Grey Zone) |
| < 1.81 | 위험 (Distress Zone) |

제조업 외 기업(금융·SaaS 등)은 Z-Score 적용 한계가 있으므로 참고 지표로만 활용합니다.

---

### 7-8. DCF 내재가치 (2단계 모델)

```
고성장 5년:    Σ EPS × (1 + g)^t / (1 + r)^t   (t = 1..5)
터미널 가치:   EPS₅ × (1 + g_t) / (r - g_t) / (1 + r)^5
내재주가:     고성장 PV + 터미널 PV
```

| 파라미터 | 값 | 출처 |
|----------|-----|------|
| 할인율 r | `Rf + β × ERP` | CAPM: Rf=4.5%, ERP=5.0% |
| 고성장률 g | 애널리스트 컨센서스 또는 실적 CAGR | yfinance / 계산 |
| 터미널 성장률 g_t | 2.5% | 장기 GDP 성장률 가정 |

```
DCF 업사이드 = (내재가치 - 현재가) / 현재가 × 100%
```

---

### 7-9. EPS 서프라이즈

```
서프라이즈% = (실제 EPS - 컨센서스 EPS) / |컨센서스 EPS| × 100
```

- **비트율**: 4분기 중 실제 ≥ 컨센서스 비율 (0~100%)
- **서프라이즈 추세**:
  - 최근 2분기 평균 - 이전 2분기 평균 ≥ +5%p → 가속(↑ Accelerating)
  - ≤ −5%p → 둔화(↓ Decelerating)
  - 그 외 → 안정(→ Stable)

---

### 7-10. 매크로 레짐 (macro_pulse.py)

| 지표 | Risk-On 조건 | Risk-Off 조건 |
|------|-------------|--------------|
| VIX | < 20 | > 30 |
| 10Y 금리 변화 | ±20bp 이내 | +30bp 이상 급등 |
| USD-KRW | 약세 (원화 강세) | 강세 |
| WTI 원유 | 안정적 | 급등 or 급락 |

> 금리 변화는 항상 **bp (베이시스포인트, 0.01% = 1bp)** 단위로 표현합니다.

---

## 8. 데이터 수집 파이프라인

### 아키텍처 원칙

모든 yfinance 호출은 `stock_data_provider.py`를 경유합니다.
동일 종목에 대한 중복 네트워크 요청을 TTL 5분 메모리 캐시로 차단합니다.

```
요청 → stock_data_provider.py (캐시 TTL 5분)
              ↓ 캐시 미스 시만
         yfinance / REST API / pykrx
```

### 데이터 소스 14개

| 소스 | 수집 내용 | API 키 |
|------|----------|--------|
| Yahoo Finance (yfinance) | OHLCV 1년, PER/PBR/ROE, 재무제표, 옵션 체인, 애널리스트 의견 | 불필요 |
| pykrx | KRX 시가총액, 외국인·기관 순매수 | KRX 회원가입 |
| SEC EDGAR | 미국 8-K 공시 원문, 티커 검색 fallback | 불필요 |
| RSS | PR Newswire, BusinessWire 공시 | 불필요 |
| OpenDART | 수주계약, 자사주매입, 실적공시 | 필요 |
| FRED | 금리, 실업률, CPI, M2, PCE | 필요 |
| ECOS | 한국은행 기준금리, 통화량, 환율 | 필요 |
| Finnhub | 뉴스 건수, EPS 실제치 vs 예상치 | 필요 |
| NewsAPI | 영어 뉴스 헤드라인 | 필요 |
| FMP | EV/EBITDA, FCF, 실적 캘린더 | 필요 |
| Naver Open API | 국내 뉴스, 증권사 리포트 링크 | 필요 |
| Telegram 채널 | 증권사 리포트 텍스트 (Telethon MTProto) | 필요 |
| Alpha Vantage | 기술지표 보완 (EMA, MACD) | 필요 |
| EIA | 원유 재고, 생산량 | 필요 |

---

## 9. 대시보드 기능 (8개 탭)

`http://localhost:8765` 접속 후 상단 탭으로 이동합니다.

### 홈 / 워치리스트
- 177종목 실시간 주가·등락률 표시
- RSI, 볼린저밴드%, 거래량비율 기반 간이 등급 표시

### 스크리너
- 전체 177종목 병렬 스캔 (약 30~60초 소요)
- 종합 점수 기준 정렬 — ★★★ / ★★ / ★ / 중립 등급
- 섹터·시가총액·RSI 범위 필터

### 종목 분석 (`/분석`)
한글명, 티커, 종목코드 모두 입력 가능. 출력 내용:

1. 기술적 분석 — RSI, OBV, 볼린저밴드, 거래량
2. 펀더멘탈 — PER, PBR, ROE, 52주 위치
3. 재무 품질 — Piotroski F-Score, Altman Z-Score, ROIC, 매출 CAGR
4. DCF 내재가치 — 2단계 성장 모델, CAPM 할인율
5. EPS 서프라이즈 — 4분기 비트율·트렌드
6. 투자 스코어카드 — 5차원 종합 점수 + 티어 판정
7. 매집 분석 — Wyckoff 7구성요소 점수 + 레벨
8. 기관/외국인 수급 — KRX 순매수 or OBV proxy
9. TradingView 차트 링크

### 4H 브리핑
- KR / US 시장별 4시간 단위 매크로 + 섹터 리포트
- 터미널 미리보기: `uv run tele-quant briefing --market KR --no-send`

### 텔레그램 설정
- 봇 토큰·채팅 ID 브라우저에서 직접 설정·저장
- 테스트 메시지 발송 확인

### 4H 스케줄러
- 자동 브리핑 발송 주기 설정
- KR/US 시장별 독립 스케줄 설정

### 데이터 소스
- API 키 활성화/비활성화 상태 시각화

### Ollama AI
- 로컬 LLM 모델 설정 (기본: `qwen3:8b`)
- 뉴스 감성 심화 분석, 브리핑 자연어 다듬기

---

## 10. 기술 스택

| 항목 | 기술 | 비고 |
|------|------|------|
| 언어 | Python 3.11+ | type hints 필수 |
| 패키지 관리 | uv (Astral, Rust 기반) | pip 대비 10~100배 빠름 |
| 웹 프레임워크 | FastAPI + Uvicorn | 비동기 ASGI |
| 설정 관리 | Pydantic Settings | .env.local 자동 파싱 |
| 데이터베이스 | SQLite + aiosqlite | 서버리스, 파일 1개 |
| 주가 데이터 | yfinance | TTL 5분 캐시 필수 |
| KRX 데이터 | pykrx 1.2.8+ | stdout 리다이렉트 필요 |
| 텔레그램 발신 | python-telegram-bot | 봇 API |
| 텔레그램 수집 | Telethon (MTProto) | 사용자 API 필요 |
| 스케줄링 | APScheduler (in-process) | systemd timer 보조 (WSL) |
| 린트 | ruff | Black + isort + flake8 대체 |
| 테스트 | pytest | 2,477개 (2026-05-22 기준) |
| 프론트엔드 | 순수 HTML/CSS/Vanilla JS | 외부 프레임워크 없음 |
| 실행 환경 | Windows 10/11 + WSL2 Ubuntu | 포트 8765 |

---

## 11. 트러블슈팅

### 실행.bat 더블클릭해도 아무것도 안 뜸

프로젝트 경로에 한글·공백이 포함된 경우, CMD 로그 파일 리다이렉션이 실패할 수 있습니다.
`실행.bat`은 이 문제를 따옴표 처리로 해결했습니다. 그래도 안 된다면:

1. `run_dashboard.bat`을 대신 사용해보세요.
2. `.setup_done` 파일이 있는지 확인하세요 (없으면 setup이 먼저 실행됩니다).

### yfinance 401 에러 / "possibly delisted" 경고

대시보드 실행 시 로그에 `HTTP Error 401: Invalid Crumb` 또는 `possibly delisted` 메시지가 보일 수 있습니다.
이는 yfinance 세션 초기화 전 병렬 요청으로 인한 것으로 **기능에 영향을 주지 않습니다**.
로그 필터(`_SuppressYFNoise`)가 적용되어 있어 대부분 숨겨집니다.

### KRX 로그인 실패

`.env.local`에 `KRX_ID`와 `KRX_PW`가 정확히 입력되어 있는지 확인합니다.
미설정 시 기관/외국인 수급 섹션이 공란으로 표시되며, 나머지 분석은 정상 동작합니다.

### pykrx "Error occurred in ..." 에러가 로그에 찍힘

pykrx는 내부적으로 `print()`로 오류를 출력합니다 (Python logging 미사용).
이 프로젝트는 `contextlib.redirect_stdout`으로 해당 출력을 억제합니다.
억제가 안 된다면 pykrx 버전을 확인하세요 (`uv run pip show pykrx`).

### "사이트에 연결할 수 없음"

1. `실행.bat` 창이 열려 있는지 확인 (서버 실행 중이어야 함)
2. 브라우저에서 직접 입력: `http://localhost:8765`
3. WSL IP 확인: WSL 터미널에서 `hostname -I`
4. 포트 충돌: `fuser -k 8765/tcp` (WSL 터미널)

### setup.bat을 재실행하고 싶을 때

프로젝트 폴더에서 `.setup_done` 파일을 삭제한 후 `setup.bat`을 다시 실행합니다.

### 테스트 실행

```bash
uv run ruff check .          # 린트 검사
uv run pytest -q             # 전체 테스트
uv run tele-quant ops-doctor # 시스템 진단
```

---

## 12. 개발자·학부생 Q&A 30선

### 아키텍처·설계

**Q1. 왜 yfinance를 직접 호출하지 않고 `stock_data_provider.py`를 거칩니까?**

A. 스크리너가 177종목을 동시에 분석할 때, 동일 종목(예: SPY)이 여러 분석 모듈에서
각각 yfinance를 호출하면 수백 번의 중복 네트워크 요청이 발생합니다. TTL 5분 메모리
캐시를 단일 파일에 집중시키면 첫 번째 요청 후 캐시에서 즉시 반환하므로 응답 속도가
수 초에서 수백 ms로 줄어듭니다.

**Q2. FastAPI 서버가 단일 파일(`dashboard/app.py`)에 HTML까지 인라인으로 있는 이유는?**

A. 배포 단순화가 목적입니다. 별도의 정적 파일 서버, npm 빌드 파이프라인, CDN 없이
Python 서버 하나만 실행하면 전체 대시보드가 동작합니다.
학습·개인 프로젝트 규모에서는 이 패턴이 오버엔지니어링을 피하는 현실적인 선택입니다.

**Q3. `run_in_executor`를 왜 사용합니까?**

A. FastAPI는 asyncio 기반 서버로, 이벤트 루프 스레드에서 블로킹 I/O(yfinance 네트워크 호출 등)를
실행하면 그 시간 동안 다른 모든 요청이 멈춥니다. `loop.run_in_executor(None, func)`는
블로킹 작업을 별도 스레드 풀에서 실행하고 await으로 결과를 기다리므로,
메인 이벤트 루프가 다른 요청을 계속 처리할 수 있습니다.

**Q4. `pydantic-settings`를 직접 `os.environ`보다 선호하는 이유는?**

A. `.env.local` 파일 자동 파싱, 타입 변환(문자열 → int/bool/list), 필수값 누락 시
명시적 에러 등 보일러플레이트 코드를 제거합니다. `Settings()` 객체 하나에서
전 모듈이 동일한 설정 인스턴스를 참조하므로 테스트 시 한 곳에서 override가 가능합니다.

**Q5. SQLite를 왜 사용합니까? PostgreSQL 같은 서버 DB는요?**

A. 개인 로컬 운용 툴이므로 동시 접속자가 1명(본인)입니다. SQLite는 서버 설치·운영
비용이 없고 파일 하나로 백업·이동이 가능합니다. 읽기 집중 워크로드에서 SQLite의
성능은 대부분의 개인 사용 케이스에서 충분합니다.

---

### 분석·금융 로직

**Q6. Piotroski F-Score는 어떤 상황에서 가장 유용합니까?**

A. 가치주(저PER·저PBR) 스크리닝에서 재무 함정(Value Trap)을 피하는 데 효과적입니다.
PER이 낮아도 재무가 악화 중인 기업은 F-Score가 낮게 나옵니다.
반대로 F-Score ≥ 8인 저PBR 주는 역사적으로 시장 대비 초과 수익률을 보이는 연구가 있습니다.
단, 금융주·신생 기업(적자 성장주)에는 직접 적용이 부적합합니다.

**Q7. Altman Z-Score가 비제조업에 맞지 않는 이유는?**

A. 원래 1968년에 제조업체를 기반으로 회귀 분석해 만든 공식이라 자산회전율, 부채비율 등의
가중치가 제조업 재무구조를 전제합니다. 소프트웨어 회사(고마진·저자산), 금융회사(레버리지가
본업)에 그대로 적용하면 오진이 잦습니다. 이 프로젝트에서는 참고 지표로만 활용하고
섹터별 수정 계수를 검토 중입니다.

**Q8. DCF에서 CAPM 할인율을 왜 `4.5% + β × 5%`로 설정했습니까?**

A. 2025~2026년 기준 미국 10년물 국채 금리(위험무이자율 Rf)가 4~5% 수준이므로
중간값 4.5%를 사용합니다. ERP(Equity Risk Premium)는 Damodaran의 장기 역사적 ERP
추정치인 5%를 채용했습니다. β × ERP는 개별 종목의 시장 대비 위험 프리미엄입니다.
금리가 크게 변하면 `.env.local`에서 조정 가능하도록 설계할 예정입니다.

**Q9. EPS 서프라이즈 "비트율"이 100%라도 주가가 안 오르는 경우가 있는 이유는?**

A. EPS가 컨센서스를 초과해도 "Buy the rumor, Sell the news" 효과로 이미 선반영된 경우
주가가 하락합니다. 또한 컨센서스 자체가 낮게 조정된 경우(Beat 조작, Guidance 게임)
실질적 어닝 파워 개선이 없을 수 있습니다. 이 프로젝트는 서프라이즈% 절댓값과
트렌드를 함께 보는 이유가 여기에 있습니다.

**Q10. VIX가 몇 이상이면 Risk-Off로 판정합니까?**

A. 30 이상이면 Risk-Off 레짐으로 판정합니다. VIX 20 미만은 Risk-On입니다.
20~30 구간은 다른 지표(금리 변화, USD 강도)를 함께 고려해 Neutral 또는
Risk-Off로 세분화합니다. 금리 변화는 **bp(베이시스포인트)** 단위로 측정하며,
30bp 이상 급등 시 Risk-Off 가중치를 추가합니다.

**Q11. Wyckoff Spring이 탐지되면 즉시 매수해야 합니까?**

A. 아닙니다. Spring 탐지는 "가능성 신호"이며, 이후 확인(Sign of Strength: 거래량을
동반한 지지선 돌파)이 나오지 않으면 false spring(진짜 하락 시작)일 수 있습니다.
이 시스템은 Spring 신호를 MEDIUM~HIGH 가능성으로 표현하며, 최종 결정은 사용자 판단입니다.

**Q12. OBV(On-Balance Volume)란 무엇이며 왜 사용합니까?**

A. OBV는 주가 상승일에 거래량을 더하고 하락일에 빼는 누적 지표입니다.
주가보다 먼저 수급 방향을 반영하는 경우가 많아 선행 지표로 활용됩니다.
이 프로젝트에서는 OBV의 20일 선형회귀 기울기가 양수이면 수급 유입, 음수이면
수급 이탈로 판단하고 기술 점수에 반영합니다.

**Q13. Short DTC(Days to Cover)는 어떻게 계산합니까?**

A. `Short DTC = 공매도 잔량(주) / 일평균 거래량(주)`.
이 값이 클수록 공매도 세력이 환매수에 더 많은 시간이 걸립니다.
DTC가 높은 종목이 급등할 경우 공매도 강제 청산(Short Squeeze)이 발생해
가속 상승할 수 있습니다. 이 시스템은 DTC > 10일 이상일 때 스코어카드에 가점을 줍니다.

**Q14. 왜 매집 점수에 리스크 패널티를 추가합니까?**

A. 급등 후(1개월 +30% 이상) 나타나는 매집 신호는 진짜 매집이 아니라 추격 매수
또는 분산의 초기 단계일 가능성이 높습니다. RSI > 70은 이미 과열 상태를 의미하며,
Altman Z < 1.81 기업은 부도 위험이 있어 아무리 기술 신호가 좋아도 신뢰도가
낮습니다. 패널티 시스템은 "좋아 보이는 함정"을 걸러냅니다.

---

### 데이터·API

**Q15. yfinance 데이터가 실제 거래소 데이터와 다른 경우가 있습니까?**

A. 있습니다. yfinance는 Yahoo Finance 공개 데이터를 파싱하며, 분할(Split)·배당 조정가,
일부 KR 종목 거래량 단위(100주 vs 1주), 상장폐지·변경 종목 데이터 오류 등이
발생합니다. 이 프로젝트는 `stock_data_provider.py`에서 이상치 필터링과
fallback 로직을 추가해 신뢰성을 높이고 있습니다.

**Q16. DART API는 왜 발급에 1~2일이 걸립니까?**

A. 금융감독원 시스템으로 담당자가 신청을 검토 후 승인하는 절차가 있습니다.
자동 발급이 아닌 수동 심사 방식입니다.
DART 없이도 yfinance로 KR 기본 분석은 가능하며, DART가 있으면 수주계약·
자사주매입 같은 공시 이벤트 탐지가 추가됩니다.

**Q17. pykrx가 print()로 에러를 출력하는 이유는 무엇이며 어떻게 처리합니까?**

A. pykrx는 내부 유틸리티에서 Python `logging` 대신 `print()`를 사용합니다.
logging 필터로는 차단이 불가능합니다. 이 프로젝트는 pykrx import와 API 호출 모두를
`contextlib.redirect_stdout(io.StringIO())`로 감싸서 stdout 출력을 
가상 버퍼로 흡수합니다.

**Q18. SEC EDGAR fallback은 언제 발동됩니까?**

A. `ticker_resolver.py`에서 yfinance 조회 시 가격도 없고 사명도 없으면,
SEC EDGAR 공개 검색 API에 해당 티커를 질의해 현재 유효한 티커를 찾습니다.
주로 티커가 변경된 경우(합병·분사·이름 변경)에 사용됩니다. 3초 타임아웃으로
실패 시 None을 반환합니다.

**Q19. TTL 캐시를 5분으로 설정한 이유는?**

A. 주식 데이터는 실시간 트레이딩에 쓰이는 게 아니라 리서치·브리핑 목적입니다.
5분 내 동일 종목 재분석 요청은 대부분 동일한 데이터를 필요로 합니다.
5분 이상이면 스크리너 → 상세 분석 전환 시 데이터가 너무 오래됩니다.
5분 미만이면 자주 갱신으로 API 과부하가 발생합니다.

**Q20. Finnhub EPS 데이터와 yfinance EPS 데이터 중 어느 것이 더 정확합니까?**

A. Finnhub가 일반적으로 더 신뢰성이 높습니다. yfinance의 EPS 데이터는
Yahoo Finance 스크래핑 결과로 가끔 누락·오류가 있습니다. 이 프로젝트는
Finnhub를 우선 사용하고, 키가 없으면 yfinance로 fallback합니다.

---

### 코딩·테스트

**Q21. 테스트에서 yfinance를 어떻게 모킹합니까?**

A. `yfinance.Ticker`를 직접 모킹하면 `stock_data_provider`의 캐시 레이어가
이미 채워져 있을 때 적용이 안 됩니다. 따라서 `stock_data_provider.get_ticker_info`
같은 함수를 직접 patch합니다:

```python
from unittest.mock import patch

with patch("tele_quant.stock_data_provider.get_income_stmt", return_value=mock_df):
    result = compute_piotroski("AAPL")
```

**Q22. `ruff check .`을 통과하지 못하는 흔한 케이스는?**

A. (1) import 순서 불일치(I001) — stdlib → third-party → local 순 위반,
(2) 미사용 import(F401), (3) 타입 어노테이션 없는 함수(ANN001, 프로젝트 설정에 따라 다름),
(4) f-string에서 불필요한 따옴표 이중화(Q000). `uv run ruff check --fix .`로
자동 수정 가능한 항목은 한 번에 처리됩니다.

**Q23. 왜 `dataclass`를 사용하고 `TypedDict`는 사용하지 않습니까?**

A. `dataclass`는 기본값, `__post_init__` 검증, 직렬화 편의 메서드를 제공합니다.
분석 결과 객체(`StockSnapshot`, `InstitutionalFlowSignal` 등)는 단순 딕셔너리보다
IDE 자동완성·타입체크가 명확합니다. `TypedDict`는 읽기 전용 구조에 더 적합하고
인스턴스 메서드가 없습니다.

**Q24. 비동기(async)와 동기(sync) 코드가 섞여 있는 구조적 이유는?**

A. yfinance·pykrx·대부분의 REST 클라이언트가 동기 블로킹 함수입니다.
이를 async로 바꾸려면 `httpx.AsyncClient` 기반으로 완전 재작성이 필요합니다.
현실적 타협으로, FastAPI 라우터는 async이고 무거운 분석은 `run_in_executor`로
스레드 풀에 위임합니다. 순수 async I/O보다는 느리지만 기존 라이브러리 생태계를
그대로 활용할 수 있습니다.

**Q25. `lru_cache`와 TTL 5분 캐시의 차이는?**

A. `lru_cache`는 TTL(만료) 개념이 없어 서버가 실행되는 동안 영구히 캐시합니다.
`_safe_name_sector(sym)` 같이 거의 변하지 않는 회사명·섹터 조회에 사용합니다.
주가·재무 데이터처럼 시간이 지나면 변하는 데이터는 TTL이 있는 커스텀 캐시를
`stock_data_provider.py`에서 구현해 사용합니다.

---

### 운영·환경

**Q26. WSL2에서 Windows 브라우저가 `localhost:8765`에 접속되는 원리는?**

A. WSL2는 Linux VM이지만 Windows Hyper-V 가상 네트워크 어댑터를 통해
`localhost`가 WSL2 내부 IP로 자동 포워딩됩니다 (Windows 11 기본 설정).
FastAPI는 `0.0.0.0:8765`에 바인딩하므로 WSL2 어댑터의 모든 인터페이스에서
수신합니다. Windows 방화벽이 막는 경우 수동 포트 포워딩 설정이 필요합니다.

**Q27. `.env.local`이 Git에 포함되면 안 되는 이유는?**

A. 텔레그램 봇 토큰, KRX 비밀번호, 각종 API 키가 담겨 있습니다.
GitHub에 한 번 push되면 크롤러가 수집해 수 분 내에 악용될 수 있습니다.
`.gitignore`에 `.env.local`이 반드시 포함되어 있어야 하며,
이 프로젝트는 setup.bat이 `.env.local`을 생성하므로 절대 커밋하지 마세요.

**Q28. systemd timer와 APScheduler 중 어느 것을 사용합니까?**

A. 둘 다 사용합니다. WSL2 내에서 `systemd --user` 타이머(45개 유닛)가
4시간 브리핑·데이터 수집 등을 스케줄합니다. 대시보드가 실행 중일 때는
APScheduler(in-process)가 동일한 작업을 수행합니다.
대시보드 없이 백그라운드 운용 시 systemd 타이머만으로도 동작합니다.

**Q29. uv를 pip/poetry 대신 사용하는 이유는?**

A. Rust로 작성되어 패키지 설치 속도가 pip 대비 10~100배 빠릅니다.
`pyproject.toml` 표준을 지원하고 가상환경 관리·잠금 파일 생성을
단일 도구로 처리합니다. `uv run`으로 가상환경 활성화 없이 명령 실행이
가능해 배치 파일 작성이 간단해집니다.

**Q30. 이 프로젝트를 리눅스 서버(VPS)에 배포할 수 있습니까?**

A. 가능합니다. WSL2 전용 기능(배치 파일, Windows 경로 변환)을 제외하면
순수 Python 프로젝트이므로 Ubuntu/Debian 서버에서 `uv sync && uv run tele-quant dashboard`
명령으로 실행됩니다. Telegram 수신봇과 4H 브리핑은 서버에서 24시간 운용하기에
더 적합합니다. pykrx의 KRX_ID/KRX_PW 환경변수만 동일하게 설정하면 됩니다.

---

## 13. 라이선스 및 면책

이 소프트웨어는 공개 데이터 기반 **개인 리서치 보조 도구**입니다.

- 매수·매도 추천이 아닙니다.
- 과거 데이터 기반 분석이며 미래 수익을 보장하지 않습니다.
- 투자 판단의 최종 책임은 사용자에게 있습니다.
- 실계좌 자동 매매 기능은 포함되어 있지 않습니다.
- 각 외부 API의 이용약관을 준수하여 사용하세요.
