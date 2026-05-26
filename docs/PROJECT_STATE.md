# PROJECT_STATE.md — 실제 구현 상태

> 기준: 2026-05-19 | `main_tele` 브랜치  
> **현실 기준** 문서 — 코드에 없는 기능은 ✅로 표시하지 않는다.

---

## 1. 구현 완료 모듈 (파일 존재 확인됨)

### 핵심 인프라

| 파일 | 상태 | 비고 |
|------|------|------|
| `settings.py` | ✅ 완성 | Pydantic Settings v2, .env.local 로딩 |
| `db.py` | ✅ 완성 | SQLite Store, 모든 테이블 스키마 포함 |
| `models.py` | ✅ 완성 | |
| `stock_data_provider.py` | ✅ 완성 | TTL 5분 캐시, `get_ohlcv/info/income_stmt/balance_sheet/cashflow/earnings_history` |
| `logging.py` | ✅ 완성 | |

### 텔레그램 I/O

| 파일 | 상태 | 비고 |
|------|------|------|
| `inbound_bot.py` | ✅ 완성 | httpx 기반, `/분석·/브리핑·/매크로·/수혜주·/포트·/수주·/도움말`, run_in_executor |
| `telegram_sender.py` | ✅ 완성 | TelegramSender, 토큰 마스킹 |
| `telegram_client.py` | ✅ 완성 | |

### 단일 종목 분석 (Phase 2 완성 — 2026-05-19)

| 파일 | 상태 | 비고 |
|------|------|------|
| `stock_snapshot.py` | ✅ 완성 | `build_stock_snapshot` + `format_stock_snapshot`, 20+ 섹션 |
| `fundamentals.py` | ✅ 완성 | PER/PBR/ROE + ev_to_ebitda/fcf_yield/peg_ratio/analyst_target 등 18개 지표 |
| `financial_quality.py` | ✅ 완성 | Piotroski F-Score 9기준·Altman Z·ROIC·CAGR 3Y·유동성 등급 |
| `dcf_estimator.py` | ✅ 완성 | 2단계 DCF, CAPM, EPS 기반, 성장률 2~45% 클램프 |
| `earnings_history.py` | ✅ 완성 | income_stmt 경유, 5년 연간 실적 |
| `earnings_surprise.py` | ✅ 완성 | 4분기 EPS 비트율·평균서프라이즈·가속/둔화 트렌드 |
| `momentum_signals.py` | ✅ 완성 | SPY RS(1M/3M)·거래량 서지(5D/20D)·52주 돌파·Short DTC·순현금 |
| `investment_scorecard.py` | ✅ 완성 | 5차원 스코어카드, 바 시각화, STRONG_WATCH/WATCH/NEUTRAL/AVOID |
| `ticker_resolver.py` | ✅ 완성 | 나노/마이크로/스몰/미드/라지/메가캡·OTC·IPO·SEC EDGAR fallback |
| `tradingview.py` | ✅ 완성 | KRX/KOSDAQ/US, 4H(240)/1D/1W 인터벌 |
| `financial_sanity.py` | ✅ 완성 | |
| `earnings_snapshot.py` | ✅ 완성 | |
| `sector_intelligence.py` | ✅ 완성 | 20개 섹터 심층 분석 |
| `sector_analysis_engine.py` | ✅ 완성 | 섹터별 playbook 스코어링 |
| `sector_macro.py` | ✅ 완성 | 섹터별 매크로 지표 포맷 |
| `sector_valuation.py` | ✅ 완성 | 섹터별 가치평가 지표 |

### 시장 스크리닝

| 파일 | 상태 | 비고 |
|------|------|------|
| `daily_alpha.py` | ✅ 완성 | 70점 게이트, ATR 무효화, 감성 RSS fallback |
| `surge_alert.py` | ✅ 완성 | 5분봉, 카탈리스트 규명, 미반영 갭 LONG/SHORT |
| `price_alert.py` | ✅ 완성 | 목표가/무효화가 DB 추적, 30분 주기 |
| `supply_chain_alpha.py` | ✅ 완성 | 29개 체인 규칙, 16개 산업 |
| `order_backlog.py` | ✅ 완성 | DART/EDGAR/yfinance/정적 데이터, 3차 체인티어 |
| `theme_board.py` | ✅ 완성 | |
| `scenario_alpha.py` | ✅ 완성 | 9종 시나리오, reason_quality 게이트 |

### 매크로·섹터 분석

| 파일 | 상태 | 비고 |
|------|------|------|
| `macro_pulse.py` | ✅ 완성 | **금리 변화 bp 단위** — % 단위 혼용 주의 |
| `external_indicators.py` | ✅ 완성 | |
| `ecos_client.py` | ✅ 완성 | |
| `sector_cycle.py` | ✅ 완성 | 13개 사이클 |
| `economic_calendar.py` | ✅ 완성 | |
| `calendar_score_policy.py` | ✅ 완성 | |

