# tele-quant — AI 인수인계 온보딩

> **작성일**: 2026-05-19 | 브랜치: `integration/rebuild-modoo-advisor`  
> **테스트**: 2361 passed | **소스**: 83 modules | **systemd**: 45 files

---

## 이 프로젝트가 무엇인가

한국·미국 주식 4시간 단위 매매 어드바이징 자동화 시스템.  
공시(DART/SEC)·뉴스·yfinance 데이터를 수집해, 기술·펀더멘탈·모멘텀·DCF·EPS 서프라이즈를 종합한 단일 분석 리포트를 텔레그램에 제공한다.  
**실계좌 연동 없음.** "매수 권장" 표현 금지. "LONG 관찰" 사용.

---

## 즉시 확인할 것들

```bash
uv run pytest -q                                       # 전체 테스트 (2361개)
uv run ruff check .                                    # 린트
uv run tele-quant briefing --market KR --no-send       # KR 4H 브리핑 미리보기
uv run tele-quant briefing --market US --no-send       # US 4H 브리핑 미리보기
uv run tele-quant ops-doctor                           # 시스템 진단
uv run tele-quant inbound-bot -v                       # 수신봇 (디버그 모드)
```

---

## 핵심 파일 위치

| 목적 | 파일 |
|------|------|
| **AI 지시서 (최우선)** | `CLAUDE.md` |
| 상세 인수인계 | `docs/HANDOVER.md` |
| 실제 구현 상태 | `docs/PROJECT_STATE.md` |
| CLI 진입점 | `src/tele_quant/cli/` |
| **단일 종목 분석 엔진** | `src/tele_quant/stock_snapshot.py` |
| **텔레그램 수신봇** | `src/tele_quant/inbound_bot.py` |
| yfinance 캐싱 레이어 | `src/tele_quant/stock_data_provider.py` |
| 4H 통합 브리핑 | `src/tele_quant/briefing.py` |
| LONG/SHORT 후보 엔진 | `src/tele_quant/daily_alpha.py` |
| 수급 체인 | `src/tele_quant/supply_chain_alpha.py` |
| 모의 포트폴리오 | `src/tele_quant/mock_portfolio.py` |
| 매크로 온도계 | `src/tele_quant/macro_pulse.py` |
| 펀더멘탈 스냅샷 | `src/tele_quant/fundamentals.py` |
| DB 스키마 | `src/tele_quant/db.py` |
| systemd 타이머 | `systemd/` (45개 파일) |

---

## 텔레그램 수신봇 사용법

### .env.local 설정

```bash
TELEGRAM_BOT_TOKEN=7xxx...
TELEGRAM_BOT_TARGET_CHAT_ID=879...
TELEGRAM_INBOUND_BOT_TOKEN=7yyy...          # 없으면 BOT_TOKEN으로 fallback
TELEGRAM_INBOUND_ALLOWED_IDS=879...,-1003...  # 콤마 구분

SQLITE_PATH=./data/private/tele_quant.sqlite
DART_API_KEY=...
FINNHUB_API_KEY=...
ECOS_API_KEY=...
```

chat_id 확인: 봇 실행 후 `WARNING 미허가 chat_id=XXXXXXX` 로그에서 복사.

### 텔레그램 명령

```
/분석 NVDA              → 미국 종목 즉시 전체 분석 (30~60초)
/분석 삼성전자           → 한국 종목 즉시 전체 분석
/분석 005930            → KR 6자리 코드로도 가능
/분석 PLTR              → 마이크로캡·신규상장 포함 전 US 티커 지원
/매크로                  → WTI·금리·환율·VIX 온도계
/브리핑 KR              → KR 4H 통합 브리핑
/브리핑 US              → US 4H 통합 브리핑
/수혜주 삼성전자          → 수급 체인 수혜주·피해주 목록
/포트                    → 모의 포트폴리오 P&L
/수주 NVDA              → 수주잔고 조회
/도움말                  → 전체 명령 목록
```

**주의**: 브로드캐스트 채널에서는 수신봇 동작 안 함. DM 또는 그룹 채팅에서만.

---

## `/분석` 출력 구조 (2026-05-19 기준 전체 섹션)

