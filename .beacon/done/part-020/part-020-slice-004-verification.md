# part-020 slice-004 Verification

## Result

PASS — DB1 `job_runs` schema and observability APIs verified.

## Evidence

- Red test: initial `test_job_runs.py` failed because `job_runs` and APIs were absent.
- Focused tests: `python -m pytest tests/test_job_runs.py -q` → **6 passed**.
- Full regression: `python -m pytest tests/ -q` → **979 passed, 1 warning**.
- Independent probe: `python scripts/probes/probe_job_runs_schema.py --db <TEMP> --report <TEMP>` → schema columns complete, `overlap_skipped=true`, `no_duplicate_running=true`, statuses `failed/succeeded`, report assertions passed.
- Migration: repeated `stm.init()` preserved the job_runs schema and existing DB1 contracts.

## Adversarial audit

- duplicate active run: atomic start plus partial unique index returned `None` for overlap.
- terminal transition: running rows finalized once; invalid terminal status rejected.
- deterministic timestamps: tests and probe inject fixed epoch values.
- stale report: probe removes disposable DB/WAL/SHM paths before recreating and report was deleted after verification.

## Scope

No daemon, dashboard job UI, scheduler migration, vault, transcript, or vector-index changes.