### 뉴스·감성·공시 수집

| 파일 | 상태 | 비고 |
|------|------|------|
| `rss_collector.py` | ✅ 완성 | PR Newswire·GlobeNewswire·BusinessWire·GoogleNews |
| `finnhub_client.py` | ✅ 완성 | |
| `opendart_client.py` | ✅ 완성 | |
| `sec_client.py` | ✅ 완성 | 8-K + full-text 검색, User-Agent 필수 |
| `recent_issue_collector.py` | ✅ 완성 | |
| `headline_cleaner.py` | ✅ 완성 | |
| `polarity.py` | ✅ 완성 | |
| `evidence.py` | ✅ 완성 | |
| `evidence_ranker.py` | ✅ 완성 | |
| `catalyst_classifier.py` | ✅ 완성 | |
| `source_quality.py` | ✅ 완성 | |

### 관계 그래프

| 파일 | 상태 | 비고 |
|------|------|------|
| `relation_feed.py` | ✅ 완성 | 유니버스 US 100+·KR 100+ |
| `relation_seed_importer.py` | ✅ 완성 | 23개 섹터 1220 엣지 |
| `relation_fallback.py` | ✅ 완성 | lead-lag 자체 계산 |
| `relation_graph.py` | ✅ 완성 | |
| `relation_miner.py` | ✅ 완성 | |
| `alias_audit.py` | ✅ 완성 | |
| `universe_audit.py` | ✅ 완성 | |

### 4H 어드바이징 (integration 브랜치 신규)

| 파일 | 상태 | 비고 |
|------|------|------|
| `advisory_policy.py` | ✅ 완성 | score≥90+direct_ev=URGENT, ≥70=ACTION/WATCH |
| `risk_advisor.py` | ✅ 완성 | 매크로 기반 리스크 노출, LightGBM optional |
| `advisor_4h.py` | ✅ 완성 | 4H 파이프라인 오케스트레이터 |

### 4H 브리핑·포트폴리오·주간

| 파일 | 상태 | 비고 |
|------|------|------|
| `briefing.py` | ✅ 완성 | 8개 섹션 구조 |
| `mock_portfolio.py` | ✅ 완성 | 실주문 아님 |
| `weekly.py` | ✅ 완성 | |
| `weekly_cycle_orchestrator.py` | ✅ 완성 | |
| `live_pair_watch.py` | ✅ 완성 | 선행·후행 페어 추적 |
| `alpha_review.py` | ✅ 완성 | |
| `watchlist.py` | ✅ 완성 | |

### 파이프라인·품질

| 파일 | 상태 | 비고 |
|------|------|------|
| `pipeline.py` | ✅ 완성 | |
| `deterministic_report.py` | ✅ 완성 | |
| `local_data.py` | ✅ 완성 | 상관관계 CSV |
| `dedupe.py` | ✅ 완성 | |
| `trade_phrase_cleaner.py` | ✅ 완성 | |
| `ollama_client.py` | ✅ 완성 | polish-only, optional |
| `clinical_pipeline.py` | ✅ 완성 | 바이오 임상 파이프라인 |
| `top_mover_miner.py` | ✅ 완성 | |

---

## 2. 미구현 (우선순위 기준)

| 기능 | 우선순위 | 예정 파일 |
|------|----------|-----------|
| 이슈-주가 선반영 감지기 | 🔴 P1 | `mispricing_detector.py` |
| 수혜주 자동 라우팅 강화 | 🔴 P1 | `supply_chain_alpha.py` 확장 |
| M&A / 자사주 공시 감시 | 🟡 P2 | `corporate_action_watcher.py` |
| 자기개선 가중치 조정 | 🟡 P2 | `weight_optimizer.py` |
| 섹터별 가치평가 강화 | 🟠 P3 | `sector_valuation.py` 확장 |

---

## 3. 알림 통합 정책 (현재 상태)

| 알림 종류 | 현재 | 목표 |
|-----------|------|------|
| surge-scan | 30분 독립 발송 | score<90 → 4H 브리핑 섹션5로 흡수 |
| price-alert | 30분 독립 발송 | score<90 → 4H 브리핑 섹션6으로 흡수 |
| daily-alpha | 별도 발송 | 4H 브리핑 섹션3·4로 흡수 |
| weekly | 일요일 23:00 | 유지 |
| 4H 브리핑 | 4H마다 | 유지 (내용 강화 중) |

---

## 4. 보안 점검 현황 (2026-05-19)

| 항목 | 상태 |
|------|------|
| `.env.local` → .gitignore | ✅ |
| `*.session` → .gitignore | ✅ |
| `data/*.db` / `data/*.sqlite` → .gitignore | ✅ |
| `data/private/` → .gitignore | ✅ |
| API 키 하드코딩 없음 (settings.py env 변수만) | ✅ |
| 투자 금지 표현 필터 (`trade_phrase_cleaner.py`) | ✅ |
| 면책 문구 필수 포함 | ✅ |