```
🔍 [기업명] (티커) [시총 버킷] [거래소]
   ⚠ 티커 경고 (OTC·나노캡·신규IPO 등)

── 가격 변동
── 4H 기술 지표 (RSI·볼린저·OBV·tech_score)
── 일봉 이동평균 (MA20·MA60·daily RSI)
── 스윙 셋업 (셋업유형·수급패턴·스윙점수)
── 펀더멘탈 스냅샷 (PER·PBR·ROE·EPS성장·OPM·부채비율)
── 심화 지표 (EV/EBITDA·FCF수익률·매출총이익률·현재비율·PEG)
── 목표가·투자의견 (애널리스트 컨센서스)
── 52주 위치·시가총액·섹터
── 섹터 분석 (섹터 점수·위험·촉매·동종기업·체크포인트)
── 종합 점수·스윙 등급
── 최근 이슈 (뉴스·공시 요약)
── 수혜 연관 종목 (관계 그래프)
── 연간 실적 5년 (매출·OPM·순익 YoY)
── 재무 품질 (Piotroski F-Score·Altman Z·ROIC·CAGR)
── DCF 내재가치 추정
── 섹터 심층 분석 (sector_intelligence)
── 섹터 시드 관계 힌트
── 섹터 매크로 지표
── 캘린더 정책 노트
── 모멘텀 신호 (SPY 상대강도·거래량·52주·Short DTC·순현금)
── 분기 EPS 서프라이즈 4분기
── 투자 스코어카드 (5차원, STRONG_WATCH/WATCH/NEUTRAL/AVOID)
── TradingView 차트 링크 (4H·일봉)
── LONG 관찰 적합도 별점 (★1-5)
⚠ 공개 정보 기반 리서치 보조 — 투자 판단 책임은 사용자에게 있음
```

---

## 점수 계산 구조

### 자동화 스크리닝 (0~100점)

```python
total_score = tech_4h*0.30 + tech_3d*0.20 + sentiment*0.25 + backlog*0.10 + valuation*0.15
# 70점 이상 → 후보 | 80점 이상 → 모의 포트 | 90점+직접증거 → URGENT 즉시 발송
```

### 투자 스코어카드 (0~100점)

```python
scorecard = momentum*0.25 + fundamental*0.20 + growth*0.25 + reliability*0.20 + valuation*0.10
# STRONG_WATCH ≥75 / WATCH ≥60 / NEUTRAL ≥45 / AVOID <45
```

### LONG 관찰 별점 (1~5★)

```python
star_raw = tech_score*0.40 + val_score*0.30 + swing_score*0.30
# ★★★★★ ≥80 / ★★★★☆ ≥65 / ★★★☆☆ ≥50 / ★★☆☆☆ ≥35 / ★☆☆☆☆ <35
```

---

## 개발 시 반드시 알아야 할 것들

### 1. 모든 yfinance 호출은 stock_data_provider 경유

```python
# ❌ 직접 호출 금지
yf.Ticker("NVDA").info

# ✅ 캐시 경유 필수
from tele_quant.stock_data_provider import get_ticker_info, get_ohlcv
info = get_ticker_info("NVDA")
df = get_ohlcv("NVDA", period="3mo", interval="1d")
```

### 2. inbound_bot에서 blocking I/O는 run_in_executor 필수

```python
# ❌ 이벤트 루프 블로킹
result = analyze_single(symbol, market)

# ✅ 비차단
loop = asyncio.get_event_loop()
result = await loop.run_in_executor(None, analyze_single, symbol, market)
```

### 3. 테스트에서 yfinance 패치 방법

```python
# ❌ 캐시가 이미 채워져 있으면 무시됨
with patch("yfinance.Ticker", return_value=mock):

# ✅ stock_data_provider 함수를 직접 패치
with patch("tele_quant.stock_data_provider.get_income_stmt", return_value=df):
```

### 4. 금리 변화는 bp 단위

```python
# macro_pulse.py의 us10y_chg는 % 아닌 bp(베이시스포인트)
# +100 → +1% 금리 상승, -25 → -0.25% 금리 하락
```

---

## 4H 브리핑 8개 섹션 구조

```
① 시장 온도 (위험선호/중립/위험회피 + 매크로 수치)
② 리스크 노출 (Risk Mode + KR/US 비중 힌트)  ← risk_advisor.py
③ LONG 관찰 후보 Top 3
④ SHORT/회피 후보 Top 1
⑤ 수혜주 라우팅 (급등 후 tier-2 수혜주)
⑥ 모의 포트폴리오 P&L
⑦ 다음 4H 체크포인트
⑧ 면책 문구 (필수)
```

---

## 다음 개발 과제

| 우선순위 | 기능 | 설명 |
|----------|------|------|
| 🔴 P1 | 이슈-주가 선반영 감지기 | 이슈 발생 후 주가 반응 → 반영/미반영 판단 |
| 🔴 P1 | 수혜주 자동 라우팅 강화 | 급등 → tier-2 수혜주 저평가 자동 발굴 |
| 🟡 P2 | M&A / 자사주 공시 감시 | DART "자사주매입" → LONG +15점 |
| 🟡 P2 | 자기개선 가중치 조정 | 주간 성과 데이터로 scoring 가중치 점진 조정 |

---

## 절대 금지 사항

| 금지 | 이유 |
|------|------|
| `git push` / `git reset --hard` | 원격 손상·데이터 손실 |
| `.env.local` / `data/` / `*.db` 커밋 | 보안 |
| "매수 권장" / "확정 수익" / "자동매매" | 투자자 보호 |
| 면책 문구 없이 추천 발송 | 투자자 보호 |
| 실계좌·브로커 주문 코드 | 프로젝트 범위 외 |

---

## 커밋 전 반드시 실행

```bash
uv run ruff check .     # 린트 통과
uv run pytest -q        # 2361개 테스트 통과
```
