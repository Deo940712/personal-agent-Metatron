# CURRENT

Part: part-004.5
Slice: slice-002
Status: active
Design authority: `.beacon/parts/part-004.5/DESIGN.md`
TODO source: `.beacon/parts/part-004.5/TODO.md#part-0045-slice-002-矛盾偵測--supersede-執行mneme`

## Goal

preference 蒸餾前注入既有 profile；LLM 可輸出 supersedes；落地補 superseded_by；
recall 契約查詢邏輯。

## Allowed Scope

- [ ] `agents/consolidator.md`：preference 蒸餾輸入注入既有 profile INDEX；
      輸出可選 `supersedes` 欄位 + few-shot（矛盾情境）
- [ ] `core/consolidate.py`：supersedes 驗證（存在性+非已 superseded）
- [ ] `core/ltm.py` 或 `core/writer.py`：`mark_superseded(vault, old_id, new_id)`
- [ ] `agents/recall.md`：落地「查 superseded_by，優先引用新版，矛盾並列」規則
- [ ] `core/recall.py`：read_note 工具結果附帶 superseded_by 提示（若有）
- [ ] pytest：supersede 落地、驗證攔截（指不存在/已被 superseded 的 id）、
      recall 讀到 superseded_by 的行為

## Forbidden Scope

- RRF（slice-003）

## Files-scope

agents/consolidator.md, agents/recall.md, core/consolidate.py, core/ltm.py, core/writer.py, core/recall.py, tests/test_consolidate.py, tests/test_recall.py

## Expected Output

蒸餾出「偏好改變」的新事實 → 舊 profile 筆記被標記 superseded_by，不刪；
recall 讀到會提醒有更新版。

## Verification Plan

- Unit: `python -m pytest tests/test_consolidate.py tests/test_recall.py -q`
- Regression: `python -m pytest tests/ -q`（262 不壞）

## Current Blockers

None

## Recovery Incident

None
