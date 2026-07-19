# part-011-slice-002 — 文件同步 + golden queries(done 2026-07-19)

Snapshot of CURRENT at completion.

## Goal(達成)

文件反映 part-010 + 三接線;記憶檢索品質回歸防護(backlog-007)。

## Delivered

- **todo 8** `tests/test_golden_queries.py`:15 筆種子筆記跨主題 + 24 條
  query→expected-hit 斷言(top-5 成員,非精確排名)+ count 守衛 + 負向鑑別力測;
  測 `retrieve.search`(不給 embed_fn → index+FTS,確定性、零 LLM/網路)。改索引/
  檢索邏輯必跑。BACKLOG-007 標 in-progress。(26 tests)
- **todo 7** 文件同步:
  - ARCHITECTURE §15 標 part-010 ✅ 全部已實作(778→852 tests);能力表 Scenario
    Rehearsal ✅;目錄樹加 `core/scenario.py` / `crowd_scenario_vendor/` / `tools/`;
    §5.2 vault 結構加 `scenarios/` 專區(非事實層說明)
  - docs/TOOLS.md 加 `scenario.rehearse` CLI
  - README(zh+en)進度加 part-010 + part-011,test 數 778→852,自適應層四塊完成

## Verification

- Unit: `python -m pytest tests/test_golden_queries.py -q` → 26 passed;
  `python .beacon/verification/CheckMemoryDocs.py` → OK
- Regression: `python -m pytest tests/ -q` → **852 passed**(基線 826 + 26)
- 殘留掃描:無 778 tests / 無「part-010 待 promote」

## Notes

- golden queries 斷 top-k 成員(非精確排名)——避免脆弱;負向測證明 harness 有
  鑑別力。cross-encoder rerank(backlog-025)觸發條件 = 此 harness 出排名問題。
