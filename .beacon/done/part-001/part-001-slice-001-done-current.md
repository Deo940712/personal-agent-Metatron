# DONE: part-001-slice-001 專案骨架 + config.py + DB1 schema

Completed: 2026-07-13
Design authority: `.beacon/parts/part-001/DESIGN.md`(DDL 權威:ARCHITECTURE.md §5.1)

## 交付物

- `pyproject.toml` — uv 格式、Python 3.11+、pytest dev group
- `config.py` — DATA_DIR / STATE_DB / VAULT_PATH / INDEX_DB / TRANSCRIPT_DIR + 秘密走 *_ENV
- `core/stm.py` — 六張表 DDL(IF NOT EXISTS → 天然 idempotent)+ `init` 子命令 + connect(WAL)
- `tests/test_schema.py` — 13 個測試
- `.gitignore` — 排除 data/ 與秘密

## Verification Evidence

UnitTestCore command: (uv 未安裝,以系統 Python 直跑等效命令)

Automated commands:
- command: `python -m pytest tests/test_schema.py -q`(Python 3.12.4 / pytest 7.4.4)
- result: **13 passed** — 六表存在、欄位對齊 §5.1、init idempotent、建父目錄、
  CHECK 約束(agent_runs.trigger / tasks.status / events.state)、events 預設值
  (health=1.0, immune=0, state=alive)、remind partial index 被查詢計畫使用、
  cursors 複合主鍵去重

Manual QA:
- item: `python -m core.stm init` 跑兩次
- status: passed
- evidence: 兩次皆輸出 `OK: C:\Users\tcart\my-agent-data\state.db tables=[六表]`,
  第二次 no-op 不報錯;sqlite_master 查驗 schedule DDL 與 §5.1 一致

Incidents:
- none

## Deviations

- uv 未安裝於本機 → 驗證以系統 Python 3.12 + pytest 7.4 直跑(測試不依賴 pytest 8 特性)。
  pyproject.toml 仍為 uv 格式,安裝 uv 後 `uv sync && uv run pytest` 即可接手。
- 測試 DDL 斷言修正一處:pytest fixture 名 `db` 與參數化並用。
