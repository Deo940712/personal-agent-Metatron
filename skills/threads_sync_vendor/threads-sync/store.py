"""SQLite state: dedupe by post_id and per-run logging.

Schema mirrors threads-sync-plan.md section 4. `posts` drives dedupe +
stop-on-seen; `sync_runs.status` is the primary breakage detector when the
Threads GraphQL interface changes.
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
  id            TEXT PRIMARY KEY, -- Threads post_id, dedupe key
  author        TEXT,
  url           TEXT,
  saved_at      TEXT,             -- if the response provides it
  synced_at     TEXT,             -- first time we captured it
  md_path       TEXT,             -- corresponding .md
  media_done    INTEGER DEFAULT 0,-- 1 once images are downloaded
  thread_len    INTEGER DEFAULT 1,-- self_thread_length (1 = not a thread)
  thread_done   INTEGER DEFAULT 0 -- 1 once author continuations are merged in
);

CREATE TABLE IF NOT EXISTS sync_runs (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  started_at  TEXT,
  finished_at TEXT,
  new_count   INTEGER,
  status      TEXT               -- ok / login_expired / error
);

CREATE TABLE IF NOT EXISTS crawl_state (
  id          INTEGER PRIMARY KEY CHECK (id = 1),  -- single-row table
  end_cursor  TEXT,              -- last page_info.end_cursor for resume
  updated_at  TEXT
);
"""


def _now() -> str:
    return datetime.now(UTC).isoformat()


@contextmanager
def connect(db_path: Path | None = None) -> Iterator[sqlite3.Connection]:
    """Open a connection with sane defaults; commits on clean exit."""
    path = db_path or config.DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _migrate(conn: sqlite3.Connection) -> None:
    """Add columns introduced after the first release. Idempotent.

    The existing DB predates thread_len/thread_done, so ALTER them in if missing.
    """
    existing = {row[1] for row in conn.execute("PRAGMA table_info(posts)")}
    if "thread_len" not in existing:
        conn.execute("ALTER TABLE posts ADD COLUMN thread_len INTEGER DEFAULT 1")
    if "thread_done" not in existing:
        conn.execute("ALTER TABLE posts ADD COLUMN thread_done INTEGER DEFAULT 0")


def init_db(db_path: Path | None = None) -> None:
    """Create tables if absent, then migrate. Idempotent."""
    with connect(db_path) as conn:
        conn.executescript(SCHEMA)
        _migrate(conn)


def is_known(conn: sqlite3.Connection, post_id: str) -> bool:
    """True if this post_id was already synced."""
    row = conn.execute("SELECT 1 FROM posts WHERE id = ?", (post_id,)).fetchone()
    return row is not None


def add_post(
    conn: sqlite3.Connection,
    *,
    post_id: str,
    author: str | None = None,
    url: str | None = None,
    saved_at: str | None = None,
    md_path: str | None = None,
    thread_len: int = 1,
) -> None:
    """Insert a newly captured post. Ignores duplicates (append-only).

    `thread_len` is self_thread_length; posts with thread_len > 1 need a later
    backfill pass to merge in the author's continuation posts (thread_done=0).
    """
    conn.execute(
        """
        INSERT OR IGNORE INTO posts
          (id, author, url, saved_at, synced_at, md_path, media_done, thread_len, thread_done)
        VALUES (?, ?, ?, ?, ?, ?, 0, ?, 0)
        """,
        (post_id, author, url, saved_at, _now(), md_path, thread_len),
    )


def mark_media_done(conn: sqlite3.Connection, post_id: str) -> None:
    conn.execute("UPDATE posts SET media_done = 1 WHERE id = ?", (post_id,))


def mark_thread_done(conn: sqlite3.Connection, post_id: str) -> None:
    """Mark a post's author-continuation backfill as complete."""
    conn.execute("UPDATE posts SET thread_done = 1 WHERE id = ?", (post_id,))


def set_thread_len(conn: sqlite3.Connection, post_id: str, thread_len: int) -> None:
    """Record self_thread_length for a known post without touching its .md.

    Lets a re-run of the crawl flag the pre-existing 780 posts as threads so the
    backfill pass can pick them up. Never clears an already-done backfill.
    """
    conn.execute(
        "UPDATE posts SET thread_len = ? WHERE id = ?",
        (thread_len, post_id),
    )


def pending_threads(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Return posts that are self-threads still needing continuation backfill.

    thread_len defaults to 1 for the 780 posts synced before this column existed,
    so those correctly report as not-a-thread until re-synced. Rows here are ones
    the crawl has since flagged as thread_len > 1 with thread_done = 0.
    """
    return conn.execute(
        "SELECT id, author, url, md_path, thread_len FROM posts "
        "WHERE thread_len > 1 AND thread_done = 0"
    ).fetchall()


def start_run(conn: sqlite3.Connection) -> int:
    """Open a sync_runs row; returns its id."""
    cur = conn.execute(
        "INSERT INTO sync_runs (started_at, status) VALUES (?, 'running')",
        (_now(),),
    )
    return int(cur.lastrowid)


def finish_run(conn: sqlite3.Connection, run_id: int, *, new_count: int, status: str) -> None:
    """Close a sync_runs row. status: ok / login_expired / error."""
    conn.execute(
        "UPDATE sync_runs SET finished_at = ?, new_count = ?, status = ? WHERE id = ?",
        (_now(), new_count, status, run_id),
    )


def save_cursor(conn: sqlite3.Connection, end_cursor: str | None) -> None:
    """Persist the last pagination cursor for resume-on-interrupt (single row)."""
    conn.execute(
        """
        INSERT INTO crawl_state (id, end_cursor, updated_at) VALUES (1, ?, ?)
        ON CONFLICT(id) DO UPDATE SET end_cursor = excluded.end_cursor,
                                      updated_at = excluded.updated_at
        """,
        (end_cursor, _now()),
    )


def get_cursor(conn: sqlite3.Connection) -> str | None:
    """Return the last saved pagination cursor, or None if never set."""
    row = conn.execute("SELECT end_cursor FROM crawl_state WHERE id = 1").fetchone()
    return row["end_cursor"] if row else None


def clear_cursor(conn: sqlite3.Connection) -> None:
    """Clear the saved cursor once a full crawl finishes (has_next_page=False)."""
    conn.execute("UPDATE crawl_state SET end_cursor = NULL, updated_at = ? WHERE id = 1", (_now(),))


if __name__ == "__main__":
    init_db()
    print(f"Initialized DB at {config.DB_PATH}")
