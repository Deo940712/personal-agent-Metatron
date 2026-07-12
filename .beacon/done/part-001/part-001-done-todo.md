# part-001 TODO

Design authority: .beacon/parts/part-001/DESIGN.md

## SLICE Map

### part-001-slice-001: 專案骨架 + config.py + DB1 schema

Status: done (2026-07-13; snapshot: `.beacon/done/part-001/part-001-slice-001-done-current.md`)

Goal: 建立 uv 專案骨架、config.py、state.db schema 與初始化。

Outcome: `python -m core.stm init` 在 `DATA_DIR` 建出含六張表的 state.db。

Candidate scope:
- [ ] `pyproject.toml`（uv、Python 3.11+、pytest）
- [ ] `config.py`：`DATA_DIR`, `STATE_DB`, `VAULT_PATH`
- [ ] `core/stm.py`：schema DDL（六張表，含 events 的 source_ids/health 欄位）+ `init` 子命令
- [ ] `.gitignore`：排除 `data/`
- [ ] pytest：schema 建立測試（六張表存在、欄位正確）

Forbidden scope:
- CRUD 邏輯（slice-002）
- LLM / vault / sync 相關任何程式碼

Verification target:
- Unit: `uv run pytest tests/test_schema.py -q`
- Regression: 無（首個 slice）
- Manual QA: 執行 init 後以 sqlite3 檢視表結構

Done gate:
- init 為 idempotent（跑兩次不報錯、不重建）
- pytest 綠

### part-001-slice-002: stm.py CRUD + CLI

Status: done (2026-07-13; snapshot: `.beacon/done/part-001/part-001-slice-002-done-current.md`)

Goal: schedule / tasks / projects 三領域的 typed CRUD 與 CLI 動詞。

Outcome: `python -m core.stm schedule add/list/done`、`tasks ...`、`projects set/show` 可用。

Candidate scope:
- [ ] `core/stm.py` CRUD 函式（三領域 + cursors get/set + events append/查詢）
- [ ] argparse CLI 子命令
- [ ] pytest：每表 create/read/update/list-by-status roundtrip
- [ ] 跨行程測試：subprocess A 寫入 → subprocess B 讀到

Forbidden scope:
- 健康值代謝/封存邏輯的執行（欄位存在即可，job 在 part-003）
- 任何 LLM 呼叫

Verification target:
- Unit: `uv run pytest tests/ -q`
- Regression: slice-001 schema 測試仍綠
- Manual QA: CLI 新增行程/待辦/專案進度各一筆，重開行程查詢確認持久化

Done gate:
- 跨行程測試證明狀態僅經 DB1 接續
- 全部 pytest 綠 + 手動 QA passed
