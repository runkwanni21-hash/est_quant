# Claude Code 전달 프롬프트 — sector relation seeds import

중요: 이번 작업 대상은 est_quant가 아니라 modoo다.

repo:
https://github.com/runkwanni21-hash/modoo.git

branch:
integration/rebuild-modoo-advisor

업로드된 패키지:
modoo_sector_relation_seed_package_2026-05-17.zip

패키지 요약:
- 커버 섹터: 23/24
- 누락 섹터: 1개
- relation edges: 1216개
- factor_edges: 4개
- HIGH/MEDIUM/LOW: 139/626/455
- 한국 6자리 티커 접미사 보정 필요: 530건

가장 중요한 결론:
- 완전 중복 sector_id는 없음.
- 누락된 핵심 섹터는 `ai_semiconductor_hbm_foundry` 1개.
- `semicap_equipment_materials_osat`에 HBM/메모리 source가 일부 있지만, NVDA/AMD/AVGO/MU/TSM/ASML 중심 AI 반도체 대장 섹터 파일은 별도로 필요.

절대 주의:
- est_quant에 push 금지.
- force push 금지.
- .env.local, token, chat_id, session, DB, data/private, logs 커밋 금지.
- 매수·매도 확정 표현 금지.
- “상관관계는 인과관계가 아님” 문구 유지.
- LOW confidence는 active=false 또는 watch_only.
- evidence URL 없는 HIGH는 금지.
- 한국 bare ticker는 반드시 `.KS/.KQ`로 resolver를 통해 보정.

1. 패키지 복사

아래처럼 압축을 풀고 프로젝트 내부로 복사하라.

```bash
cd ~/projects/quant_spillover/tele_quant
mkdir -p /tmp/modoo_sector_package
unzip -o /path/to/modoo_sector_relation_seed_package_2026-05-17.zip -d /tmp/modoo_sector_package

mkdir -p data/research/sector_relation_seeds
mkdir -p docs/relation_research

cp -R /tmp/modoo_sector_package/data/research/sector_relation_seeds/*.yml data/research/sector_relation_seeds/
cp -R /tmp/modoo_sector_package/docs/relation_research/*.md docs/relation_research/
```

2. Git 상태 확인

```bash
git status
git remote -v
git branch -a -vv
git log --oneline --decorate -10
```

확인:
- 현재 repo가 modoo인지
- 현재 branch가 integration/rebuild-modoo-advisor인지
- est_quant remote가 origin이면 중단하고 remote 정리

3. Import CLI 추가

새 CLI를 추가하라.

```bash
uv run tele-quant relation-import-sector-seeds --dir data/research/sector_relation_seeds --dry-run
uv run tele-quant relation-import-sector-seeds --dir data/research/sector_relation_seeds --save
```

구현 파일 후보:
- src/tele_quant/relation_seed_importer.py
- src/tele_quant/cli.py
- src/tele_quant/db.py
- tests/test_relation_seed_importer.py

동작:
- `sector_manifest.yml`은 manifest로만 읽고 import 대상에서 제외.
- 각 `*.yml`의 `sector_relation_seeds.edges`와 `factor_edges`를 읽는다.
- edges는 relation_edges DB에 저장한다.
- factor_edges는 별도 factor relation으로 저장하거나 source_market=`FACTOR`/`COMMODITY`로 저장하되 audit에서 개별주와 구분한다.

4. Symbol normalization

필수:
- KR symbol이 `005930`처럼 6자리 bare code면 resolver로 `.KS` 또는 `.KQ` 보정.
- 보정 확신이 없으면 `symbol_needs_resolution=true` 또는 audit MEDIUM으로 표시.
- 기존 relation_feed, ticker_aliases, pykrx/FinanceDataReader/market listing을 우선 사용.
- 임의로 전부 `.KS` 붙이지 말 것. KOSDAQ은 `.KQ`가 필요.

5. Confidence/active policy

- HIGH/MEDIUM: active=true 가능
- LOW: active=false 또는 watch_only=true
- evidence_url 없는 HIGH: HIGH 금지, MEDIUM 이하로 강등하거나 audit HIGH
- source_3m_move_pct=null: price_backfill_required=true
- evidence placeholder/citation only: evidence_backfill_required=true

