# CURRENT

Part: part-004.5
Slice: slice-001
Status: active
Design authority: `.beacon/parts/part-004.5/DESIGN.md`
TODO source: `.beacon/parts/part-004.5/TODO.md#part-0045-slice-001-主題連續性蒸餾membox`

## Goal

蒸餾契約加 topic 欄位；consolidate 收尾自動連結近 30 天同主題筆記（Membox 輕量版）。

## Allowed Scope

- [ ] `agents/consolidator.md`：輸出 schema 加 `topic`（必填,<=30字）+ few-shot
- [ ] `core/consolidate.py`：`_validate_group` 第六條（topic）；寫筆記後掃近 30
      天同 topic episodic 筆記，雙向補 related
- [ ] pytest：topic 驗證 boundary；連結產生；無同主題時不連結；30 天窗口邊界

## Forbidden Scope

- supersede（slice-002）；RRF（slice-003）

## Files-scope

agents/consolidator.md, core/consolidate.py, tests/test_consolidate.py

## Expected Output

兩天各蒸餾出同主題筆記 → 自動產生雙向 related 連結。

## Verification Plan

- Unit: `python -m pytest tests/test_consolidate.py -q`
- Regression: `python -m pytest tests/ -q`（254 不壞）

## Current Blockers

None

## Recovery Incident

None
