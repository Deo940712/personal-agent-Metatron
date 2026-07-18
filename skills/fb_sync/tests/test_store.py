"""store 測試:SQLite 去重(by id)+ sync_runs + crawl_state(cursor 續傳)。"""

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


# ── init idempotent ──────────────────────────────────────────────────

def test_init_idempotent(db):
    store.init_db(db)                          # 二次不炸
    with store.connect(db) as conn:
        tabs = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"posts", "sync_runs", "crawl_state"} <= tabs


# ── dedupe by id ─────────────────────────────────────────────────────

def test_add_and_is_known(db):
    with store.connect(db) as conn:
        assert not store.is_known(conn, "p1")
        store.add_post(conn, post_id="p1", author="a", url="http://x", md_path="p1.md")
        assert store.is_known(conn, "p1")


def test_add_duplicate_ignored(db):
    with store.connect(db) as conn:
        store.add_post(conn, post_id="p1", author="a", url="http://x")
        store.add_post(conn, post_id="p1", author="b", url="http://y")  # 重複
        n = conn.execute("SELECT COUNT(*) FROM posts WHERE id='p1'").fetchone()[0]
    assert n == 1                              # append-only,不覆蓋


# ── sync_runs 生命週期 ───────────────────────────────────────────────

def test_run_lifecycle(db):
    with store.connect(db) as conn:
        rid = store.start_run(conn)
        store.finish_run(conn, rid, new_count=5, status="ok")
        row = conn.execute(
            "SELECT status, new_count FROM sync_runs WHERE id=?", (rid,)).fetchone()
    assert row["status"] == "ok" and row["new_count"] == 5


# ── crawl_state cursor 續傳 ──────────────────────────────────────────

def test_cursor_roundtrip(db):
    with store.connect(db) as conn:
        assert store.get_cursor(conn) is None
        store.save_cursor(conn, "CURSOR_ABC")
        assert store.get_cursor(conn) == "CURSOR_ABC"
        store.save_cursor(conn, "CURSOR_DEF")   # 覆寫(單列)
        assert store.get_cursor(conn) == "CURSOR_DEF"


def test_clear_cursor(db):
    with store.connect(db) as conn:
        store.save_cursor(conn, "X")
        store.clear_cursor(conn)
        assert store.get_cursor(conn) is None


# ── media_done 標記(media 階段用)─────────────────────────────────────

def test_mark_media_done(db):
    with store.connect(db) as conn:
        store.add_post(conn, post_id="p1", url="http://x")
        store.mark_media_done(conn, "p1")
        row = conn.execute("SELECT media_done FROM posts WHERE id='p1'").fetchone()
    assert row["media_done"] == 1


# ── 跨連線持久(無狀態驗證)────────────────────────────────────────────

def test_survives_reconnect(db):
    with store.connect(db) as conn:
        store.add_post(conn, post_id="persist", url="http://x")
    with store.connect(db) as conn:            # 新連線
        assert store.is_known(conn, "persist")
