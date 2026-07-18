# part-011 TODO

Design authority: `.beacon/parts/part-011/DESIGN.md`
Plan authority: `.omo/plans/next-phase-wiring-qa.md`（8 todo，5 元件）

## SLICE Map

### part-011-slice-000: 作息迴圈接線（completed 事件 → routine facet → advisor）

Status: in-progress

Goal: 補完 routine 迴圈根因（todo 1-4）：完成事件 → extract_routine → routine facet
→ advisor 偏離偵測 → 建議。死程式碼 extract_routine 從此有 caller。

Candidate scope:
- [x] todo 1：`core/writer.py` done → `completed` 事件 + transcript source_id
      （cancel 不寫；state_change 保留）— 5 tests 綠
- [ ] todo 2：`core/consolidate.py` 尾端 window-read completed → extract_routine →
      routine facet via writer（durable transcript evidence）
- [ ] todo 3：advisor routine-deviation 讀真 completed 事件端到端測
- [ ] todo 4：routine loop 整合測（completed→facet→deviation→advice）

Files-scope: core/writer.py, core/consolidate.py, tests/test_completed_event.py,
tests/test_facets_pipeline.py, tests/test_advisor.py, tests/test_routine_loop.py,
.beacon/parts/part-011/**, .beacon/CURRENT.md

Verification target:
- Unit: `python -m pytest tests/test_completed_event.py tests/test_facets_pipeline.py tests/test_routine_loop.py -q`
- Regression: `python -m pytest tests/ -q`（基線 807）

Done gate: extract_routine 有 caller；端到端 routine loop 測綠；全綠

### part-011-slice-001: advisor 降頻 + world-diff 知識訊號（todo 5-6）

Status: planned

Goal: 校準閉環收尾 + part-008↔009 接線。

Candidate scope:
- [ ] todo 5：`advisor.push_candidates` 過濾穩定 ignore 的 dedup_key
- [ ] todo 6：`advisor.observe` world-diff 加 new_knowledge（scout untrusted inbox
      count-only，防注入）

Files-scope: core/advisor.py, tests/test_advisor.py, tests/test_advisor_push.py

Verification target:
- Unit: `python -m pytest tests/test_advisor.py tests/test_advisor_push.py -q`
- Regression: 全綠

Done gate: 降頻 + new_knowledge 測綠；全綠

### part-011-slice-002: 文件同步 + golden queries（todo 7-8）

Status: planned

Goal: 文件反映 part-010 + 三接線；記憶檢索品質回歸防護。

Candidate scope:
- [ ] todo 7：ARCHITECTURE/README/TOOLS 同步 part-010 + 接線
- [ ] todo 8：`tests/test_golden_queries.py`（15 筆記 / 20 斷言，backlog-007）

Files-scope: ARCHITECTURE.md, README.md, README-en.md, docs/TOOLS.md,
tests/test_golden_queries.py, .beacon/BACKLOG.md

Verification target:
- Unit: `python -m pytest tests/test_golden_queries.py -q` + CheckMemoryDocs
- Regression: 全綠

Done gate: 文件反映 part-010；golden queries 綠；CheckMemoryDocs 綠；全綠
