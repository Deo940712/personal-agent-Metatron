# CURRENT

Part: part-020
Slice: slice-002
Status: active — promoted 2026-08-03 after slice-001 verification and audit
Design authority: `.beacon/parts/part-020/DESIGN.md`
TODO source: `.beacon/parts/part-020/TODO.md#slice-002`

## Goal

Prevent DB1 path footguns B7/B10: invalid internal paths must fail closed instead of silently creating an empty SQLite database, while explicit initialization remains idempotent.

## Allowed Scope

- [ ] Add an explicit path-safety mode to `core/stm.py` connection helpers; initialization remains the only path that may create a database.
- [ ] Ensure `existing_tables()` and internal read/write callers use the safe connection behavior without changing the DB schema.
- [ ] Add boundary regression tests in `tests/test_known_issues.py` and, if needed, `tests/test_db_path_safety.py` (new).
- [ ] Add `scripts/probes/probe_db_b7.py` (new) that checks missing/typo paths fail fast and no empty DB is created.

## Files-scope

- `core/stm.py`
- `tests/test_known_issues.py`
- `tests/test_db_path_safety.py` (new, only if needed)
- `scripts/probes/probe_db_b7.py` (new)

## Forbidden Scope

- Do not change DB1 schema or migrations.
- Do not modify vault, index, transcript, dashboard, daemon, or Windows Task Scheduler.
- Do not alter `.beacon/CURRENT.md` outside the active slice status and verification evidence.
- Do not change unrelated dirty files.

## Verification Plan

- Red: add boundary tests for a missing path and a typo path; confirm the current implementation creates an empty DB or otherwise fails the intended assertion.
- Unit: `python -m pytest tests/test_known_issues.py -q` and any new `python -m pytest tests/test_db_path_safety.py -q`.
- Regression: `python -m pytest tests/ -q`.
- Operational QA: `python scripts/probes/probe_db_b7.py --path "$env:TEMP\metatron-db-path-safety"`; assert non-zero/clear failure and assert the target file does not exist afterward.

## Done Gate

- Invalid non-initialization paths fail closed with a typed/clear error.
- `stm.init()` remains idempotent and is the only explicit creator path.
- Full regression passes and the operational probe proves no empty DB creation.
- B7/B10 status changes only with slice evidence; otherwise they remain open/planned.
