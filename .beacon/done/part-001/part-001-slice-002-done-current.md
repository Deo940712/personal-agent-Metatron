# DONE: part-001-slice-002 stm.py CRUD + CLI

Completed: 2026-07-13
Design authority: `.beacon/parts/part-001/DESIGN.md`

## 交付物

- `core/stm.py` 擴充:
  - schedule:add / list(active 過濾,--all 全列)/ set_status
  - tasks:add / list(預設未完結含 waiting_user)/ set_status
  - projects:set(upsert by name,部分更新保留舊值)/ show(blockers JSON 解回 list)
  - cursors:get / set(UPSERT)
  - events:append(source_ids/immune)/ query(只查 alive——§4.1 遺忘語意)
  - 時間輔助:parse_when(ISO 本地時區或 epoch)/ fmt_when
  - CLI:全域 --db + schedule/tasks/projects 三領域動詞;done 找不到 → exit code 1
- `tests/test_crud.py` — 15 個測試(合計 28)

## Verification Evidence

UnitTestCore command: (uv 未安裝,等效直跑)

Automated commands:
- command: `python -m pytest tests/ -q`
- result: **28 passed**(13 schema + 15 CRUD)——三領域 roundtrip、status 過濾語意、
  projects 部分更新不覆蓋、cursors UPSERT、events 只回 alive、immune 落庫、
  CLI subprocess 全動詞、**跨行程測試:process A 寫入 → process B 讀到(Phase 1 gate)**

Manual QA:
- item: 真實 DB(config.STATE_DB)CLI 新增行程/待辦/專案各一筆,查詢、標記 done
- status: passed
- evidence: `schedule add/list/done`、`tasks add/list/done`、`projects set/show`
  全部如預期;中文標題與時間格式化正確;done 後 active 清單消失、--all 可見

Incidents:
- none

## Deviations / 發現

- Windows 子行程 stdout 預設 cp950 → 測試以 `PYTHONUTF8=1` 環境變數強制 UTF-8。
  **記入 ops 教訓候選**:channels/(Discord bot 等)呼叫子行程時同樣要帶此設定。

## Part-001 Phase 1 Gate 判定

- ✅ CLI 可增查改行程/待辦/專案
- ✅ init idempotent
- ✅ 跨行程測試證明狀態僅經 DB1
**→ part-001 完成,Phase 1 gate 通過。**
