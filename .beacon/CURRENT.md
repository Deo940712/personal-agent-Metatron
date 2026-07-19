# CURRENT

Status: active
Part: part-011（收尾接線 + 文件 + 回歸測試）
Slice: part-011-slice-002 — 文件同步 + golden queries（todo 7-8）

## Context

part-011-slice-000/001 已完成歸檔（`.beacon/done/part-011/`）：
- slice-000：作息迴圈接線（820 tests，extract_routine 復活）
- slice-001：advisor 降頻 + world-diff new_knowledge（826 tests）

## Goal

文件反映 part-010 + 三接線（routine loop / down-throttle / new_knowledge）；
記憶檢索品質回歸防護（golden queries，backlog-007）。

Design authority: `.beacon/parts/part-011/DESIGN.md`
Slice map: `.beacon/parts/part-011/TODO.md`

## Allowed scope

- [ ] todo 7：ARCHITECTURE §15 標 part-010 已實作 + §5.1 scenarios 澄清 + 目錄樹
      scenario.py/crowd_scenario_vendor + `core.scenario` CLI + 三接線註記；
      README(zh+en) 進度加 part-010 + 更新 test 數；CheckMemoryDocs 綠
- [ ] todo 8：`tests/test_golden_queries.py`（15 筆記 / 20 斷言，確定性）；
      BACKLOG-007 標進度

Files-scope: ARCHITECTURE.md, README.md, README-en.md, docs/TOOLS.md,
tests/test_golden_queries.py, .beacon/BACKLOG.md, .beacon/parts/part-011/**,
.beacon/CURRENT.md

## Forbidden scope

- 憑空編數字（讀實際 pytest 數）；改 memory 契約；gate-locked backlog

## Verification target

- Unit: `python -m pytest tests/test_golden_queries.py -q` + `python .beacon/verification/CheckMemoryDocs.py`
- Regression: `python -m pytest tests/ -q`（基線 826）

## Done gate

文件反映 part-010 + 接線；golden queries 綠；CheckMemoryDocs 綠；全綠。
