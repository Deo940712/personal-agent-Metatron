# CURRENT

Status: executable
Active part: part-018 Knowledge Base 2.0
Active slice: slice-002 檢索邏輯降級（Zerachiel/Retrieve）
Design: `.beacon/parts/part-018/DESIGN.md`

## Completed

- slice-001: KB 2.0 migration script（`scripts/migrate_kb_2_0.py`）+ 8 tests
  - Dry-run 驗證：807 evidence notes, 5 topic notes
  - 處理 malformed YAML frontmatter
  - Rollback 機制可運作
  - 951 tests 通過

## Scope (slice-002)

修改檢索邏輯，預設只搜尋 topic notes，evidence 降級為佐證連結。

## Verification

- `python -m pytest tests/test_retrieve_topic_first.py -q`（新增）
- `python -m pytest tests/ -q`（951 tests 必須維持通過）

## Files allowed

- `core/retrieve.py` (modify)
- `core/vindex.py` (modify rebuild/upsert to filter note_type)
- `core/tools/memory.py` (add include_evidence flag)
- `tests/test_retrieve_topic_first.py` (new)

## Done gate

搜尋「AI 開源工具」只回傳 topic note，不回傳 9 篇原始貼文；`include_evidence=True` 時可搜尋原始貼文（向後相容）。
