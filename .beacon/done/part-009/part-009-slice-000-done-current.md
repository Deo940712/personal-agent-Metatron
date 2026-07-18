# part-009-slice-000 — advices 表 + baseline checkpoint + world-diff 讀取器(done 2026-07-19)

Snapshot of CURRENT at completion.

## Goal(達成)

DB1 第十表 `advices` + baseline checkpoint(cursors 復用)+ 確定性 world-diff
讀取器。tick 機制成形:無變化 → quiet(零 LLM);有變化 → 結構化 diff。全確定性。

## Delivered

- `core/stm.py`:`advices` DDL(priority/observation/suggestion/evidence_ids/
  actions/state[pending|pushed|accepted|ignored|expired]/dedup_key/expires_at)+
  CRUD(advice_add/get/list/set_state/dedup_recent/count_since/expire_due)+
  CLI `advices list`
- `core/advisor.py`:
  - baseline checkpoint(cursors 'advisor'/'baseline_ts';get/advance;
    壞值 fallback 0)
  - `observe(db, now_ts) -> WorldDiff`:確定性讀取新增行程/逾期任務/停滯專案/
    routine 偏離(part-007 facet)/goal facet;`quiet` 屬性短路(零 LLM 判定)
- `tests/test_advisor.py`:33 tests(CRUD/state 機/CHECK 約束/dedup/count/expire/
  baseline roundtrip+壞值/world-diff 五訊號確定性重放/quiet 判定)

## Verification

- Unit: `python -m pytest tests/test_advisor.py tests/test_schema.py -q` → 33 passed
- Regression: `python -m pytest tests/ -q` → **706 passed**(基線 688 + 18)
- Manual QA(實跑):9 表舊庫 → `init` idempotent 升級 10 表;world-diff 正確偵測
  逾期任務 + 停滯專案;`advices list` 空表印 (empty)。

## Notes

- part-008(Knowledge Scout)未建:「新收知識」world-diff 訊號暫不接線。
- goal facet 失速判定 slice-000 為粗略(列出 active goal),精緻化留 slice-001 的
  reflect 上下文;不預先過度工程。
- 無 LLM、無推播、不改真實狀態——嚴守 §15.2「觀察與建議分離」。
