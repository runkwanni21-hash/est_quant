# tele-quant 인수인계 문서

> **대상**: 이 프로젝트를 처음 받는 AI / 개발자  
> **작성일**: 2026-05-19  
> **기준 브랜치**: `integration/rebuild-modoo-advisor`  
> **테스트**: 2361 passed (121 test files, 83 source modules)

---

## 1. 이 프로젝트가 무엇인가

**한국·미국 주식 4시간 단위 매매 어드바이징 자동화 시스템.**

사용자가 텔레그램에서 `/분석 NVDA` 또는 `/분석 삼성전자`를 입력하면, 공개 정보(yfinance·DART·SEC·RSS)를 조합해 다음을 한 화면에 제공한다:

- 4H/일봉 기술 지표 (RSI, 볼린저밴드, OBV, 거래량)
- 펀더멘탈 스냅샷 (PER·PBR·ROE·EPS성장·매출성장·OPM·부채비율)
- 심화 밸류에이션 (EV/EBITDA·FCF 수익률·PEG·순현금·현재비율)
- 애널리스트 컨센서스 (목표가·투자의견·커버리지 수)
- 재무 품질 (Piotroski F-Score 9점·Altman Z·ROIC·3년 매출 CAGR)
- DCF 2단계 내재가치 추정 (CAPM 할인율)
- 연간 실적 5년 히스토리 (매출·OPM·순익 YoY)
- EPS 서프라이즈 4분기 (비트율·평균서프라이즈·가속/둔화 트렌드)
- 모멘텀 신호 (SPY 대비 상대강도·거래량 서지·52주 돌파·Short DTC·순현금)
- 투자 스코어카드 (5차원 종합 점수 + STRONG_WATCH / WATCH / NEUTRAL / AVOID)
- 섹터 심층 분석 (20개 섹터별 매크로·밸류에이션·체크포인트)
- 수급 체인 수혜주 (공급망 관계 그래프 기반)
- TradingView 차트 링크 (4H·일봉)
- LONG 관찰 적합도 별점 (★1-5)

또한 4시간마다 자동으로 브리핑을 발송하고, 장중 급등 감지·가격 알림·주간 성과 리뷰도 수행한다.

**중요 제약**: 실계좌·브로커 연동 없음. "매수 권장" 표현 금지. "LONG 관찰" 표현 사용.

---

## 2. 프로젝트 목표 (사용자 의도)

> "공시·뉴스·급등 이슈를 실시간으로 받아, 가격·차트·가치 분석으로 검증하고, 섹터별 알고리즘으로 저평가 종목을 선별하며, 추천 시점부터 주말까지 성과를 자동 추적해 스스로 개선되는 한국·미국 주식 리서치 보조 시스템"

### 핵심 5가지

1. **즉각 반응**: 텔레그램 `/분석` → 30~60초 내 전체 분석 결과 반환
2. **차트+가치 복합 분석**: 기술·펀더멘탈·모멘텀·DCF·EPS서프라이즈 통합
3. **섹터별 알고리즘**: 20개 섹터별 특화 지표 적용
4. **이슈 선반영 판단 → 수혜주 자동 라우팅**: 메인 종목 급등 시 tier-2 수혜주 자동 발굴
5. **자기개선 루프**: 추천 성과 추적 → 가중치 점진 조정

---

## 3. 아키텍처 전체 흐름

```
[외부 데이터 소스]
  DART 공시 ──────────────────────────────────────────┐
  SEC EDGAR 8-K ──────────────────────────────────────┤
  RSS (PR Newswire/GlobeNewswire/GoogleNews) ──────────┤
  yfinance (OHLCV·info·재무제표) ─────────────────────┤──► [stock_data_provider.py]
  한국은행 ECOS ───────────────────────────────────────┤         TTL 5분 캐시
  EIA 에너지 / ECB 환율 ──────────────────────────────┘
                        │
                        ▼
              [db.py — SQLite Store]
              ./data/private/tele_quant.sqlite
                        │
          ┌─────────────┼─────────────────────────────┐
          ▼             ▼                              ▼
  [daily_alpha.py]  [macro_pulse.py]         [inbound_bot.py]
  KR/US LONG/SHORT   WTI·금리(bp)·환율·VIX    텔레그램 수신
  후보 자동 스크리닝  매크로 온도계              /분석·/브리핑·/매크로 등
          │             │                              │
          ▼             ▼                              ▼
  [supply_chain_alpha] [sector_cycle]        [stock_snapshot.py]
  수급 체인 스필오버   섹터 순환 분석           단일 종목 분석 엔진
  tier-1/2/3 수혜주    13개 사이클              (기술+펀더+모멘텀+DCF+EPS)
          │             │                              │
          └─────────────┴──────────────────────────────┘
                        │
                        ▼
              [briefing.py] — 4H 통합 브리핑 8개 섹션
                        │
                        ▼
              [telegram_sender.py] — 텔레그램 발신

[systemd timers — WSL Ubuntu]
  briefing-kr/us.timer        4H마다 브리핑 발송
  alpha-review-kr/us.timer    매일 LONG/SHORT 후보
  surge-scan-kr/us.timer      30분 급등 감지
  price-alert.timer           30분 목표가 알림
  backlog-kr/us.timer         수주잔고 갱신
  weekly.timer                일요일 23:00 주간 리뷰
  inbound-bot.service         상시 데몬 (타이머 없음)
  ... 총 45개 파일 (22 timers + 22 services + 1 service)
```

