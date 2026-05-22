# Tele Quant — 한국·미국 주식 AI 분석 대시보드

한국(KRX/KOSDAQ) 및 미국 주식을 대상으로 기술적·펀더멘탈·모멘텀·DCF·EPS 서프라이즈 분석을 통합 제공하는
로컬 웹 대시보드입니다. Windows 10/11 + WSL2 환경에서 동작하며,
브라우저 하나로 전 기능을 사용할 수 있습니다.

---

## 목차

1. [프로젝트 개요 · 분석 대상 종목](#1-프로젝트-개요--분석-대상-종목)
2. [빠른 시작 (Windows 10/11)](#2-빠른-시작-windows-1011)
3. [환경변수 설정](#3-환경변수-설정)
4. [대시보드 기능 (8개 탭)](#4-대시보드-기능-8개-탭)
5. [데이터 수집 방법](#5-데이터-수집-방법)
6. [점수 계산 방법론](#6-점수-계산-방법론)
7. [백엔드 아키텍처](#7-백엔드-아키텍처)
8. [프론트엔드 구조](#8-프론트엔드-구조)
9. [기술 스택](#9-기술-스택)
10. [트러블슈팅](#10-트러블슈팅)
11. [라이선스 및 면책](#11-라이선스-및-면책)

---

## 1. 프로젝트 개요 · 분석 대상 종목

### 무엇을 하는 프로그램인가

한국·미국 주식에 대해 4시간 단위로 아래 분석을 자동 수행합니다:

- **기술적 분석**: RSI, OBV, 볼린저밴드, 거래량 서지
- **펀더멘탈 분석**: PER, PBR, ROE + 심화 18개 지표
- **재무 품질**: Piotroski F-Score, Altman Z-Score, ROIC, 매출 CAGR
- **DCF 내재가치**: 2단계 성장 모델 (CAPM 할인율)
- **EPS 서프라이즈**: 최근 4분기 비트율·서프라이즈 크기·추세
- **모멘텀**: SPY 상대강도, 52주 돌파, Short Float, 수급 방향
- **매크로 레짐**: VIX, 10Y 금리, USD, WTI 조합으로 Risk-On/Off 판정

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

GitHub에서 ZIP으로 다운로드 후 압축 해제하거나, WSL Ubuntu 터미널에서 git clone:

```bash
git clone https://github.com/runkwanni21-hash/est_quant
```

### Step 3 — setup.bat 실행

압축 해제한 폴더에서 `setup.bat`을 더블클릭합니다.

자동으로 진행되는 작업:

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

- **키 없이도** yfinance 기반 분석(기술·펀더멘탈·재무품질·DCF·EPS)은 **전부 동작**합니다.
- 텔레그램 알림을 원할 경우 `TELEGRAM_BOT_TOKEN`, `TELEGRAM_BOT_TARGET_CHAT_ID` 입력.
- 자세한 항목은 [3. 환경변수 설정](#3-환경변수-설정) 참조.

### Step 5 — 대시보드 실행

`run_dashboard.bat`을 더블클릭하면:

1. WSL에서 FastAPI 서버가 포트 8765에서 시작됩니다.
2. 8초 후 브라우저에서 `http://localhost:8765`가 자동으로 열립니다.
3. 창을 닫거나 `Ctrl+C`를 누르면 서버가 종료됩니다.

---

## 3. 환경변수 설정

`.env.local` 파일에서 설정합니다. `[선택]` 항목은 없어도 기본 기능이 동작합니다.

### 대시보드 접근 제어

| 변수 | 필수 | 설명 |
|------|------|------|
| `DASHBOARD_MASTER_KEY` | 선택 | 소유자용 키, 세션 만료 없음. 미설정 시 인증 없이 접근 |
| `DASHBOARD_PASSWORD` | 선택 | 일반 사용자용 비밀번호, 24시간 세션 |

### 텔레그램 발신 봇

| 변수 | 필수 | 설명 | 발급 |
|------|------|------|------|
| `TELEGRAM_BOT_TOKEN` | 선택 | 4H 브리핑·급등 알림 발송 봇 | [BotFather](https://t.me/BotFather) → `/newbot` |
| `TELEGRAM_BOT_TARGET_CHAT_ID` | 선택 | 알림 수신 채팅 ID | [@userinfobot](https://t.me/userinfobot) |

### 텔레그램 사용자 API (증권사 채널 수집)

| 변수 | 필수 | 설명 | 발급 |
|------|------|------|------|
| `TELEGRAM_API_ID` | 선택 | Telegram 앱 ID (숫자) | [my.telegram.org/apps](https://my.telegram.org/apps) |
| `TELEGRAM_API_HASH` | 선택 | Telegram 앱 Hash (32자리) | 동일 |
| `TELEGRAM_PHONE` | 선택 | 로그인 전화번호 (+8210...) | 동일 |

### 데이터 소스 API 키

| 변수 | 활성화 기능 | 발급 |
|------|------------|------|
| `FINNHUB_API_KEY` | 미국 기업 뉴스 건수 + EPS 서프라이즈 | [finnhub.io](https://finnhub.io) (무료 즉시) |
| `OPENDART_API_KEY` | 한국 전자공시 (수주/자사주/실적) | [opendart.fss.or.kr](https://opendart.fss.or.kr) (1~2일) |
| `NAVER_CLIENT_ID` / `NAVER_CLIENT_SECRET` | 국내 뉴스·증권 리포트 링크 | [developers.naver.com](https://developers.naver.com) |
| `FRED_API_KEY` | 미국 연준 매크로 (금리·실업률·CPI) | [fred.stlouisfed.org](https://fred.stlouisfed.org/docs/api) (무료) |
| `ECOS_API_KEY` | 한국은행 통계 (기준금리·환율·M2) | [ecos.bok.or.kr](https://ecos.bok.or.kr) (무료) |
| `ALPHAVANTAGE_API_KEY` | 기술지표 보완 (EMA, MACD) | [alphavantage.co](https://www.alphavantage.co/support/#api-key) (무료) |
| `NEWSAPI_KEY` | 영어 뉴스 헤드라인 | [newsapi.org](https://newsapi.org/register) (무료 100req/일) |
| `FMP_API_KEY` | EV/EBITDA, FCF, 실적 캘린더 | [financialmodelingprep.com](https://site.financialmodelingprep.com) |
| `OLLAMA_HOST` | 로컬 AI 모델 연동 (없으면 규칙 기반) | [ollama.com](https://ollama.com) 로컬 설치 |

---

## 4. 대시보드 기능 (8개 탭)

`http://localhost:8765` 접속 후 상단 탭으로 이동합니다.

### 홈 / 워치리스트

- 177종목 실시간 주가·등락률 표시
- RSI, 볼린저밴드%, 거래량비율 기반 간이 등급 표시
- 관심 종목 즐겨찾기

### 스크리너

- 전체 177종목 병렬 스캔 (약 30초 소요)
- 종합 점수 기준 정렬 — ★★★ / ★★ / ★ / 중립 등급
- 섹터·시가총액·RSI 범위 필터

### 종목 분석 (`/분석`)

한글명, 티커, 종목코드 모두 입력 가능. 출력 내용:

1. 기술적 분석 — RSI, OBV, 볼린저밴드, 거래량
2. 펀더멘탈 — PER, PBR, ROE, 52주 위치
3. 재무 품질 — Piotroski F-Score, Altman Z-Score, ROIC, 매출 CAGR
4. DCF 내재가치 — 2단계 성장 모델
5. EPS 서프라이즈 — 4분기 비트율·트렌드
6. 투자 스코어카드 — 5차원 종합 점수 + 티어 판정
7. TradingView 차트 링크

### 4H 브리핑

- KR / US 시장별 4시간 단위 매크로 + 섹터 리포트
- 8개 섹션: 시장온도 → 리스크노출 → LONG 후보 Top3 → SHORT/회피 후보 → 수혜주 체인 → 모의포트폴리오 P&L → 다음 체크포인트 → 면책고지
- 터미널 미리보기: `uv run tele-quant briefing --market KR --no-send`

### 텔레그램 설정

- 봇 토큰·채팅 ID 브라우저에서 직접 설정·저장
- 테스트 메시지 발송 확인

### 4H 스케줄러

- 자동 브리핑 발송 주기 설정 (4시간 기본)
- KR/US 시장별 독립 스케줄 설정
- 다음 발송 예정 시간 표시

### 데이터 소스

- API 키 활성화/비활성화 상태 시각화
- API 응답 상태 실시간 확인

### Ollama AI

- 로컬 LLM 모델 설정 (기본: `qwen3:8b`)
- 뉴스 감성 심화 분석, 브리핑 자연어 다듬기

---

## 5. 데이터 수집 방법

### 아키텍처 원칙

모든 yfinance 호출은 `stock_data_provider.py`를 경유합니다.
동일 종목에 대한 중복 네트워크 요청을 TTL 5분 메모리 캐시로 차단합니다.

```
요청 → stock_data_provider.py (캐시 TTL 5분)
              ↓ 캐시 미스 시만
         yfinance / REST API / 파싱
```

### 데이터 소스 14개

| 소스 | 수집 내용 | 방식 | API 키 |
|------|----------|------|--------|
| Yahoo Finance (yfinance) | OHLCV 1년, PER/PBR/ROE, 재무제표, 애널리스트 의견, 옵션 체인 | Python 라이브러리 | 불필요 |
| pykrx | KRX 시가총액, 외국인·기관 순매수 | Python 라이브러리 | 불필요 |
| SEC EDGAR | 미국 8-K 공시 원문 파싱, 티커 검색 fallback | REST API | 불필요 |
| RSS | PR Newswire, Globe Newswire, BusinessWire | RSS 파싱 | 불필요 |
| OpenDART | 수주계약, 자사주매입, 실적공시 | REST API | 필요 |
| FRED | 금리, 실업률, CPI, M2, PCE | REST API | 필요 |
| ECOS | 한국은행 기준금리, 통화량, 환율 | REST API | 필요 |
| Finnhub | 뉴스 건수, EPS 실제치 vs 예상치 | REST API | 필요 |
| NewsAPI | 영어 뉴스 헤드라인 | REST API | 필요 |
| FMP | EV/EBITDA, FCF, 실적 캘린더 | REST API | 필요 |
| Naver Open API | 국내 뉴스, 증권사 리포트 링크 | REST API | 필요 |
| Telegram 채널 | 증권사 리포트 텍스트 자동 수집 | Telethon (MTProto) | 필요 |
| Alpha Vantage | 기술지표 보완 (EMA, MACD) | REST API | 필요 |
| EIA | 원유 재고, 생산량 | REST API | 필요 |

---

## 6. 점수 계산 방법론

종목 분석은 **세 가지 독립 점수**를 병렬로 계산합니다:

| 시스템 | 출력 | 구성 요소 |
|--------|------|-----------|
| 종합 등급 (snap.grade) | ★★★ / ★★ / ★ / — | 기술점수 50% + 가치점수 50% |
| 별점 (star_rating) | ★★★★★ ~ ★☆☆☆☆ | 기술 40% + 가치 30% + 스윙 30% |
| 투자 스코어카드 (tier) | STRONG_WATCH / WATCH / NEUTRAL / AVOID | 5차원 가중 평균 |

---

### 6-1. 기술 점수 (tech_score, 0~40)

4시간봉 데이터를 기반으로 아래 신호를 합산합니다:

| 조건 | 점수 |
|------|------|
| RSI < 30 (과매도, LONG 진입 유리) | +15 |
| RSI 30~70 (중립) | +8 |
| RSI > 70 (과열, LONG 유의) | −5 |
| OBV 20봉 선형회귀 상승 (수급 유입) | +10 |
| 볼린저밴드% < 0.2 (하단 근접, 지지권) | +8 |
| 거래량 서지 > 2x 20일 평균 | +7 |

최대 합산: **40점** (RSI 15 + OBV 10 + 볼린저 8 + 거래량 7)

---

### 6-2. 가치 점수 (val_score, 0~100)

펀더멘탈 지표를 섹터 벤치마크와 비교하여 가산합니다:

**PER (주가수익비율)**

| PER 범위 | 점수 |
|----------|------|
| < 10 | +30 |
| 10~20 | +20 |
| 20~30 | +10 |
| > 30 | 0 |

**PBR (주가순자산비율)**

| PBR 범위 | 점수 |
|----------|------|
| < 1 | +20 |
| 1~2 | +15 |
| 2~3 | +8 |
| > 3 | 0 |

**ROE (자기자본이익률)**

| ROE 범위 | 점수 |
|----------|------|
| > 20% | +25 |
| 10~20% | +15 |
| 5~10% | +8 |
| < 5% | 0 |

**기타 가산**

| 조건 | 점수 |
|------|------|
| 52주 위치 < 30% (저가 구간) | +8 |
| 52주 위치 > 85% (고가 구간) | −5 |
| 시가총액 기관 사각지대 (중형주) | +5 |

---

### 6-3. 종합 등급 (total_score → snap.grade)

```
total_score = min( tech_score/40 × 50 + val_score/100 × 50 , 100 )
```

기술 점수와 가치 점수를 각각 0~50점으로 정규화 후 합산합니다.

| total_score | 등급 | 의미 |
|-------------|------|------|
| ≥ 80 | ★★★ | 강력 관찰 |
| ≥ 65 | ★★  | 관찰 |
| ≥ 50 | ★   | 약한 관찰 |
| < 50 | —   | 중립/회피 |

---

### 6-4. 별점 (star_rating, ★☆☆☆☆ ~ ★★★★★)

스윙 점수(거래량·OBV·단기 모멘텀 복합)를 추가로 반영합니다:

```
composite = tech_norm × 0.40 + val_score × 0.30 + swing_score × 0.30

tech_norm = tech_score / 40 × 100   (0~100 정규화)
```

| composite | 별점 |
|-----------|------|
| ≥ 82 | ★★★★★ |
| ≥ 70 | ★★★★☆ |
| ≥ 55 | ★★★☆☆ |
| ≥ 40 | ★★☆☆☆ |
| < 40 | ★☆☆☆☆ |

각 차원의 알파벳 등급(A/B/C/기준미달)도 함께 출력됩니다. 예: `기술:B / 펀더:A / 스윙:C`

---

### 6-5. 투자 스코어카드 (5차원 모델)

단기 공격적 투자 적합도를 5개 차원으로 평가합니다.
각 차원은 기본값 50점에서 시작하며 조건에 따라 가산·감산됩니다.

| 차원 | 가중치 | 주요 입력값 |
|------|--------|------------|
| 기술 모멘텀 | 25% | SPY 상대강도(RS 3개월), 52주 위치%, 거래량 서지비율, 52주 돌파 여부, Short DTC |
| 펀더멘탈 | 20% | Piotroski F-Score, ROIC, 매출총이익률, 유동비율, 순현금 여부 |
| 성장 가속도 | 25% | 매출 CAGR 3년, 이익 성장률, EPS 비트율%, 평균 서프라이즈%, 서프라이즈 트렌드 |
| 실적 신뢰도 | 20% | Piotroski 통과 항목 수, Altman Z-Score, 기관 보유비율%, Short Float% |
| 밸류에이션 | 10% | PEG 비율, DCF 업사이드%, FCF 수익률, 애널리스트 목표가 상승여력% |

```
scorecard_total = Σ (차원점수 × 가중치)
```

| scorecard_total | 티어 | 의미 |
|-----------------|------|------|
| ≥ 75 | 🔥 STRONG_WATCH | 강력 관찰 대상 |
| ≥ 60 | 👀 WATCH | 관찰 대상 |
| ≥ 45 | ⚖️ NEUTRAL | 중립 |
| < 45 | ⛔ AVOID | 회피 |

---

### 6-6. 재무 품질 지표

**Piotroski F-Score (0~9)**

9개 항목을 각 1점으로 채점합니다:

| 카테고리 | 항목 |
|----------|------|
| 수익성 (4점) | ROA 양수, 영업현금흐름 양수, ROA 전년 대비 증가, 발생액 < 영업현금흐름 |
| 레버리지 (3점) | 부채비율 감소, 유동비율 증가, 신규 주식 발행 없음 |
| 효율성 (2점) | 매출총이익률 증가, 자산회전율 증가 |

점수 해석: 8~9 우량 / 5~7 보통 / 0~4 취약

**Altman Z-Score**

```
Z = 1.2×(유동자산-유동부채)/총자산
  + 1.4×(이익잉여금/총자산)
  + 3.3×(EBIT/총자산)
  + 0.6×(시가총액/총부채)
  + 1.0×(매출/총자산)
```

| Z 값 | 판정 |
|------|------|
| > 2.99 | 안전 (Safe Zone) |
| 1.81~2.99 | 회색지대 (Grey Zone) |
| < 1.81 | 위험 (Distress Zone) |

**ROIC (투하자본이익률)**

```
ROIC = 영업이익 × (1 - 법인세율) / 투하자본
투하자본 = 총자산 - 유동부채
```

---

### 6-7. DCF 내재가치 (2단계 모델)

```
고성장 기간 (5년): EPS × (1+g)^t / (1+r)^t  합산
영구 성장 기간:    EPS_5년차 × (1+g_terminal) / (r - g_terminal)
```

- **할인율 r**: CAPM = `Rf + β × ERP` (위험무이자율 + 베타 × 시장 초과수익률)
- **고성장률 g**: yfinance 애널리스트 컨센서스 또는 실적 CAGR
- **터미널 성장률 g_terminal**: 장기 GDP 성장률 (기본 2.5%)

DCF 업사이드 = `(내재가치 - 현재가) / 현재가 × 100%`

---

### 6-8. EPS 서프라이즈

```
서프라이즈% = (실제 EPS - 컨센서스 EPS) / |컨센서스 EPS| × 100
```

- **비트율**: 4분기 중 실제 EPS ≥ 컨센서스인 분기 비율
- **추세 판정**: 최근 2분기 평균 vs 이전 2분기 평균
  - 차이 ≥ +5%p → 가속(↑)
  - 차이 ≤ −5%p → 둔화(↓)
  - 나머지 → 안정(→)

---

### 6-9. 매크로 레짐

VIX·10Y 금리 변화(bp)·USD-KRW·WTI 원유 네 가지 지표를 조합합니다:

| 레짐 | 조건 |
|------|------|
| Risk-On | VIX < 20, 금리 안정(±20bp), 달러 약세 |
| Neutral | 혼재 신호 |
| Risk-Off | VIX > 30, 금리 급등(+30bp+), 달러 강세 |

> 금리 변화는 항상 **bp(베이시스포인트)** 단위로 표현합니다.

---

## 7. 백엔드 아키텍처

### 프로세스 흐름

```
브라우저 요청
    │
    ▼
FastAPI (app.py, port 8765)
    │  ├─ /api/analyze/{symbol}        비동기 → run_in_executor
    │  ├─ /api/screener                병렬 워커 (ThreadPoolExecutor)
    │  ├─ /api/briefing                4H 브리핑 JSON
    │  └─ /api/settings                .env.local 읽기/쓰기
    │
    ▼
stock_snapshot.py (오케스트레이터, ~10초)
    │
    ├─ stock_data_provider.py   ←  yfinance TTL 5분 캐시
    │      │
    │      └─ yfinance / pykrx / REST APIs
    │
    ├─ fundamentals.py           PER/PBR/ROE + 18개 심화 지표
    ├─ financial_quality.py      Piotroski / Altman Z / ROIC / CAGR
    ├─ dcf_estimator.py          2단계 DCF 내재가치
    ├─ earnings_history.py       5년 연간 실적
    ├─ earnings_surprise.py      4분기 EPS 서프라이즈
    ├─ momentum_signals.py       SPY RS / 거래량 서지 / 52주 돌파
    ├─ investment_scorecard.py   5차원 스코어카드
    └─ sector_intelligence.py   20개 섹터 심층 분석
```

### 비동기 처리 패턴

`stock_snapshot.py`의 `build_stock_snapshot()`은 동기 I/O 작업(yfinance 호출 등)을 포함하므로
FastAPI 이벤트 루프를 블로킹하지 않도록 `run_in_executor`로 실행합니다:

```python
loop = asyncio.get_event_loop()
result = await loop.run_in_executor(None, build_stock_snapshot, symbol, market)
```

### 핵심 모듈 역할

| 파일 | 역할 |
|------|------|
| `stock_snapshot.py` | 단일 종목 분석 최종 오케스트레이터 |
| `stock_data_provider.py` | yfinance 캐시 레이어 (TTL 5분) — 모든 yfinance 호출 경유 |
| `fundamentals.py` | PER/PBR/ROE + 심화 18개 지표 |
| `financial_quality.py` | Piotroski F-Score, Altman Z-Score, ROIC, 매출 CAGR |
| `dcf_estimator.py` | 2단계 DCF 내재가치 (CAPM 할인율) |
| `earnings_history.py` | 5년 연간 실적 히스토리 |
| `earnings_surprise.py` | 4분기 EPS 서프라이즈·비트율·추세 |
| `momentum_signals.py` | SPY 상대강도, 거래량 서지, 52주 돌파, Short DTC, 순현금 |
| `investment_scorecard.py` | 5차원 종합 스코어카드 |
| `ticker_resolver.py` | 14,495개 별명 테이블 + SEC EDGAR fallback |
| `sector_intelligence.py` | 20개 섹터 심층 분석 |
| `advisor_4h.py` | 4H 어드바이징 파이프라인 오케스트레이터 |
| `briefing.py` | 4H 통합 브리핑 8섹션 생성 |
| `risk_advisor.py` | 매크로 기반 리스크 노출 판단 |
| `advisory_policy.py` | 알림 심각도·발송 정책 중앙 관리 |
| `supply_chain_alpha.py` | 수급 체인 스필오버 (29개 체인 규칙) |
| `daily_alpha.py` | KR/US LONG/SHORT 후보 스크리닝 |
| `inbound_bot.py` | 텔레그램 수신봇 (`/분석` 명령 처리) |
| `tradingview.py` | TradingView 차트 URL 생성 (KRX/KOSDAQ/US) |

### 알림 발송 정책

| 조건 | 처리 방식 |
|------|-----------|
| 스코어 ≥ 90 + 직접 증거 | 즉시 발송 (URGENT) |
| 스코어 ≥ 70 | 4H 브리핑에 포함 (ACTION / WATCH) |
| 스코어 < 70 | 무시 또는 4H 브리핑으로 흡수 |

---

## 8. 프론트엔드 구조

| 항목 | 상세 |
|------|------|
| 기술 스택 | 순수 HTML / CSS / Vanilla JavaScript (외부 프레임워크 없음) |
| 구조 | 단일 파일 SPA — `src/tele_quant/dashboard/app.py`에 HTML 인라인 |
| 테마 | 다크 테마 기본 |
| 탭 구성 | 8개 탭 (상단 네비게이션) |
| API 통신 | `fetch()` → FastAPI JSON 응답 |
| 가격 포맷 | KRW → 원화(₩), USD → 달러($) 자동 구분 |
| EPS 단위 | KR 종목: `원` 단위 정수 표기 / US 종목: `$0.00` 소수 표기 |

외부 CDN 의존성이 없으므로 인터넷 연결 없이도 대시보드 UI 자체는 로드됩니다.
데이터 갱신 시에만 네트워크가 필요합니다.

---

## 9. 기술 스택

| 항목 | 기술 | 버전 |
|------|------|------|
| 언어 | Python | 3.11+ |
| 패키지 관리 | uv (Astral) | 최신 |
| 웹 프레임워크 | FastAPI + Uvicorn | — |
| 설정 관리 | Pydantic Settings | — |
| 데이터베이스 | SQLite (aiosqlite) | — |
| 주가 데이터 | yfinance | — |
| KRX 데이터 | pykrx | — |
| 텔레그램 봇 발신 | python-telegram-bot | — |
| 텔레그램 채널 수집 | Telethon (MTProto) | — |
| 스케줄링 | APScheduler (in-process) + systemd timer (WSL) | — |
| 린트 | ruff | — |
| 테스트 | pytest | 2,477개 통과 (2026-05-22 기준) |
| 실행 환경 | Windows 10/11 + WSL2 Ubuntu | — |
| 서비스 바인딩 | 0.0.0.0:8765 (WSL2 → Windows 브라우저 접근) | — |

---

## 10. 트러블슈팅

### WSL2가 설치되어 있지 않음

```powershell
# 관리자 PowerShell에서 실행
wsl --install
# 재부팅 후 Ubuntu 초기 설정
```

### 포트 8765 충돌

```bash
# WSL Ubuntu 터미널에서 실행
fuser -k 8765/tcp
```

### "사이트에 연결할 수 없음"

1. `run_dashboard.bat` 창이 열려 있는지 확인 (서버 실행 중이어야 함)
2. 브라우저 주소창에 직접 입력: `http://localhost:8765`
3. WSL IP 직접 확인: WSL 터미널에서 `hostname -I`

### yfinance 데이터가 없거나 오래됨

TTL 캐시(5분) 적용 중입니다. 5분 후 재시도하거나,
`.env.local`에서 `OFFLINE_MODE=false`를 확인하세요.

### 한글 입력·출력 오류

```cmd
chcp 65001
```

CMD 창에서 UTF-8 코드 페이지를 활성화합니다.

### setup.bat을 재실행하고 싶을 때

프로젝트 폴더에서 `.setup_done` 파일을 삭제한 후 `setup.bat`을 다시 실행합니다.

### uv 명령을 찾을 수 없음 (WSL)

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.bashrc
```

### 테스트 전체 실행

```bash
uv run ruff check .          # 린트 검사
uv run pytest -q             # 전체 테스트
```

---

## 11. 라이선스 및 면책

이 소프트웨어는 공개 데이터 기반 **개인 리서치 보조 도구**입니다.

- 매수·매도 추천이 아닙니다.
- 과거 데이터 기반 분석이며 미래 수익을 보장하지 않습니다.
- 투자 판단의 최종 책임은 사용자에게 있습니다.
- 실계좌 자동 매매 기능은 포함되어 있지 않습니다.
