#!/usr/bin/env python3
"""Create a verified SQLite backup from explicit disposable paths.

# --- How to run ---
# python scripts/backup.py --source-db .tmp/part-020-slice-003/source.db --output .tmp/part-020-slice-003/backup.db
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


class OperationError(RuntimeError):
    """Typed CLI failure with a stable machine-readable code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class BackupPayload(TypedDict):
    operation: str
    source_db: str
    output: str
    integrity: str
    bytes: int
    elapsed_seconds: float


class ErrorPayload(TypedDict):
    operation: str
    healthy: bool
    error: str
    message: str
    elapsed_seconds: float


@dataclass(frozen=True, slots=True)
class BackupRequest:
    source_db: Path
    output: Path


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


def require_disposable_path(path: Path, *, role: str) -> None:
    if is_production_path(path):
        raise OperationError("production_path_rejected", f"{role} is inside a protected production path: {path}")


def sqlite_integrity(path: Path) -> str:
    uri = f"{resolve_path(path).as_uri()}?mode=ro"
    with closing(sqlite3.connect(uri, uri=True)) as connection:
        row = connection.execute("PRAGMA integrity_check").fetchone()
    if row is None:
        raise OperationError("integrity_check_failed", f"SQLite returned no integrity result for {path}")
    result = str(row[0])
    if result != "ok":
        raise OperationError("integrity_check_failed", result)
    return result


def run_backup(request: BackupRequest) -> BackupPayload:
    source_db = resolve_path(request.source_db)
    output = resolve_path(request.output)
    require_disposable_path(source_db, role="source-db")
    require_disposable_path(output, role="output")
    if not source_db.is_file():
        raise OperationError("source_missing", f"source DB does not exist: {source_db}")
    if output.exists():
        raise OperationError("output_exists", f"backup output already exists: {output}")

    started = time.perf_counter()
    sqlite_integrity(source_db)
    output.parent.mkdir(parents=True, exist_ok=True)
    source_uri = f"file:{source_db.as_posix()}?mode=ro"
    with closing(sqlite3.connect(source_uri, uri=True)) as source_connection:
        with closing(sqlite3.connect(output)) as output_connection:
            source_connection.backup(output_connection)
    integrity = sqlite_integrity(output)
    elapsed = round(time.perf_counter() - started, 6)
    return {
        "operation": "backup",
        "source_db": str(source_db),
        "output": str(output),
        "integrity": integrity,
        "bytes": output.stat().st_size,
        "elapsed_seconds": elapsed,
    }


def parse_args() -> BackupRequest:
    parser = argparse.ArgumentParser(description="Create a verified non-production SQLite backup.")
    parser.add_argument("--source-db", required=True, type=Path, help="Explicit disposable SQLite source path")
    parser.add_argument("--output", required=True, type=Path, help="Explicit disposable backup output path")
    args = parser.parse_args()
    return BackupRequest(source_db=args.source_db, output=args.output)


def fail(error: OperationError, started: float) -> NoReturn:
    payload: ErrorPayload = {
        "operation": "backup",
        "healthy": False,
        "error": error.code,
        "message": error.message,
        "elapsed_seconds": round(time.perf_counter() - started, 6),
    }
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True), file=sys.stderr)
    raise SystemExit(1)


def main() -> int:
    started = time.perf_counter()
    try:
        payload = run_backup(parse_args())
    except OperationError as error:
        fail(error, started)
    except (OSError, sqlite3.Error) as error:
        fail(OperationError("backup_failed", str(error)), started)
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