---

## 4. 모듈 전체 목록 (83개 소스 파일)

### 핵심 인프라

| 파일 | 역할 |
|------|------|
| `settings.py` | Pydantic Settings — 모든 환경변수 중앙 관리 |
| `db.py` | SQLite Store — 모든 DB 접근 단일 진입점 |
| `models.py` | 공유 데이터 모델 |
| `stock_data_provider.py` | **yfinance 캐싱 레이어 (TTL 5분)** — 모든 yfinance 호출 경유 필수 |
| `logging.py` | 로깅 설정 |

### 텔레그램 I/O

| 파일 | 역할 |
|------|------|
| `inbound_bot.py` | 텔레그램 수신봇 — `/분석·/브리핑·/매크로·/수혜주·/포트·/수주·/도움말` |
| `telegram_sender.py` | 텔레그램 발신 — `TelegramSender` 클래스, 토큰 마스킹 포함 |
| `telegram_client.py` | 저수준 Telegram API 래퍼 |

### 단일 종목 분석 (`/분석` 경로)

| 파일 | 역할 |
|------|------|
| `stock_snapshot.py` | **핵심** — `build_stock_snapshot()` + `format_stock_snapshot()` |
| `fundamentals.py` | FundamentalSnapshot (PER/PBR/ROE/EPS성장/OPM + 심화 9개 지표) |
| `financial_quality.py` | Piotroski F-Score·Altman Z·ROIC·매출 CAGR 3Y |
| `dcf_estimator.py` | 2단계 DCF 내재가치 (CAPM 할인율, EPS 기반) |
| `earnings_history.py` | 5년 연간 실적 히스토리 (income_stmt 경유) |
| `earnings_surprise.py` | 4분기 EPS 서프라이즈 (비트율·평균서프라이즈·트렌드) |
| `momentum_signals.py` | SPY 상대강도·거래량 서지·52주 돌파·Short DTC·순현금 |
| `investment_scorecard.py` | 5차원 스코어카드 (STRONG_WATCH/WATCH/NEUTRAL/AVOID) |
| `ticker_resolver.py` | 티커 해소·cap bucket·OTC·IPO·SEC EDGAR fallback |
| `tradingview.py` | TradingView 차트 URL (KRX/KOSDAQ/US) |
| `sector_intelligence.py` | 20개 섹터 심층 분석 |
| `sector_analysis_engine.py` | 섹터별 valuation/technical playbook 스코어링 |
| `sector_macro.py` | 섹터별 매크로 지표 포맷 |
| `financial_sanity.py` | 재무 데이터 sanity 체크 |
| `earnings_snapshot.py` | 분기 실적 스냅샷 |

### 시장 스크리닝 (자동화 경로)

| 파일 | 역할 |
|------|------|
| `daily_alpha.py` | KR/US LONG/SHORT 후보 스크리닝 (70점 기준) |
| `surge_alert.py` | 장중 급등 감지 + 카탈리스트 규명 |
| `price_alert.py` | 목표가/무효화가 도달 알림 |
| `supply_chain_alpha.py` | 수급 체인 스필오버 — 29개 체인 규칙 |
| `order_backlog.py` | 수주잔고 추적 (DART/EDGAR/yfinance) |
| `theme_board.py` | 퀀터멘탈 테마 보드 |
| `scenario_alpha.py` | 9개 시나리오 분류 + 전조점수 |

### 매크로·섹터 분석

