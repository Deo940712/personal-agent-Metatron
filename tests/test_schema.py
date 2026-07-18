"""slice-001 驗證:六張表存在、欄位正確、init idempotent、約束生效。"""

import sqlite3

import pytest

from core import stm

EXPECTED_COLUMNS = {
    "schedule": {"id", "title", "detail", "start_at", "end_at", "remind_at",
                 "reminded_at", "rrule", "status", "created_at"},
    "tasks": {"id", "title", "detail", "due_at", "status", "created_at"},
    "projects": {"id", "name", "repo_path", "phase", "blockers", "next_action",
                 "updated_at", "created_at"},
    "cursors": {"pipeline", "key", "value", "updated_at"},
    "agent_runs": {"id", "started_at", "finished_at", "trigger", "status",
                   "summary", "error"},
    "events": {"id", "ts", "actor", "action", "target", "summary", "source_ids",
               "health", "last_accessed_at", "immune", "state", "trashed_at",
               "created_at"},
    "pending_proposals": {"id", "proposal", "preview", "status", "channel_ref",
                          "created_at"},
}


@pytest.fixture()
def db(tmp_path):
    path = tmp_path / "state.db"
    stm.init(path)
    return path


def columns(db, table):
    con = sqlite3.connect(db)
    try:
        return {r[1] for r in con.execute(f"PRAGMA table_info({table})")}
    finally:
        con.close()


def test_all_tables_exist(db):
    assert stm.existing_tables(db) == sorted(stm.TABLES)
    assert len(stm.TABLES) == 8                           # part-006-slice-002:+directives


@pytest.mark.parametrize("table", sorted(EXPECTED_COLUMNS))
def test_columns_match_architecture_5_1(db, table):
    assert columns(db, table) == EXPECTED_COLUMNS[table]


def test_init_is_idempotent(db):
    before = stm.existing_tables(db)
    stm.init(db)  # 重跑
    stm.init(db)  # 再重跑
    assert stm.existing_tables(db) == before


def test_init_creates_parent_dirs(tmp_path):
    nested = tmp_path / "a" / "b" / "state.db"
    stm.init(nested)
    assert nested.exists()


def test_status_check_constraints(db):
    con = sqlite3.connect(db)
    try:
        con.execute("INSERT INTO agent_runs (started_at, trigger) VALUES (1, 'cli')")
        with pytest.raises(sqlite3.IntegrityError):
            con.execute("INSERT INTO agent_runs (started_at, trigger) VALUES (1, 'bogus')")
        with pytest.raises(sqlite3.IntegrityError):
            con.execute(
                "INSERT INTO tasks (title, status, created_at) VALUES ('x', 'bogus', 1)")
        with pytest.raises(sqlite3.IntegrityError):
            con.execute(
                "INSERT INTO events (ts, actor, action, summary, state, created_at) "
                "VALUES (1, 'user', 'decision', 'x', 'bogus', 1)")
    finally:
        con.close()


def test_events_defaults(db):
    con = sqlite3.connect(db)
    try:
        con.execute(
            "INSERT INTO events (ts, actor, action, summary, created_at) "
            "VALUES (1, 'user', 'decision', 'x', 1)")
        health, immune, state, trashed_at = con.execute(
            "SELECT health, immune, state, trashed_at FROM events").fetchone()
        assert (health, immune, state, trashed_at) == (1.0, 0, "alive", None)
    finally:
        con.close()


def test_remind_partial_index_used(db):
    con = sqlite3.connect(db)
    try:
        con.execute(
            "INSERT INTO schedule (title, start_at, remind_at, created_at) "
            "VALUES ('t', 100, 90, 1)")
        plan = " ".join(
            r[3] for r in con.execute(
                "EXPLAIN QUERY PLAN SELECT * FROM schedule "
                "WHERE remind_at <= 999 AND status='active' AND reminded_at IS NULL"))
        assert "idx_schedule_remind" in plan
    finally:
        con.close()


def test_cursors_composite_pk(db):
    con = sqlite3.connect(db)
    try:
        con.execute(
            "INSERT INTO cursors (pipeline, key, value, updated_at) VALUES ('p', 'k', 'v', 1)")
        with pytest.raises(sqlite3.IntegrityError):
            con.execute(
                "INSERT INTO cursors (pipeline, key, value, updated_at) VALUES ('p', 'k', 'v2', 2)")
    finally:
        con.close()
