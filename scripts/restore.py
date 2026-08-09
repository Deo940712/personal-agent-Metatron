#!/usr/bin/env python3
"""Atomically restore a verified SQLite backup to an explicit disposable path.

# --- How to run ---
# python scripts/restore.py --backup .tmp/part-020-slice-003/backup.db --target-db .tmp/part-020-slice-003/restored.db
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


class RestorePayload(TypedDict):
    operation: str
    backup: str
    target_db: str
    integrity: str
    bytes: int
    overwritten: bool
    elapsed_seconds: float


class ErrorPayload(TypedDict):
    operation: str
    healthy: bool
    error: str
    message: str
    elapsed_seconds: float


@dataclass(frozen=True, slots=True)
class RestoreRequest:
    backup: Path
    target_db: Path
    overwrite: bool


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


def run_restore(request: RestoreRequest) -> RestorePayload:
    backup = resolve_path(request.backup)
    target_db = resolve_path(request.target_db)
    require_disposable_path(backup, role="backup")
    require_disposable_path(target_db, role="target-db")
    if not backup.is_file():
        raise OperationError("backup_missing", f"backup DB does not exist: {backup}")
    if target_db.exists() and not request.overwrite:
        raise OperationError("target_exists", f"target DB already exists: {target_db}")

    started = time.perf_counter()
    sqlite_integrity(backup)
    target_db.parent.mkdir(parents=True, exist_ok=True)
    temp_target = target_db.with_name(f".{target_db.name}.restore.tmp")
    if temp_target.exists():
        temp_target.unlink()
    backup_uri = f"file:{backup.as_posix()}?mode=ro"
    with closing(sqlite3.connect(backup_uri, uri=True)) as backup_connection:
        with closing(sqlite3.connect(temp_target)) as target_connection:
            backup_connection.backup(target_connection)
    integrity = sqlite_integrity(temp_target)
    temp_target.replace(target_db)
    elapsed = round(time.perf_counter() - started, 6)
    return {
        "operation": "restore",
        "backup": str(backup),
        "target_db": str(target_db),
        "integrity": integrity,
        "bytes": target_db.stat().st_size,
        "overwritten": request.overwrite,
        "elapsed_seconds": elapsed,
    }


def parse_args() -> RestoreRequest:
    parser = argparse.ArgumentParser(description="Restore a verified SQLite backup to a non-production path.")
    parser.add_argument("--backup", required=True, type=Path, help="Explicit disposable backup path")
    parser.add_argument("--target-db", required=True, type=Path, help="Explicit disposable restore target path")
    parser.add_argument("--overwrite", action="store_true", help="Replace an existing disposable target DB")
    args = parser.parse_args()
    return RestoreRequest(backup=args.backup, target_db=args.target_db, overwrite=args.overwrite)


def fail(error: OperationError, started: float) -> NoReturn:
    payload: ErrorPayload = {
        "operation": "restore",
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
        payload = run_restore(parse_args())
    except OperationError as error:
        fail(error, started)
    except (OSError, sqlite3.Error) as error:
        fail(OperationError("restore_failed", str(error)), started)
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
