# CURRENT

Status: active
Part: part-011（收尾接線 + 文件 + 回歸測試）
Slice: part-011-slice-000 — 作息迴圈接線（completed → routine facet → advisor）

## Context

所有規劃 part（001-010）完成。part-011 補既有 part 之間留待後續的接線 + 文件漂移
+ 測試缺口。計畫權威：`.omo/plans/next-phase-wiring-qa.md`（8 todo，已 gap 分析）。
注意：本 part-011 是收尾接線，與 PLAN backlog 的 MiroFish part-011 不同。

## Goal

補完 routine 迴圈根因（todo 1-4）：完成事件 → extract_routine → routine facet →
advisor 偏離偵測 → 建議。死程式碼 extract_routine 從此有 caller。

Design authority: `.beacon/parts/part-011/DESIGN.md`
Slice map: `.beacon/parts/part-011/TODO.md`

## Allowed scope

- [x] todo 1：writer done → completed 事件 + transcript source_id（5 tests 綠）
- [ ] todo 2：consolidate 尾端 window-read completed → extract_routine → routine facet
- [ ] todo 3：advisor routine-deviation 讀真 completed 事件端到端測
- [ ] todo 4：routine loop 整合測

Files-scope: core/writer.py, core/consolidate.py, tests/test_completed_event.py,
tests/test_facets_pipeline.py, tests/test_advisor.py, tests/test_routine_loop.py,
.beacon/parts/part-011/**, .beacon/CURRENT.md

## Forbidden scope

- 新 part/表/job；繞過 writer；gate-locked backlog；Task Capsule B 重測；真環境 QA

## Verification target

- Unit: `python -m pytest tests/test_completed_event.py tests/test_facets_pipeline.py tests/test_routine_loop.py -q`
- Regression: `python -m pytest tests/ -q`（基線 807）

## Done gate

extract_routine 有 caller；端到端 routine loop 測綠；全綠。
