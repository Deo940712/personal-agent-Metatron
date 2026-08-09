# part-020 slice-003 Verification

## Result

PASS — non-destructive backup, restore, and doctor drill verified.

## Evidence

- Disposable fixture: `.tmp/part-020-slice-003/` only.
- `doctor.py --db source.db`: healthy, integrity `ok`, all 11 required tables.
- `backup.py`: integrity `ok`, 122880 bytes, elapsed about 0.014 seconds.
- Source corruption followed by `restore.py`: integrity `ok`, 122880 bytes, elapsed about 0.018 seconds.
- Restored DB doctor: healthy, integrity `ok`, all required tables.
- Backup source under production DB1: rejected with `production_path_rejected`.
- Restore target under production DB1: rejected with `production_path_rejected`.
- Full regression: `python -m pytest tests/ -q` → **973 passed, 1 warning**.
- Cleanup: `.tmp/part-020-slice-003` removed; existence verified false.

## Adversarial audit

- production-path mutation: backup/restore guard rejected protected paths before operation.
- corrupted disposable source: restore used verified backup and recovered a healthy DB.
- stale/leftover fixture: unique disposable root was removed after the drill.
- read-only doctor: doctor inspected SQLite with `mode=ro`; no production write path was invoked.
