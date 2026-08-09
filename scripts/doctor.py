#!/usr/bin/env python3
"""Inspect DB1 SQLite health without writing to the database.

# --- How to run ---
# python scripts/doctor.py --db C:\\Users\\tcart\\my-agent-data\\state.db
# python scripts/doctor.py --db .tmp/part-020-slice-003/restored.db --reject-production
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Final, NoReturn, TypedDict

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from core import stm


class OperationError(RuntimeError):
    """Typed CLI failure with a stable machine-readable code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class DoctorPayload(TypedDict):
    operation: str
    healthy: bool
    path: str
    tables: list[str]
    missing_tables: list[str]
    integrity: str
    elapsed_seconds: float


class ErrorPayload(TypedDict):
    operation: str
    healthy: bool
    path: str
    tables: list[str]
    missing_tables: list[str]
    integrity: str
    error: str
    message: str
    elapsed_seconds: float


class DoctorRunResult(TypedDict):
    payload: DoctorPayload
    exit_code: int


@dataclass(frozen=True, slots=True)
class DoctorRequest:
    db: Path
    reject_production: bool


PRODUCTION_PATHS: Final[tuple[Path, ...]] = (
    config.STATE_DB,
    config.DATA_DIR,
    config.VAULT_PATH,
    config.INDEX_DB,
    config.TRANSCRIPT_DIR,
)


def resolve_path(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


def is_production_path(path: Path) -> bool:
    resolved = resolve_path(path)
    for root in PRODUCTION_PATHS:
        production_root = resolve_path(root)
        if resolved == production_root or production_root in resolved.parents:
            return True
    return False


def sqlite_uri(path: Path) -> str:
    return f"{resolve_path(path).as_uri()}?mode=ro"


def read_health(path: Path) -> tuple[str, list[str]]:
    with closing(sqlite3.connect(sqlite_uri(path), uri=True)) as connection:
        integrity_row = connection.execute("PRAGMA integrity_check").fetchone()
        table_rows = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
    if integrity_row is None:
        raise OperationError("integrity_check_failed", "SQLite returned no integrity result")
    return str(integrity_row[0]), [str(row[0]) for row in table_rows]


def run_doctor(request: DoctorRequest) -> DoctorRunResult:
    db = resolve_path(request.db)
    if request.reject_production and is_production_path(db):
        raise OperationError("production_path_rejected", f"db is inside a protected production path: {db}")
    if not db.is_file():
        raise OperationError("db_missing", f"DB does not exist: {db}")

    started = time.perf_counter()
    integrity, tables = read_health(db)
    required_tables = set(stm.TABLES)
    present_tables = set(tables)
    missing_tables = sorted(required_tables - present_tables)
    healthy = integrity == "ok" and not missing_tables
    payload: DoctorPayload = {
        "operation": "doctor",
        "healthy": healthy,
        "path": str(db),
        "tables": tables,
        "missing_tables": missing_tables,
        "integrity": integrity,
        "elapsed_seconds": round(time.perf_counter() - started, 6),
    }
    return {"payload": payload, "exit_code": 0 if healthy else 1}


def parse_args() -> DoctorRequest:
    parser = argparse.ArgumentParser(description="Read-only DB1 integrity and required-table doctor.")
    parser.add_argument("--db", required=True, type=Path, help="SQLite DB path to inspect read-only")
    parser.add_argument(
        "--reject-production",
        action="store_true",
        help="Fail when --db points at config production paths; default allows read-only production diagnostics",
    )
    args = parser.parse_args()
    return DoctorRequest(db=args.db, reject_production=args.reject_production)


def fail(error: OperationError, started: float, db: Path | None) -> NoReturn:
    payload: ErrorPayload = {
        "operation": "doctor",
        "healthy": False,
        "path": str(resolve_path(db)) if db is not None else "",
        "tables": [],
        "missing_tables": list(stm.TABLES),
        "integrity": "failed",
        "error": error.code,
        "message": error.message,
        "elapsed_seconds": round(time.perf_counter() - started, 6),
    }
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True), file=sys.stderr)
    raise SystemExit(1)


def main() -> int:
    started = time.perf_counter()
    request: DoctorRequest | None = None
    try:
        request = parse_args()
        result = run_doctor(request)
    except OperationError as error:
        fail(error, started, request.db if request is not None else None)
    except sqlite3.DatabaseError as error:
        fail(OperationError("sqlite_error", str(error)), started, request.db if request is not None else None)
    except OSError as error:
        fail(OperationError("doctor_failed", str(error)), started, request.db if request is not None else None)
    output = json.dumps(result["payload"], ensure_ascii=False, sort_keys=True)
    if result["exit_code"] == 0:
        print(output)
    else:
        print(output, file=sys.stderr)
    return result["exit_code"]


if __name__ == "__main__":
    raise SystemExit(main())
