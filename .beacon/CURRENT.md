# CURRENT

Status: executable
Active part: part-018 Knowledge Base 2.0
Active slice: slice-001 Schema 定義與 Migration Script
Design: `.beacon/parts/part-018/DESIGN.md`

## Scope

建立 `note_type` frontmatter schema、deterministic migration script（標記 807 篇為 evidence）、5 篇 topic notes seed 檔案，以及 rollback 機制。

## Verification

- `python -m pytest tests/test_migrate_kb_2_0.py -q`（新增）
- `python -m pytest tests/ -q`（943 tests 必須維持通過）

## Files allowed

- `scripts/migrate_kb_2_0.py` (new)
- `core/ltm.py` (extend schema)
- `tests/test_migrate_kb_2_0.py` (new)
- `vault/semantic/topic/*.md` (5 seed topic notes)

## Done gate

Migration script 可執行 dry-run 無誤，943 tests 通過，rollback 機制可運作。
