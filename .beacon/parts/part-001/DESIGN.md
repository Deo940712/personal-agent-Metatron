# part-001 DESIGN

## Goal

建立專案基礎層：`config.py`（所有路徑/參數集中）、DB1（SQLite 短期記憶）schema、
`core/stm.py` 存取層，以及可增查改行程 / 待辦 / coding 進度的 CLI。

## Non-goals

- 不含 LLM 呼叫（part-002）
- 不含 DB2 / 向量索引 / 封存 job（part-003）
- 不含任何社交平台 sync（part-004）

## Assumptions

- Python 3.11+，uv 管理（沿用 threads-sync 技術棧）
- Windows 開發（PowerShell 5.1），之後可能移 Linux——路徑只進 config.py
- SQLite 單檔即可承載短期記憶量級（個人使用）
- `data/` 可能需移出 OneDrive 同步範圍以避免 SQLite 鎖檔（open question）

## Design Options

1. **單一 state.db，多表**（schedule / tasks / projects / cursors）— 簡單、與
   threads-sync store.py 模式一致。
2. 每領域一個 .db — 隔離好但管理成本高，個人量級不必要。

## Chosen Design

選項 1。**完整 DDL 為 ARCHITECTURE.md §5.1（設計權威，含全部欄位型態、CHECK
約束與索引），實作以該節為準。** 六張表摘要：

- `schedule` — 行程，免疫衰減；`reminded_at` 防重複提醒 + partial index；`rrule` 重複行程
- `tasks` — Working State；status 含 `waiting_user`
- `projects` — coding tracker；`repo_path` 供三源掃描；blockers 為 JSON array 字串
- `cursors` — 複合主鍵 (pipeline, key)
- `agent_runs` — 含 trigger/finished_at/error（斷點與靜默壞掉偵測）
- `events` — 情節緩衝；`source_ids`（回水）、`health`+`immune`（代謝）、`state`+`trashed_at`（狀態機）

`core/stm.py` 提供 typed CRUD；CLI 入口 `python -m core.stm <domain> <verb>`。
`config.py` 參數：`DATA_DIR`, `STATE_DB`, `VAULT_PATH`（先定義，part-003 才使用）。

## Verification Targets

- pytest：schema 建立、CRUD roundtrip、TTL 欄位語意
- 跨行程測試：process A 寫入 → process B 讀到（無共享記憶體）
- CLI 手動 QA：新增一筆行程與一個專案進度並查詢

## Unit Test Strategy

pytest + tmp_path 上的臨時 SQLite；不 mock sqlite3。每表至少：create / read /
update / list-by-status 各一測試。

## Manual QA Strategy

PowerShell 執行 CLI 新增行程、待辦、專案進度各一筆，重開行程查詢確認持久化。

## Risks

- OneDrive 同步 + SQLite WAL 檔案鎖衝突（可能需 `DATA_DIR` 指到 OneDrive 外）
- schema 過早固化——TTL/封存語意在 part-003 才會被真正驗證

## Open Questions

（已全部定案）

- `DATA_DIR` = `C:\Users\tcart\my-agent-data`（本地、OneDrive 外；使用者定案。
  後期遷 VPS 只改 config.py。空間量級：頭一年約 3–5 GB，圖片附件為大宗）
- 時間欄位 = UTC epoch int（定案）