6. Dedupe / audit

중복 기준:
- source_symbol + target_symbol + relation_type + direction

필수 제거:
- self-loop
- 빈 symbol
- source/target 둘 다 같은 회사명
- ETF/지수/crypto가 개별주 edge로 섞인 경우
- 짧은 티커/브로커 오탐

relation-audit 보강:
```bash
uv run tele-quant relation-audit --fail-on-high
```

추가 검사:
- bare KR ticker 남아 있음
- HIGH인데 evidence_url 없음
- LOW인데 active=true
- factor edge가 stock edge로 섞임
- relation_type/direction 값이 enum 밖
- expected_lag 값이 허용값 밖

7. stock_snapshot.py 연결

`/분석 티커` 결과에 relation seed를 활용하라.

필수 표시:
- 수혜 후보 3개
- 피해/부담 후보 3개
- 경쟁/피어 후보 3개
- 각 후보의 confidence, expected_lag, relation_type
- 단, “확정 수혜/피해” 표현 금지

8. relation_follow.py 연결

source가 시가총액 규모 대비 의미 있는 급등/급락을 하면 target을 추적하라.

규모별 임계치:
- US Mega/M7급: +5~10%
- US Large: +8~15%
- US Mid: +10~20%
- US Small: +20~30%
- KR 초대형: +5~10%
- KR 대형: +8~15%
- KR 중형: +10~20%
- KR 소형: +20~30%
- KR 초소형: 상한가/작전주 주의, +30% 근처

target 조건:
- stock_snapshot의 swing_score >= 65
- accumulation_score >= 60 또는 거래량/OBV/눌림 패턴 양호
- 1D~1M 관점에서 5% 기대 보상 구간이 너무 멀지 않음

출력 표현:
- “관찰 후보”
- “후행 반응 확인 중”
- “거래량/OBV 축적 패턴”
- “5% 기대 보상 구간”

금지:
- “매수 권장”
- “확정 수익”
- “세력 매집 확정”

9. 검증 명령

```bash
uv run ruff check .
uv run pytest
uv run pytest tests/test_relation_seed_importer.py -q
uv run tele-quant relation-import-sector-seeds --dir data/research/sector_relation_seeds --dry-run
uv run tele-quant relation-import-sector-seeds --dir data/research/sector_relation_seeds --save
uv run tele-quant relation-audit --fail-on-high
uv run tele-quant relation-report --top-n 30 --no-send | tee /tmp/sector_relation_report.log
uv run tele-quant output-lint --file /tmp/sector_relation_report.log --fail-on-high
```

금지 grep:
```bash
grep -E "매수 권장|매도 권장|확정 수익|수익 보장|자동매매|실계좌 주문|반드시 상승|세력 매집 확정|기관 매집 확정|수혜 확정|피해 확정|상관관계.*인과" /tmp/sector_relation_report.log
```

결과가 비어야 함.

10. 누락 섹터 처리

현재 누락:
- `ai_semiconductor_hbm_foundry`

`docs/relation_research/MISSING_SECTOR_PROMPT_ai_semiconductor_hbm_foundry.md`를 사용해 추가 조사한 뒤, 아래 파일로 저장:

```text
data/research/sector_relation_seeds/01_ai_semiconductor_hbm_foundry.yml
```

11. 커밋

검증 통과 후:

```bash
git status
git diff --stat
git diff
```

권장 커밋 메시지:
```text
feat: sector relation seed import package
```

push는 modoo integration 브랜치에만:
```bash
git push origin integration/rebuild-modoo-advisor
```

12. 완료 보고

- repo:
- branch:
- imported sector files:
- imported relation edges:
- active HIGH/MEDIUM:
- LOW/watch_only:
- bare KR ticker resolved:
- unresolved symbols:
- duplicate merged:
- self-loop removed:
- factor_edges 처리:
- relation-audit result:
- output-lint result:
- ruff result:
- pytest result:
- commit SHA:
