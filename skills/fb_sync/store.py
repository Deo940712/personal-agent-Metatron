"""SQLite state:去重(by post id)+ sync_runs + cursor 續傳。

同 threads-sync 架構,但 FB saved 不是自我串文結構,故無 thread_len/thread_done。
posts 驅動去重 + stop-on-seen;sync_runs.status 是介面改版的主要偵測點。
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS posts (
  id            TEXT PRIMARY KEY,   -- FB 貼文 id, dedupe key
  author        TEXT,
  url           TEXT,
  saved_at      TEXT,
  synced_at     TEXT,               -- 首次捕捉時間
  md_path       TEXT,
  media_done    INTEGER DEFAULT 0   -- 1 once images downloaded
);

CREATE TABLE IF NOT EXISTS sync_runs (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  started_at  TEXT,
  finished_at TEXT,
  new_count   INTEGER,
  status      TEXT                  -- ok / login_expired / error
);

CREATE TABLE IF NOT EXISTS crawl_state (
  id          INTEGER PRIMARY KEY CHECK (id = 1),  -- single-row
  end_cursor  TEXT,
  updated_at  TEXT
);
"""


def _now() -> str:
    return datetime.now(UTC).isoformat()


@contextmanager
def connect(db_path: Path | None = None) -> Iterator[sqlite3.Connection]:
    path = db_path or config.DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db(db_path: Path | None = None) -> None:
    with connect(db_path) as conn:
        conn.executescript(SCHEMA)


def is_known(conn: sqlite3.Connection, post_id: str) -> bool:
    return conn.execute("SELECT 1 FROM posts WHERE id = ?", (post_id,)).fetchone() is not None


def add_post(conn: sqlite3.Connection, *, post_id: str, author: str | None = None,
             url: str | None = None, saved_at: str | None = None,
             md_path: str | None = None) -> None:
    """插入新貼文;重複 id 忽略(append-only)。"""
    conn.execute(
        "INSERT OR IGNORE INTO posts "
        "(id, author, url, saved_at, synced_at, md_path, media_done) "
        "VALUES (?, ?, ?, ?, ?, ?, 0)",
        (post_id, author, url, saved_at, _now(), md_path))


def mark_media_done(conn: sqlite3.Connection, post_id: str) -> None:
    conn.execute("UPDATE posts SET media_done = 1 WHERE id = ?", (post_id,))


def start_run(conn: sqlite3.Connection) -> int:
    cur = conn.execute(
        "INSERT INTO sync_runs (started_at, status) VALUES (?, 'running')", (_now(),))
    return int(cur.lastrowid)


def finish_run(conn: sqlite3.Connection, run_id: int, *,
               new_count: int, status: str) -> None:
    conn.execute(
        "UPDATE sync_runs SET finished_at = ?, new_count = ?, status = ? WHERE id = ?",
        (_now(), new_count, status, run_id))


def save_cursor(conn: sqlite3.Connection, end_cursor: str | None) -> None:
    conn.execute(
        "INSERT INTO crawl_state (id, end_cursor, updated_at) VALUES (1, ?, ?) "
        "ON CONFLICT(id) DO UPDATE SET end_cursor = excluded.end_cursor, "
        "updated_at = excluded.updated_at",
        (end_cursor, _now()))


def get_cursor(conn: sqlite3.Connection) -> str | None:
    row = conn.execute("SELECT end_cursor FROM crawl_state WHERE id = 1").fetchone()
    return row["end_cursor"] if row else None


def clear_cursor(conn: sqlite3.Connection) -> None:
    conn.execute(
        "UPDATE crawl_state SET end_cursor = NULL, updated_at = ? WHERE id = 1", (_now(),))


if __name__ == "__main__":
    init_db()
    print(f"Initialized DB at {config.DB_PATH}")
