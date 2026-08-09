"""slice-004: job_runs schema/API contract tests.

Given/When/Then:
- Given a fresh DB1
- When the DB is initialized and job run APIs are exercised
- Then job_runs must exist and behave as the authoritative job-run store
"""

from __future__ import annotations

import pytest

from core import stm


@pytest.fixture()
def db(tmp_path):
    path = tmp_path / "state.db"
    stm.init(path)
    return path


def test_job_runs_schema_is_present_after_init(db):
    columns = stm.job_run_schema_columns(db)

    assert columns
    stm.init(db)
    assert stm.job_run_schema_columns(db) == columns
    assert columns == [
        "id",
        "job_name",
        "run_id",
        "planned_at",
        "started_at",
        "finished_at",
        "status",
        "exit_code",
        "error",
        "duration_seconds",
        "log_path",
        "last_success_at",
        "next_expected_at",
        "created_at",
    ]


def test_job_run_api_can_start_and_finish_runs(db):
    started_at = 1_800_000_000
    run_id = "remind-20260715-01"

    first_run = stm.job_run_start(db, "remind", run_id, planned_at=started_at, next_expected_at=started_at, now=started_at)
    overlap_run = stm.job_run_start(db, "remind", "remind-20260715-02", planned_at=started_at + 60, next_expected_at=started_at + 3600, now=started_at + 1)

    assert first_run is not None
    assert overlap_run is None

    finished = stm.job_run_finish(db, run_id, "succeeded", exit_code=0, finished_at=started_at + 30)

    assert finished is True
    active = stm.job_run_active(db, "remind")
    assert active is None
    rows = stm.job_run_list(db, "remind")
    assert rows[0]["status"] == "succeeded"
    assert rows[0]["duration_seconds"] == 30
    assert rows[0]["last_success_at"] == started_at + 30


def test_job_run_failure_keeps_last_success_empty_and_allows_next_run(db):
    started_at = 1_800_010_000

    first_id = stm.job_run_start(db, "consolidate", "consolidate-fail", started_at, None, now=started_at)
    assert first_id is not None

    assert stm.job_run_finish(
        db,
        "consolidate-fail",
        "failed",
        exit_code=2,
        error="boom",
        finished_at=started_at + 5,
        log_path="logs/consolidate-fail.log",
    )
    second_id = stm.job_run_start(
        db,
        "consolidate",
        "consolidate-next",
        started_at + 60,
        started_at + 3600,
        now=started_at + 61,
    )

    rows = stm.job_run_list(db, "consolidate")
    failed = rows[1]
    assert second_id is not None
    assert failed["status"] == "failed"
    assert failed["exit_code"] == 2
    assert failed["error"] == "boom"
    assert failed["duration_seconds"] == 5
    assert failed["log_path"] == "logs/consolidate-fail.log"
    assert failed["last_success_at"] is None


@pytest.mark.parametrize("bad_value", ["", "  "])
def test_job_run_start_rejects_empty_identity(db, bad_value):
    with pytest.raises(ValueError, match="job_name must be a non-empty string"):
        stm.job_run_start(db, bad_value, "run-1", 1, None, now=1)
    with pytest.raises(ValueError, match="run_id must be a non-empty string"):
        stm.job_run_start(db, "remind", bad_value, 1, None, now=1)


def test_job_run_finish_rejects_running_or_unknown_status(db):
    stm.job_run_start(db, "remind", "run-1", 1, None, now=1)

    with pytest.raises(ValueError, match="invalid job run status"):
        stm.job_run_finish(db, "run-1", "running", finished_at=2)
    with pytest.raises(ValueError, match="invalid job run status"):
        stm.job_run_finish(db, "run-1", "ok", finished_at=2)