---

## 5. systemd 타이머 목록 (49개 파일: 24 timer + 25 service)

> 실제 `systemd/` 디렉토리 파일 기준 (2026-05-26 확인)

```
tele-quant-inbound-bot.service              상시 데몬 (수신봇, timer 없음)
tele-quant-briefing-kr.{service,timer}      KR 4H 브리핑
tele-quant-briefing-us.{service,timer}      US 4H 브리핑
tele-quant-alpha-review-kr.{service,timer}  KR LONG/SHORT 후보
tele-quant-alpha-review-us.{service,timer}  US LONG/SHORT 후보
tele-quant-surge-scan-kr.{service,timer}    KR 30분 급등 감지
tele-quant-surge-scan-us.{service,timer}    US 30분 급등 감지
tele-quant-price-alert.{service,timer}      30분 목표가 알림
tele-quant-backlog-kr.{service,timer}       KR 수주잔고
tele-quant-backlog-us.{service,timer}       US 수주잔고
tele-quant-backlog-report.{service,timer}   수주잔고 리포트
tele-quant-pair-watch-cleanup.{service,timer} 페어워치 정리
tele-quant-pre-market-kr.{service,timer}    KR 장 전 브리핑
tele-quant-weekend-macro.{service,timer}    주말 매크로
tele-quant-weekly.{service,timer}           일요일 23:00 주간 리뷰
tele-quant-cycle-maintenance.{service,timer}     DB 유지보수
tele-quant-cycle-monday-open.{service,timer}     월요일 오픈 루틴
tele-quant-cycle-sunday-review.{service,timer}   일요일 사이클 리뷰
tele-quant-cycle-surge-collector.{service,timer} 급등 수집
tele-quant-cycle-weekday-4h.{service,timer}      평일 4H 사이클
tele-quant-cycle-weekend-issue.{service,timer}   주말 이슈 수집
tele-quant-daily-alpha-kr.{service,timer}        KR daily alpha
tele-quant-daily-alpha-us.{service,timer}        US daily alpha
tele-quant-bulk-refresh.{service,timer}          유니버스 일괄 갱신
tele-quant-universe.{service,timer}              유니버스 업데이트
```

---

## 6. 파일 구조 (2026-05-19 실제 현황)

```
tele_quant/
├── src/tele_quant/                    # 83개 .py 파일
│   ├── [인프라] settings.py, db.py, models.py, stock_data_provider.py
│   ├── [I/O] inbound_bot.py, telegram_sender.py, telegram_client.py
│   ├── [분석] stock_snapshot.py, fundamentals.py, financial_quality.py
│   │          dcf_estimator.py, earnings_history.py, earnings_surprise.py
│   │          momentum_signals.py, investment_scorecard.py, ticker_resolver.py
│   │          tradingview.py, financial_sanity.py, earnings_snapshot.py
│   ├── [섹터] sector_intelligence.py, sector_analysis_engine.py
│   │          sector_macro.py, sector_valuation.py, sector_cycle.py
│   ├── [스크리닝] daily_alpha.py, surge_alert.py, price_alert.py
│   │             supply_chain_alpha.py, order_backlog.py, theme_board.py
│   │             scenario_alpha.py
│   ├── [매크로] macro_pulse.py, external_indicators.py, ecos_client.py
│   │            economic_calendar.py, calendar_score_policy.py
│   ├── [수집] rss_collector.py, finnhub_client.py, opendart_client.py
│   │          sec_client.py, recent_issue_collector.py, headline_cleaner.py
│   │          polarity.py, evidence.py, evidence_ranker.py, catalyst_classifier.py
│   ├── [관계] relation_feed.py, relation_seed_importer.py, relation_fallback.py
│   │          relation_graph.py, relation_miner.py, alias_audit.py, universe_audit.py
│   ├── [4H어드바이징] advisory_policy.py, risk_advisor.py, advisor_4h.py
│   ├── [브리핑] briefing.py, mock_portfolio.py, weekly.py
│   │            weekly_cycle_orchestrator.py, live_pair_watch.py
│   │            alpha_review.py, watchlist.py
│   └── cli/                           # CLI 패키지 (d1967d3에서 분리)
│
├── tests/                             # 121개 test 파일, 2361개 테스트
├── systemd/                           # 45개 파일 (22 timers + 22 services + 1)
├── docs/                              # HANDOVER.md, PROJECT_STATE.md, 기타
├── CLAUDE.md                          # AI 지시서 (최우선 읽기)
├── ONBOARDING.md                      # AI 온보딩 퀵스타트
└── pyproject.toml                     # uv 기반 빌드
```
