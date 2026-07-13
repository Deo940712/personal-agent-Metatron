# CURRENT

Part: part-004
Slice: slice-001
Status: active
Design authority: `.beacon/parts/part-004/DESIGN.md`
TODO source: `.beacon/parts/part-004/TODO.md#part-004-slice-001-threads-sync-接入--skillsrunner`

## Goal

threads-sync vendored clone 進 skills/ + 執行器 runner.py（cursors/agent_runs 整合、
login_expired 偵測）。

## Allowed Scope

- [ ] `skills/threads_sync/`：clone Deo940712/threads-sync（pin commit）、VAULT_PATH 覆蓋探勘+接線
- [ ] `skills/runner.py`：跑 1-5 步驟、exit code 捕捉、cursors + agent_runs 寫入
- [ ] `tests/test_runner.py`：mock skill CLI 三路徑（成功/失敗/login_expired）

## Forbidden Scope

- 改 threads-sync 內部邏輯（黑箱；最多 config 覆蓋）
- curator / recall（slice-002/003）

## Files-scope

skills/**, tests/test_runner.py

## Expected Output

`python -m skills.runner threads_sync` 可跑（無 session → 優雅回報 login_expired）；
DB1 cursors 有 last_run 記錄。

## Verification Plan

- Unit: `python -m pytest tests/test_runner.py -q`
- Regression: `python -m pytest tests/ -q`（210 不壞）
- Manual QA: 真同步 — blocked（Playwright session 在原機器）

## Current Blockers

- 真 threads-sync 同步需原機器的 cookies/session（不 block 程式與 mock 測試）

## Recovery Incident

None
