# Operations Runbook

This runbook covers the part-020 slice-003 DB1 backup, restore, and doctor drill. All commands run from the repository root and use explicit paths.

## Safety Model

- `scripts/backup.py` and `scripts/restore.py` reject any source, backup, output, or target path equal to or inside `config.STATE_DB`, `config.DATA_DIR`, `config.VAULT_PATH`, `config.INDEX_DB`, or `config.TRANSCRIPT_DIR`.
- `scripts/doctor.py` is read-only and opens SQLite with `mode=ro`; by default it may inspect production DB1 because diagnostics must not require copying production data.
- Add `--reject-production` to `scripts/doctor.py` when running safety probes that must prove protected paths are rejected.
- Restore is atomic: it writes a sibling temp DB, verifies SQLite integrity, then replaces the disposable target path.
- Backup refuses to overwrite an existing output file; restore refuses to overwrite an existing target unless `--overwrite` is explicit, and production targets are still never allowed.

## RPO/RTO Evidence

- RPO for this manual drill is measured as the age of the backup artifact relative to the incident time. For a fresh drill backup, record the backup command completion time and treat that as the recovery point.
- RTO is measured from starting `scripts/restore.py` to receiving its healthy JSON result. The command prints `elapsed_seconds`; record that value as observed restore time.
- `bytes` in backup and restore JSON is the artifact size used to compare future drills on larger databases.

## Disposable Drill

Create and use only `.tmp/part-020-slice-003` for drills:

```powershell
New-Item -ItemType Directory -Force -Path ".tmp/part-020-slice-003"
python -c "from pathlib import Path; from core import stm; stm.init(Path('.tmp/part-020-slice-003/source.db'))"
python scripts/doctor.py --db .tmp/part-020-slice-003/source.db
python scripts/backup.py --source-db .tmp/part-020-slice-003/source.db --output .tmp/part-020-slice-003/backup.db
python -c "from pathlib import Path; Path('.tmp/part-020-slice-003/source.db').write_bytes(b'corrupt disposable fixture')"
python scripts/restore.py --backup .tmp/part-020-slice-003/backup.db --target-db .tmp/part-020-slice-003/restored.db
python scripts/doctor.py --db .tmp/part-020-slice-003/restored.db
Remove-Item -Recurse -Force ".tmp/part-020-slice-003"
```

## Production Diagnostics

Doctor may inspect production read-only:

```powershell
python scripts/doctor.py --db C:\Users\tcart\my-agent-data\state.db
```

Backup and restore must not touch production paths. These commands are expected to fail with `production_path_rejected`:

```powershell
python scripts/backup.py --source-db C:\Users\tcart\my-agent-data\state.db --output .tmp/part-020-slice-003/prod-backup.db
python scripts/restore.py --backup .tmp/part-020-slice-003/backup.db --target-db C:\Users\tcart\my-agent-data\state.db --overwrite
python scripts/doctor.py --db C:\Users\tcart\my-agent-data\state.db --reject-production
```

## Cleanup

After a drill, remove only the disposable fixture directory:

```powershell
Remove-Item -Recurse -Force ".tmp/part-020-slice-003"
```

Never clean `config.DATA_DIR`, `config.VAULT_PATH`, `config.TRANSCRIPT_DIR`, or derived production files as part of this drill.
