"""slice-002 驗證:三領域 CRUD roundtrip、cursors、events、CLI、跨行程無狀態。"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from core import stm

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture()
def db(tmp_path):
    path = tmp_path / "state.db"
    stm.init(path)
    return path


# ── schedule roundtrip ───────────────────────────────────────────────

def test_schedule_add_list_done(db):
    rid = stm.schedule_add(db, "開會", 1_800_000_000, remind_at=1_799_998_200)
    rows = stm.schedule_list(db)
    assert len(rows) == 1 and rows[0]["id"] == rid and rows[0]["title"] == "開會"
    assert rows[0]["status"] == "active"

    assert stm.schedule_set_status(db, rid, "done")
    assert stm.schedule_list(db) == []                      # active 過濾
    assert stm.schedule_list(db, include_done=True)[0]["status"] == "done"


def test_schedule_done_nonexistent_returns_false(db):
    assert not stm.schedule_set_status(db, 999, "done")


def test_schedule_list_ordered_by_start(db):
    stm.schedule_add(db, "later", 2_000_000_000)
    stm.schedule_add(db, "sooner", 1_900_000_000)
    assert [r["title"] for r in stm.schedule_list(db)] == ["sooner", "later"]


# ── tasks roundtrip ──────────────────────────────────────────────────

def test_task_add_list_done(db):
    rid = stm.task_add(db, "買貓砂", due_at=1_800_000_000)
    assert stm.task_list(db)[0]["id"] == rid

    stm.task_set_status(db, rid, "in_progress")
    assert stm.task_list(db, status="in_progress")[0]["id"] == rid
    assert stm.task_list(db)[0]["id"] == rid                # 未完結仍列出

    stm.task_set_status(db, rid, "done")
    assert stm.task_list(db) == []                          # done 不在預設清單
    assert stm.task_list(db, status="done")[0]["id"] == rid


def test_task_waiting_user_in_default_list(db):
    rid = stm.task_add(db, "等使用者決定")
    stm.task_set_status(db, rid, "waiting_user")
    assert [r["id"] for r in stm.task_list(db)] == [rid]


# ── projects upsert ──────────────────────────────────────────────────

def test_project_set_insert_then_partial_update(db):
    pid = stm.project_set(db, "my-agent", phase="phase-1", blockers=["等 LLM 選型"])
    assert stm.project_set(db, "my-agent", phase="phase-2") == pid  # 同 id = upsert

    row = stm.project_show(db, "my-agent")[0]
    assert row["phase"] == "phase-2"
    assert row["blockers"] == ["等 LLM 選型"]               # 未給的欄位保留

    stm.project_set(db, "my-agent", blockers=[])
    assert stm.project_show(db, "my-agent")[0]["blockers"] == []


def test_project_show_all_ordered_by_updated(db):
    stm.project_set(db, "old", phase="x")
    stm.project_set(db, "new", phase="y")
    stm.project_set(db, "old", phase="x2")                  # old 變最新
    assert [r["name"] for r in stm.project_show(db)][0] == "old"


# ── cursors ──────────────────────────────────────────────────────────

def test_cursor_get_set_overwrite(db):
    assert stm.cursor_get(db, "threads_sync", "end_cursor") is None
    stm.cursor_set(db, "threads_sync", "end_cursor", "abc")
    stm.cursor_set(db, "threads_sync", "end_cursor", "def")
    assert stm.cursor_get(db, "threads_sync", "end_cursor") == "def"


# ── events ───────────────────────────────────────────────────────────

def test_event_append_and_query(db):
    stm.event_append(db, "user", "decision", "DATA_DIR 定案", target="config")
    stm.event_append(db, "writer", "proposal_rejected", "tag 不合法", target="note-1")
    assert len(stm.event_query(db)) == 2
    assert stm.event_query(db, target="config")[0]["summary"] == "DATA_DIR 定案"
    assert stm.event_query(db, actor="writer")[0]["action"] == "proposal_rejected"


def test_event_query_excludes_non_alive(db):
    rid = stm.event_append(db, "user", "decision", "x")
    con = stm.connect(db)
    con.execute("UPDATE events SET state='archived' WHERE id=?", (rid,))
    con.commit()
    con.close()
    assert stm.event_query(db) == []                        # 遺忘 = 不主動載入


def test_event_immune_flag(db):
    rid = stm.event_append(db, "user", "decision", "我偏好繁中", immune=True)
    con = stm.connect(db)
    assert con.execute("SELECT immune FROM events WHERE id=?", (rid,)).fetchone()[0] == 1
    con.close()


# ── 時間輔助 ─────────────────────────────────────────────────────────

def test_parse_when_iso_and_epoch():
    assert stm.parse_when("1800000000") == 1_800_000_000
    # ISO 視為本地時區,能 roundtrip 回同一分鐘即可
    epoch = stm.parse_when("2026-07-15T14:00")
    assert stm.fmt_when(epoch) == "2026-07-15 14:00"


# ── CLI(subprocess)───────────────────────────────────────────────────

def run_cli(db, *args):
    # PYTHONUTF8=1:Windows 子行程 stdout 預設 cp950,強制 UTF-8 確保中文輸出可解碼
    env = {**os.environ, "PYTHONUTF8": "1"}
    return subprocess.run(
        [sys.executable, "-m", "core.stm", "--db", str(db), *args],
        capture_output=True, text=True, cwd=REPO, encoding="utf-8", env=env)


def test_cli_schedule_roundtrip(db):
    r = run_cli(db, "schedule", "add", "開會", "--start", "1800000000")
    assert r.returncode == 0 and "schedule #1" in r.stdout
    r = run_cli(db, "schedule", "list")
    assert "開會" in r.stdout
    r = run_cli(db, "schedule", "done", "1")
    assert r.returncode == 0
    r = run_cli(db, "schedule", "done", "999")
    assert r.returncode == 1                                # 不存在 → 非零退出碼


def test_cli_tasks_and_projects(db):
    assert run_cli(db, "tasks", "add", "買貓砂").returncode == 0
    assert "買貓砂" in run_cli(db, "tasks", "list").stdout
    assert run_cli(db, "projects", "set", "my-agent", "--phase", "p1",
                   "--blockers", "a,b").returncode == 0
    out = run_cli(db, "projects", "show", "my-agent").stdout
    assert "p1" in out and "a" in out


# ── 跨行程無狀態(Phase 1 gate)──────────────────────────────────────

def test_cross_process_state_via_db1_only(db):
    """process A 寫入 → process B 讀到:狀態僅經 DB1 接續,無共享記憶體。"""
    a = run_cli(db, "schedule", "add", "跨行程測試", "--start", "1800000000")
    assert a.returncode == 0
    b = run_cli(db, "schedule", "list")
    assert "跨行程測試" in b.stdout
