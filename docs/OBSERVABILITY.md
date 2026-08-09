# Scheduled Job Observability Contract

`job_runs` records scheduled job execution state for part-021 Supervisor/Watchdog consumers. It does not launch, retry, stop, or schedule jobs; it is the single DB1 status authority those future components must read and write through `core.stm` APIs.

## API Invariants

- `job_run_start(db, job_name, run_id, planned_at, next_expected_at, now=None)` validates non-empty `job_name` and `run_id`, inserts a `running` row, and returns the row id.
- `job_run_start` returns `None` when the same `job_name` already has a `running` row. This is the overlap signal; callers must not create a second status store.
- `job_run_finish(db, run_id, status, ...)` accepts only terminal statuses: `succeeded`, `failed`, `skipped`, `missed`.
- `job_run_finish` returns `False` when there is no matching active `run_id`; otherwise it writes `finished_at`, `duration_seconds`, terminal status, optional exit/error/log fields, and returns `True`.
- `succeeded` sets `last_success_at = finished_at`; all other terminal statuses leave `last_success_at` null for that run.
- `job_run_active(db, job_name)` returns the one running row or `None`.
- `job_run_list(db, job_name=None, limit=50)` returns newest rows first, optionally scoped to one job.

## Status Meaning

| Status | Meaning |
|---|---|
| `running` | The scheduled job has claimed its DB1 run identity and has not reached a terminal result. |
| `succeeded` | The job completed successfully; `exit_code` should be `0` when a process exit code exists. |
| `failed` | The job ran and failed; `error` should summarize the failure. |
| `skipped` | The job intentionally did no work, for example no due items. |
| `missed` | A future supervisor/watchdog detected a scheduled run that should have happened but did not complete normally. |

## Part-021 Consumer Contract

- Consumers must treat DB1 `job_runs` as authoritative for run identity, overlap, status, and operator-facing run history.
- Consumers must call `job_run_start` before doing job work and handle `None` as an active-overlap skip.
- Consumers must finish every claimed run with `job_run_finish`, choosing exactly one terminal status.
- Consumers may use `next_expected_at` to report schedule expectations, but part-020 does not compute recurrence or replace the scheduler.
- Consumers must not write raw SQL for `job_runs`; schema and mutation logic stay in `core/stm.py`.