| 파일 | 역할 |
|------|------|
| `macro_pulse.py` | WTI·10Y금리(bp)·환율·VIX 온도계 — Regime 분류 |
| `external_indicators.py` | 외부 경제 지표 수집 |
| `ecos_client.py` | 한국은행 ECOS API |
| `sector_cycle.py` | 13개 섹터 순환 분석 |
| `economic_calendar.py` | 경제 캘린더 이벤트 |
| `calendar_score_policy.py` | 요일별 정책 점수 |

### 뉴스·감성·공시 수집

| 파일 | 역할 |
|------|------|
| `rss_collector.py` | RSS 뉴스 (PR Newswire·GlobeNewswire·BusinessWire·GoogleNews) |
| `finnhub_client.py` | Finnhub API 뉴스 |
| `opendart_client.py` | DART 공시 API |
| `sec_client.py` | SEC EDGAR 8-K·full-text 검색 |
| `recent_issue_collector.py` | 최근 이슈 수집·포맷 |
| `headline_cleaner.py` | 헤드라인 노이즈 제거 |
| `polarity.py` | 감성 극성 분류 |
| `evidence.py` | Evidence 데이터 모델 |
| `evidence_ranker.py` | 증거 중요도 랭킹 |
| `catalyst_classifier.py` | 카탈리스트 분류 |

### 관계 그래프 (종목 간 관계)

| 파일 | 역할 |
|------|------|
| `relation_feed.py` | 유니버스 정의 (US 100+ / KR 100+), 관계 피드 |
| `relation_seed_importer.py` | 23개 섹터 1220 엣지 YAML→DB |
| `relation_fallback.py` | lead-lag 자체 계산 엔진 |
| `relation_graph.py` | 관계 그래프 엔진 |
| `relation_miner.py` | 급등주 자동 관계 발굴 |
| `alias_audit.py` | 티커 alias 감사 |
| `universe_audit.py` | 유니버스 감사 |

### 4H 어드바이징 (integration 브랜치 신규)

| 파일 | 역할 |
|------|------|
| `advisory_policy.py` | 알림 심각도·발송 정책 (score≥90=URGENT, ≥70=ACTION/WATCH) |
| `risk_advisor.py` | 매크로 기반 리스크 노출 판단 (김승환 전략 통합) |
| `advisor_4h.py` | 4H 어드바이징 파이프라인 오케스트레이터 |

### 4H 브리핑·포트폴리오·주간

| 파일 | 역할 |
|------|------|
| `briefing.py` | 4H 통합 브리핑 8개 섹션 오케스트레이터 |
| `mock_portfolio.py` | 모의 포트폴리오 P&L 추적 (실주문 아님) |
| `weekly.py` | 주간 성과 리뷰 생성 |
| `weekly_cycle_orchestrator.py` | 주간 사이클 오케스트레이터 |
| `live_pair_watch.py` | 한-미 페어 관찰 엔진 |
| `alpha_review.py` | 알파 후보 리뷰 |
| `watchlist.py` | 관심 종목 관리 |

---

## 5. 점수 계산 구조

### 자동화 스크리닝 (daily_alpha, 0~100점)

```
total_score = tech_4h*0.30 + tech_3d*0.20 + sentiment*0.25 + backlog*0.10 + valuation*0.15
→ 70점 이상: 후보 | 80점 이상: 모의 포트 | 90점+direct_evidence: URGENT 즉시 발송
```

### 투자 스코어카드 (stock_snapshot, 0~100점)

```
scorecard = momentum*0.25 + fundamental*0.20 + growth*0.25 + reliability*0.20 + valuation*0.10
→ STRONG_WATCH ≥75 / WATCH ≥60 / NEUTRAL ≥45 / AVOID <45
```

### LONG 관찰 별점 (1~5★)

```
star_raw = tech_score*0.40 + val_score*0.30 + swing_score*0.30
★★★★★ ≥80 / ★★★★☆ ≥65 / ★★★☆☆ ≥50 / ★★☆☆☆ ≥35 / ★☆☆☆☆ <35
```

---

## 6. 주요 데이터 흐름 — `/분석 NVDA` 실행 시

```
텔레그램 → inbound_bot.py
  → _resolve_symbol("NVDA") → ("NVDA", "US")
  → run_in_executor(_do_analysis)           # blocking I/O 비차단 필수
    → build_stock_snapshot("NVDA", "US")
      → stock_data_provider 캐시 경유       # 모든 yfinance 호출
        → get_ticker_info, get_ohlcv
        → get_income_stmt, get_balance_sheet, get_cashflow, get_earnings_history
      → ticker_resolver.resolve_ticker()    # cap bucket / OTC / IPO
      → financial_quality.fetch_...()      # Piotroski / Altman Z / ROIC
      → dcf_estimator.estimate_dcf()
      → earnings_history.fetch_...()
      → earnings_surprise.fetch_...()
      → momentum_signals.fetch_...()       # SPY RS / 거래량 / DTC
      → investment_scorecard.build_scorecard()  # 5차원 집계
      → sector_intelligence.run_sector_analysis()
      → tradingview.chart_url()
      → compute_star_rating()
    → format_stock_snapshot(snap)
  → _send(chat_id, text)
```

