# CURRENT

Part: part-020
Slice: slice-004
Status: active — promoted 2026-08-03 after slice-003 verification and audit
Design authority: `.beacon/parts/part-020/DESIGN.md`
TODO source: `.beacon/parts/part-020/TODO.md#slice-004`

## Goal

Create the authoritative DB1 `job_runs` schema and APIs needed to observe scheduled jobs before part-021 daemon work begins.

## Allowed Scope

- [ ] Add the `job_runs` table through the existing DB1 initialization/migration path.
- [ ] Add typed `core/stm.py` APIs for starting, completing, failing, skipping, and querying job runs.
- [ ] Add `tests/test_job_runs.py` (new) covering schema, status transitions, overlap/idempotency, and last-success/next-expected fields.
- [ ] Add `scripts/probes/probe_job_runs_schema.py` (new) producing deterministic JSON evidence.
- [ ] Add `docs/SCHEMA.md` and `docs/OBSERVABILITY.md` (new) for the contract.

## Files-scope

- `core/stm.py`
- `tests/test_job_runs.py` (new)
- `scripts/probes/probe_job_runs_schema.py` (new)
- `docs/SCHEMA.md`
- `docs/OBSERVABILITY.md` (new)

## Forbidden Scope

- Do not implement the resident daemon, watchdog, dashboard job UI, or scheduler migration.
- Do not modify vault, transcript, vector index, or Windows Task Scheduler.
- Do not alter `.beacon/CURRENT.md` outside this active slice status and verification evidence.
- Do not modify unrelated dirty files.

## Verification Plan

- Red: add `tests/test_job_runs.py` first and prove the required table/API is absent or incomplete on the pre-change schema.
- Unit: `python -m pytest tests/test_job_runs.py -q`.
- Regression: `python -m pytest tests/ -q`.
- Operational QA: `python scripts/probes/probe_job_runs_schema.py --db "$env:TEMP\metatron-job-runs.db" --report "$env:TEMP\metatron-job-runs-report.json"`; assert schema, transitions, overlap handling, and deterministic report fields.

## Done Gate

- DB1 initialization/migration creates `job_runs` without breaking existing databases.
- APIs enforce allowed status transitions and prevent duplicate active runs for the same job.
- Focused/full tests and the schema probe pass.
- part-021 can consume the documented `job_runs` authority without adding a second status store.
