# CURRENT

Part: part-020
Slice: slice-003
Status: active — promoted 2026-08-03 after slice-002 verification and audit
Design authority: `.beacon/parts/part-020/DESIGN.md`
TODO source: `.beacon/parts/part-020/TODO.md#slice-003`

## Goal

Establish non-destructive backup, restore, and doctor procedures using disposable paths, with measurable RPO/RTO evidence and no production data mutation.

## Allowed Scope

- [ ] Add `scripts/backup.py` (new) for explicit source/output paths.
- [ ] Add `scripts/restore.py` (new) for explicit backup/target paths.
- [ ] Add `scripts/doctor.py` (new) to inspect DB integrity and required tables.
- [ ] Add `docs/OPERATIONS.md` (new) documenting the drill, RPO/RTO, and production-path guardrails.

## Files-scope

- `scripts/backup.py` (new)
- `scripts/restore.py` (new)
- `scripts/doctor.py` (new)
- `docs/OPERATIONS.md` (new)

## Forbidden Scope

- Do not modify runtime application modules or DB schema.
- Do not read, overwrite, corrupt, or restore production DB1, vault, transcript, or index paths.
- Do not modify Windows Task Scheduler or daemon plans.
- Do not alter `.beacon/CURRENT.md` outside this active slice status and evidence.

## Verification Plan

- Unit/regression: `python -m pytest tests/ -q`.
- Operational QA: create `.tmp/part-020-slice-003/` disposable fixture; run backup with explicit source/output, corrupt only disposable source, restore to disposable target, run doctor, and measure elapsed backup/restore seconds as RTO evidence.
- Safety QA: assert production `config.STATE_DB`, `config.VAULT_PATH`, `config.INDEX_DB`, and `config.TRANSCRIPT_DIR` are rejected as source/target paths; clean the disposable fixture afterward.

## Done Gate

- Backup, restore, and doctor commands pass on disposable fixtures.
- RPO/RTO measurements and production-path rejection are documented in verification evidence.
- Full regression passes; no production path was touched.
