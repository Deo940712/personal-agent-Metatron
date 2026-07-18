# CURRENT

Status: active
Part: part-011（收尾接線 + 文件 + 回歸測試）
Slice: part-011-slice-001 — advisor 降頻 + world-diff 知識訊號（todo 5-6）

## Context

part-011-slice-000 已完成歸檔（`.beacon/done/part-011/`）：作息迴圈接線完成
（820 tests，死程式碼 extract_routine 復活）。

## Goal

校準閉環收尾（todo 5：advisor 降頻）+ part-008↔009 接線（todo 6：world-diff
new_knowledge 訊號）。

Design authority: `.beacon/parts/part-011/DESIGN.md`
Slice map: `.beacon/parts/part-011/TODO.md`

## Allowed scope

- [ ] todo 5：`advisor.push_candidates` 過濾穩定 ignore 的 dedup_key
- [ ] todo 6：`advisor.observe` world-diff 加 new_knowledge（scout untrusted inbox
      count-only，防注入）

Files-scope: core/advisor.py, tests/test_advisor.py, tests/test_advisor_push.py,
.beacon/parts/part-011/**, .beacon/CURRENT.md

## Forbidden scope

- 新 part/表/job；繞過 writer；把 untrusted note 內文餵進 advice；gate-locked backlog

## Verification target

- Unit: `python -m pytest tests/test_advisor.py tests/test_advisor_push.py -q`
- Regression: `python -m pytest tests/ -q`（基線 820）

## Done gate

降頻 + new_knowledge 測綠；全綠。
