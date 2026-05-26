# Sector Relation Seeds Coverage Report

- 기준일: 2026-05-17
- 커버 섹터: 23/24
- 누락 섹터: 1
- 관계 edge: 1216개
- factor edge: 4개
- confidence: HIGH 139, MEDIUM 626, LOW 455
- 한국 티커 접미사 보정 필요: 530건

## 커버된 섹터
- 02. `semicap_equipment_materials_osat` — 반도체 장비 / 소재 / 부품 / OSAT / edges 65 / factor 0
- 03. `ai_software_cloud_cybersecurity` — AI 소프트웨어 / 클라우드 / SaaS / 사이버보안 / edges 56 / factor 0
- 04. `ai_power_grid_copper_nuclear` — 데이터센터 / AI 전력 / 변압기 / 전선 / 구리 / 원전 / edges 55 / factor 0
- 05. `biotech_pharma_clinical_medtech` — 바이오 / 제약 / 임상 / 의료기기 / edges 44 / factor 0
- 06. `cdmo_bioproduction_adc` — CDMO / 바이오 생산 / 항체·ADC / 위탁개발 / edges 50 / factor 0
- 07. `shipbuilding_shipping_lng_equipment` — 조선 / 해운 / LNG선 / 조선기자재 / edges 44 / factor 4
- 08. `defense_space_aerospace_drone` — 방산 / 우주 / 항공 / 드론 / edges 75 / factor 0
- 09. `auto_ev_autonomous_robotaxi` — 자동차 / EV / 자율주행 / 로봇택시 / edges 48 / factor 0
- 10. `battery_materials_lithium_recycling` — 배터리 / 양극재 / 음극재 / 리튬 / 재활용 / edges 60 / factor 0
- 11. `financials_banks_insurance_brokers` — 금융 / 은행 / 보험 / 증권 / 핀테크 / edges 60 / factor 0
- 12. `energy_oil_lng_renewables` — 에너지 / 정유 / LNG / 셰일 / 태양광 / 풍력 / edges 44 / factor 0
- 13. `materials_chem_steel_metals_rareearth` — 소재 / 화학 / 철강 / 비철 / 희토류 / edges 60 / factor 0
- 14. `construction_infra_reits_cement` — 건설 / 인프라 / 리츠 / 부동산 / 시멘트 / edges 50 / factor 0
- 15. `kbeauty_cosmetics_odm_consumer` — K뷰티 / 화장품 / ODM / 소비재 / edges 50 / factor 0
- 16. `retail_ecommerce_logistics_travel_airline_casino` — 유통 / 전자상거래 / 물류 / 여행 / 항공 / 카지노 / edges 48 / factor 0
- 17. `media_content_gaming_entertainment_ads` — 미디어 / 콘텐츠 / 게임 / 엔터 / 광고 / edges 44 / factor 0
- 18. `telecom_network_smartphone_equipment` — 통신 / 네트워크 / 스마트폰 / 통신장비 / edges 48 / factor 0
- 19. `food_agriculture_fertilizer_staples` — 음식료 / 농업 / 비료 / 필수소비재 / edges 50 / factor 0
- 20. `industrials_machinery_automation_robotics` — 산업재 / 기계 / 자동화 / 로봇 / 공장설비 / edges 65 / factor 0
- 21. `payments_crypto_exchange_brokerage` — 결제 / 카드 / 크립토 / 거래소 / 브로커리지 / edges 44 / factor 0
- 22. `healthcare_services_hospitals_diagnostics` — 헬스케어 서비스 / 병원 / 보험관리 / 진단 / edges 44 / factor 0
- 23. `environment_waste_water_carbon_infra` — 친환경 / 폐기물 / 수처리 / 탄소 / 환경 인프라 / edges 64 / factor 0
- 24. `macro_sensitive_rates_fx_commodities` — 매크로 민감주 / 금리·환율·원자재 수혜·피해 바스켓 / edges 48 / factor 0

## 누락 섹터
- 01. `ai_semiconductor_hbm_foundry` — AI 반도체 / HBM / 메모리 / 파운드리

## 중복/겹침 판정
- 완전 중복 sector_id는 발견하지 못했습니다.
- `biotech_pharma_clinical_medtech`와 `cdmo_bioproduction_adc`, `auto_ev_autonomous_robotaxi`와 `battery_materials_lithium_recycling`, `ai_power_grid_copper_nuclear`와 `energy_oil_lng_renewables`는 일부 종목/테마가 겹치지만 목적이 다른 보완 섹터로 보는 것이 맞습니다.
- `semicap_equipment_materials_osat`에 SK하이닉스/삼성전자/HBM 관련 edge가 일부 포함되어 있으나, `ai_semiconductor_hbm_foundry` 자체 섹터 파일은 아직 없습니다.

## Claude Code 적용 전 필수 정리
1. 한국 6자리 티커는 `.KS/.KQ` 접미사를 자동 보정해야 합니다.
2. `source_3m_move_pct: null` 항목은 top_mover_miner 또는 yfinance/pykrx로 가격 백필이 필요합니다.
3. evidence URL이 비어 있거나 citation placeholder인 항목은 LOW로 낮추거나 evidence_backfill 대상으로 분리해야 합니다.
4. LOW confidence는 active=false 또는 watch_only로 저장하는 것이 안전합니다.
5. factor_edges는 주식 relation_edges와 분리하거나 `source_market=FACTOR/COMMODITY`로 별도 처리해야 합니다.

## Parse errors
- 없음