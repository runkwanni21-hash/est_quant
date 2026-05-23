# 추가 조사 프롬프트 — 01 AI 반도체 / HBM / 메모리 / 파운드리

아래 프롬프트를 새 대화창에 붙여서 누락 섹터를 보강하세요.

```text
당신은 한국주식과 미국주식의 수혜주·피해주·경쟁사·선행후행 관계를 조사하는 퀀터멘탈 리서치 에이전트입니다.

sector_id: ai_semiconductor_hbm_foundry
sector_name: AI 반도체 / HBM / 메모리 / 파운드리
as_of: 2026-05-17
window: 2026-02-17~2026-05-17

조사 범위:
- 미국: NVDA, AMD, AVGO, MU, TSM, ASML, ARM, MRVL, QCOM, INTC, SMCI 등
- 한국: 삼성전자, SK하이닉스, DB하이텍, HBM/메모리/파운드리 관련주
- 핵심 키워드: AI GPU, HBM, DRAM, NAND, 파운드리, CoWoS, advanced packaging, 메모리 가격, AI capex

해야 할 일:
1. 최근 3개월 가장 크게 움직인 US/KR source 종목 10~20개를 찾으세요.
2. 각 source별 수혜 후보 2개, 피해/부담 후보 2개, 경쟁/피어 후보 1~2개를 작성하세요.
3. relation_type, direction, expected_lag, confidence, rationale, evidence URL을 붙이세요.
4. 출력은 아래 YAML 형식만 사용하세요.

sector_relation_seeds:
  sector_id: ai_semiconductor_hbm_foundry
  sector_name: AI 반도체 / HBM / 메모리 / 파운드리
  as_of: "2026-05-17"
  window: "2026-02-17~2026-05-17"
  edges:
    - source_symbol: ""
      source_name: ""
      source_market: "US 또는 KR"
      source_reason: ""
      source_3m_move_pct: null
      target_symbol: ""
      target_name: ""
      target_market: "US 또는 KR"
      relation_type: "BENEFICIARY | VICTIM | SUPPLIER | CUSTOMER | PEER_MOMENTUM | COMPETITOR | AI_CAPEX_SPILLOVER | INPUT_COST_VICTIM"
      direction: "UP_LEADS_UP | UP_LEADS_DOWN | DOWN_LEADS_DOWN | DOWN_LEADS_UP"
      expected_lag: "same_day | next_session | 1d | 3d | 5d | 10d"
      confidence: "HIGH | MEDIUM | LOW"
      rationale: ""
      evidence:
        - title: ""
          url: ""
      trading_note: "1일~1개월 스윙 관점에서 후행 반응 관찰"

주의:
- 매수/매도 추천 금지.
- 상관관계는 인과관계가 아님.
- LOW confidence는 억지로 높이지 말 것.
- 한국 티커는 가능하면 000000.KS 또는 000000.KQ 형식으로 표기.
```
