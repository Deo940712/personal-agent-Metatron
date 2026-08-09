#!/usr/bin/env python3
"""Probe DB1 job_runs schema and API behavior.

# --- How to run ---
# python scripts/probes/probe_job_runs_schema.py --db "$env:TEMP\\metatron-job-runs.db" --report "$env:TEMP\\metatron-job-runs-report.json"
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import config
from core import stm


PROTECTED_PATHS = (
    config.STATE_DB,
    config.DATA_DIR,
    config.VAULT_PATH,
    config.INDEX_DB,
    config.TRANSCRIPT_DIR,
)


@dataclass(frozen=True, slots=True)
class ProbeRequest:
    db: Path
    report: Path


def parse_args() -> ProbeRequest:
    parser = argparse.ArgumentParser(description="Probe job_runs schema and API behavior.")
    parser.add_argument("--db", required=True, type=Path, help="Disposable SQLite DB path")
    parser.add_argument("--report", required=True, type=Path, help="JSON report output path")
    args = parser.parse_args()
    return ProbeRequest(db=args.db, report=args.report)


def _resolve(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


def _is_protected(path: Path) -> bool:
    resolved = _resolve(path)
    for protected in PROTECTED_PATHS:
        protected_path = _resolve(protected)
        if resolved == protected_path or protected_path in resolved.parents:
            return True
    return False


def _prepare_disposable_db(path: Path) -> None:
    if _is_protected(path):
        raise ValueError(f"probe db must not be inside a production path: {path}")
    for candidate in (path, Path(f"{path}-wal"), Path(f"{path}-shm")):
        if candidate.exists():
            candidate.unlink()


def run_probe(request: ProbeRequest) -> dict:  # noqa: DICT_OK
    if _is_protected(request.report):
        raise ValueError(f"probe report must not be inside a production path: {request.report}")
    _prepare_disposable_db(request.db)
    stm.init(request.db)
    first_run_id = stm.job_run_start(
        request.db,
        "probe-remind",
        "probe-remind-success",
        planned_at=1_800_000_000,
        next_expected_at=1_800_003_600,
        now=1_800_000_001,
    )
    overlap_id = stm.job_run_start(
        request.db,
        "probe-remind",
        "probe-remind-overlap",
        planned_at=1_800_000_060,
        next_expected_at=1_800_003_660,
        now=1_800_000_002,
    )
    success_finished = stm.job_run_finish(
        request.db,
        "probe-remind-success",
        "succeeded",
        exit_code=0,
        finished_at=1_800_000_031,
        log_path="logs/probe-remind-success.log",
    )
    failed_id = stm.job_run_start(
        request.db,
        "probe-consolidate",
        "probe-consolidate-failed",
        planned_at=1_800_010_000,
        next_expected_at=None,
        now=1_800_010_005,
    )
    failed_finished = stm.job_run_finish(
        request.db,
        "probe-consolidate-failed",
        "failed",
        exit_code=2,
        error="probe failure",
        finished_at=1_800_010_045,
    )
    rows = stm.job_run_list(request.db, limit=10)
    statuses = sorted({row["status"] for row in rows})
    payload = {
        "columns": stm.job_run_schema_columns(request.db),
        "failed_finished": failed_finished,
        "failed_id_created": failed_id is not None,
        "no_duplicate_running": stm.job_run_running_count(request.db, "probe-remind") <= 1,
        "overlap_skipped": overlap_id is None,
        "rows": rows,
        "statuses": statuses,
        "success_finished": success_finished,
        "success_id_created": first_run_id is not None,
    }
    request.report.parent.mkdir(parents=True, exist_ok=True)
    request.report.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return payload


def main() -> int:
    payload = run_probe(parse_args())
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
