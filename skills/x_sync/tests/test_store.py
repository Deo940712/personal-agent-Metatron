"""store 測試:SQLite 去重(by tweet id)+ sync_runs + crawl_state(cursor 續傳)。"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import store  # noqa: E402


@pytest.fixture()
def db(tmp_path):
    path = tmp_path / "state.db"
    store.init_db(path)
    return path


def test_init_idempotent(db):
    store.init_db(db)
    with store.connect(db) as conn:
        tabs = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"posts", "sync_runs", "crawl_state"} <= tabs


def test_add_and_is_known(db):
    with store.connect(db) as conn:
        assert not store.is_known(conn, "t1")
        store.add_post(conn, post_id="t1", author="a", url="http://x/status/1")
        assert store.is_known(conn, "t1")


def test_add_duplicate_ignored(db):
    with store.connect(db) as conn:
        store.add_post(conn, post_id="t1", author="a", url="u1")
        store.add_post(conn, post_id="t1", author="b", url="u2")
        n = conn.execute("SELECT COUNT(*) FROM posts WHERE id='t1'").fetchone()[0]
    assert n == 1


def test_run_lifecycle(db):
    with store.connect(db) as conn:
        rid = store.start_run(conn)
        store.finish_run(conn, rid, new_count=7, status="ok")
        row = conn.execute(
            "SELECT status, new_count FROM sync_runs WHERE id=?", (rid,)).fetchone()
    assert row["status"] == "ok" and row["new_count"] == 7


def test_cursor_roundtrip(db):
    with store.connect(db) as conn:
        assert store.get_cursor(conn) is None
        store.save_cursor(conn, "CUR1")
        assert store.get_cursor(conn) == "CUR1"
        store.save_cursor(conn, "CUR2")
        assert store.get_cursor(conn) == "CUR2"


def test_clear_cursor(db):
    with store.connect(db) as conn:
        store.save_cursor(conn, "X")
        store.clear_cursor(conn)
        assert store.get_cursor(conn) is None


def test_mark_media_done(db):
    with store.connect(db) as conn:
        store.add_post(conn, post_id="t1", url="u")
        store.mark_media_done(conn, "t1")
        row = conn.execute("SELECT media_done FROM posts WHERE id='t1'").fetchone()
    assert row["media_done"] == 1


def test_survives_reconnect(db):
    with store.connect(db) as conn:
        store.add_post(conn, post_id="persist", url="u")
    with store.connect(db) as conn:
        assert store.is_known(conn, "persist")
