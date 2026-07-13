"""part-005-slice-001:三源唯讀掃描器(git 實測 tmp repo/假 opencode.db/
假 CURRENT.md + boundary 容錯)。"""

import sqlite3
import subprocess

import pytest

from core import octools, scanners


# ── git_scan(tmp repo 實測)──────────────────────────────────────────

@pytest.fixture()
def git_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=repo, check=True)
    (repo / "a.txt").write_text("x")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "feat: first commit"], cwd=repo, check=True)
    return repo


def test_git_scan_real_repo(git_repo):
    r = scanners.git_scan(git_repo)
    assert r is not None
    assert r["last_message"] == "feat: first commit"
    assert isinstance(r["last_commit_at"], int) and r["last_commit_at"] > 1_500_000_000
    assert r["branch"] in ("master", "main")
    assert r["unpushed"] is None                            # 無 upstream(P6 容忍)
    assert len(r["recent"]) == 1


def test_git_scan_non_git_dir(tmp_path):
    assert scanners.git_scan(tmp_path) is None


def test_git_scan_nonexistent_path(tmp_path):
    assert scanners.git_scan(tmp_path / "ghost") is None


# ── beacon_scan(兩形態 + 容錯)───────────────────────────────────────

def test_beacon_scan_active_form(tmp_path):
    b = tmp_path / ".beacon"
    b.mkdir()
    (b / "CURRENT.md").write_text(
        "# CURRENT\n\nPart: part-005\nSlice: slice-001\nStatus: active\n"
        "Design authority: `x`\n\n## Goal\n\n三個確定性掃描器,全唯讀。\n",
        encoding="utf-8")
    r = scanners.beacon_scan(tmp_path)
    assert r == {"status": "active", "part": "part-005", "slice": "slice-001",
                 "goal": "三個確定性掃描器,全唯讀。"}


def test_beacon_scan_planning_only_form(tmp_path):
    b = tmp_path / ".beacon"
    b.mkdir()
    (b / "CURRENT.md").write_text(
        "# CURRENT\n\nStatus: planning-only\n\npart-004 完成。\n", encoding="utf-8")
    r = scanners.beacon_scan(tmp_path)
    assert r["status"] == "planning-only"
    assert r["part"] is None and r["slice"] is None


def test_beacon_scan_missing(tmp_path):
    assert scanners.beacon_scan(tmp_path) is None           # 沒用 Beacon ≠ 錯誤


def test_beacon_scan_this_project():
    """對本專案實跑:CURRENT 是 part-005 active。"""
    r = scanners.beacon_scan(".")
    assert r is not None and r["part"] == "part-005"


# ── octools(假 opencode.db,同 schema)────────────────────────────────

@pytest.fixture()
def fake_ocdb(tmp_path):
    db = tmp_path / "opencode.db"
    con = sqlite3.connect(db)
    con.executescript("""
        CREATE TABLE session (
          id TEXT PRIMARY KEY, directory TEXT, title TEXT, agent TEXT,
          model TEXT, time_updated INTEGER, parent_id TEXT
        );
        CREATE TABLE todo (
          session_id TEXT, content TEXT, status TEXT, position INTEGER,
          time_updated INTEGER
        );
    """)
    proj = str(tmp_path / "myproj").replace("\\", "/")
    con.executemany(
        "INSERT INTO session VALUES (?, ?, ?, ?, ?, ?, ?)",
        [
            ("ses_1", proj, "設計架構", "build", "{}", 1_783_950_000_000, None),
            ("ses_2", proj, "子任務", "librarian", "{}", 1_783_940_000_000, "ses_1"),  # 子 session
            ("ses_3", proj.upper(), "大小寫路徑", "build", "{}", 1_783_930_000_000, None),
            ("ses_4", "C:/other/proj", "別的專案", "build", "{}", 1_783_960_000_000, None),
        ])
    con.executemany(
        "INSERT INTO todo VALUES (?, ?, ?, ?, ?)",
        [
            ("ses_1", "第一項", "completed", 0, 1),
            ("ses_1", "第二項", "in_progress", 1, 2),
            ("ses_1", "第三項", "pending", 2, 3),
        ])
    con.commit()
    con.close()
    (tmp_path / "myproj").mkdir()
    return {"db": db, "proj": tmp_path / "myproj"}


def test_recent_sessions_filters_and_converts(fake_ocdb):
    sessions = octools.recent_sessions(fake_ocdb["proj"], db_path=fake_ocdb["db"])
    ids = [s["id"] for s in sessions]
    assert "ses_1" in ids                                    # 本專案主 session
    assert "ses_2" not in ids                                # 子 agent 排除
    assert "ses_4" not in ids                                # 別的專案排除
    assert "ses_3" in ids                                    # 大小寫不敏感(P2)
    s1 = next(s for s in sessions if s["id"] == "ses_1")
    assert s1["updated_at"] == 1_783_950_000                 # 毫秒 → 秒(P1)
    assert s1["title"] == "設計架構"


def test_session_todos_completion(fake_ocdb):
    t = octools.session_todos("ses_1", db_path=fake_ocdb["db"])
    assert t["total"] == 3 and t["completed"] == 1 and t["in_progress"] == 1
    assert t["items"][0]["content"] == "第一項"


def test_project_activity_aggregate(fake_ocdb):
    a = octools.project_activity(fake_ocdb["proj"], db_path=fake_ocdb["db"])
    assert a["sessions"] and a["latest_todos"]["total"] == 3


# ── octools 容錯(外部 schema 鐵律)────────────────────────────────────

def test_octools_missing_db(tmp_path):
    assert octools.recent_sessions("x", db_path=tmp_path / "ghost.db") == []
    t = octools.session_todos("s", db_path=tmp_path / "ghost.db")
    assert t["total"] == 0


def test_octools_wrong_schema(tmp_path):
    db = tmp_path / "weird.db"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE session (id TEXT)")            # 缺欄位
    con.commit()
    con.close()
    assert octools.recent_sessions("x", db_path=db) == []    # 容錯不 crash


def test_octools_readonly_never_creates(tmp_path):
    ghost = tmp_path / "nothere.db"
    octools.recent_sessions("x", db_path=ghost)
    assert not ghost.exists()                                # 唯讀:不建檔


def test_octools_real_db_smoke():
    """對真 opencode.db 冒煙(存在時):本專案目錄有 session。"""
    if not octools.OPENCODE_DB.exists():
        pytest.skip("no real opencode.db")
    sessions = octools.recent_sessions(r"C:\Users\tcart\OneDrive\Desktop\MY AGENT")
    assert isinstance(sessions, list)                        # 不 crash 即可
