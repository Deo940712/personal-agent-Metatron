# DB1 `job_runs` Schema

`job_runs` is the DB1 authority for scheduled job run identity, status, overlap control, and observability. Schema migration authority lives only in `core/stm.py`; `stm.init()` applies the table and indexes idempotently for new and existing DB1 files.

## Table

| Column | Type | Null | Meaning |
|---|---|---|---|
| `id` | `INTEGER PRIMARY KEY AUTOINCREMENT` | no | Local row id. |
| `job_name` | `TEXT` | no | Stable scheduled job name, for example `remind` or `consolidate`. |
| `run_id` | `TEXT UNIQUE` | no | Correlation id for one planned execution. |
| `planned_at` | `INTEGER` | no | Planned UTC epoch seconds. |
| `started_at` | `INTEGER` | no | Actual start UTC epoch seconds. |
| `finished_at` | `INTEGER` | yes | Terminal UTC epoch seconds. `NULL` while running. |
| `status` | `TEXT` | no | `running`, `succeeded`, `failed`, `skipped`, or `missed`. |
| `exit_code` | `INTEGER` | yes | Process/job exit code when applicable. |
| `error` | `TEXT` | yes | Terminal error summary for failed/missed runs. |
| `duration_seconds` | `INTEGER` | yes | `finished_at - started_at`, computed by `job_run_finish`. |
| `log_path` | `TEXT` | yes | Optional relative or operator-readable log pointer. |
| `last_success_at` | `INTEGER` | yes | Set to `finished_at` only for `succeeded` runs. |
| `next_expected_at` | `INTEGER` | yes | Next planned UTC epoch seconds when known at start. |
| `created_at` | `INTEGER` | no | Row creation UTC epoch seconds. |

## Indexes And Constraints

- `run_id` is unique, so one scheduled execution has one durable DB1 identity.
- `status` is checked to the allowed set: `running`, `succeeded`, `failed`, `skipped`, `missed`.
- `idx_job_runs_job_status_time` indexes `(job_name, status, planned_at)` for job dashboards and probes.
- `idx_job_runs_one_running` is a partial unique index on `job_name WHERE status = 'running'`; it prevents more than one active run for the same job.

## Migration Contract

- `core/stm.py` is the only migration authority for this table.
- `stm.init(db_path)` creates or upgrades DB1 with `CREATE TABLE IF NOT EXISTS` and `CREATE INDEX IF NOT EXISTS` statements.
- Existing DBs migrate by re-running `stm.init`; no daemon, scheduler, vault, transcript, or vector-index migration is part of this schema.