---

## 7. 환경변수 설정 (.env.local — Git 절대 불가)

```bash
TELEGRAM_BOT_TOKEN=7xxx...
TELEGRAM_BOT_TARGET_CHAT_ID=879...
TELEGRAM_INBOUND_BOT_TOKEN=7yyy...          # 없으면 BOT_TOKEN으로 fallback
TELEGRAM_INBOUND_ALLOWED_IDS=879...,-1003...  # 콤마 구분

SQLITE_PATH=./data/private/tele_quant.sqlite
TELEGRAM_SESSION_PATH=./data/private/tele_quant.session
EVENT_PRICE_CSV_PATH=./data/private/event_price_1000d.csv
CORRELATION_CSV_PATH=./data/private/stock_correlation_1000d.csv

DART_API_KEY=...
FINNHUB_API_KEY=...
ECOS_API_KEY=...
```

chat_id 확인: 봇 실행 후 `WARNING 미허가 chat_id=XXXXXXX` 로그에서 복사.

---

## 8. 코딩 규칙 (반드시 준수)

| 규칙 | 이유 |
|------|------|
| `git push` / `git reset --hard` 금지 | 원격 손상·데이터 손실 위험 |
| `.env.local` / `data/` / `*.db` 커밋 금지 | 보안 |
| "매수 권장" / "확정 수익" / "자동매매" 표현 금지 | 투자자 보호 |
| 면책 문구 없이 종목 추천 발송 금지 | 투자자 보호 |
| 10Y 금리 변화는 bp(베이시스포인트) 단위 | 오해 방지 |
| 모든 yfinance 호출은 `stock_data_provider` 경유 | TTL 5분 캐시 |
| blocking I/O는 `run_in_executor`로 래핑 | inbound_bot 이벤트 루프 보호 |
| 테스트에서 yfinance 패치는 `tele_quant.stock_data_provider.get_*` 직접 패치 | 캐시 오염 방지 |
| `ruff check .` 통과 필수 | CI |
| `pytest -q` 전량 통과 필수 (현재 2361개) | CI |

---

## 9. 알려진 버그 / 주의사항

1. **`_stmt_cache` 테스트 오염**: `stock_data_provider`의 모듈 수준 캐시는 pytest 세션 내 지속된다. yfinance 관련 테스트는 반드시 `tele_quant.stock_data_provider.get_income_stmt` 등을 직접 patch. `yfinance.Ticker` 직접 patch는 캐시가 채워져 있으면 무시됨.
2. **분석 응답 속도**: `/분석` 후 30~60초 소요. "⏳ 분석 중..." 메시지 → 정상.
3. **10Y 금리 단위**: `macro_pulse.py`의 `us10y_chg`는 bp. % 오해 → regime 분류 오작동.
4. **WSL 환경**: Windows Claude Code 앱에서 WSL 경로로 열기. systemd는 WSL Ubuntu 내에서만 동작.
5. **수신봇 blocking**: `analyze_single` 등 yfinance 함수는 반드시 `run_in_executor` 래핑.
6. **브로드캐스트 채널**: Telegram 채널에서는 수신봇(`getUpdates`) 동작 안 함. DM/그룹에서만.

---

## 10. 다음 우선 작업

| 우선순위 | 기능 | 파일 |
|----------|------|------|
| 🔴 P1 | 이슈-주가 선반영 감지기 | `mispricing_detector.py` |
| 🔴 P1 | 수혜주 자동 라우팅 강화 | `supply_chain_alpha.py` 확장 |
| 🟡 P2 | M&A / 자사주 공시 감시 | `corporate_action_watcher.py` |
| 🟡 P2 | 자기개선 가중치 조정 | `weight_optimizer.py` |
| 🟠 P3 | 섹터별 가치평가 강화 | `sector_valuation.py` 확장 |

---

## 11. 테스트 명령

```bash
uv run ruff check .
uv run pytest -q
uv run tele-quant briefing --market KR --no-send
uv run tele-quant briefing --market US --no-send
uv run tele-quant ops-doctor
uv run tele-quant inbound-bot -v
```
