"""part-005-slice-002:track 管線(mock LLM 全路徑、幻覺專案名、部分掃描失敗、
writer 驗證 boundary、Phase 5 gate)。"""

import json
import subprocess

import pytest

from core import stm, track, writer


@pytest.fixture()
def env(tmp_path):
    db = tmp_path / "state.db"
    stm.init(db)
    # 真 git repo(有 .beacon)作為掃描目標
    repo = tmp_path / "proj"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=repo, check=True)
    (repo / "x.txt").write_text("x")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "feat: work in progress"], cwd=repo, check=True)
    beacon = repo / ".beacon"
    beacon.mkdir()
    (beacon / "CURRENT.md").write_text(
        "Part: part-002\nSlice: slice-001\nStatus: active\n\n## Goal\n\n做某功能。\n",
        encoding="utf-8")

    stm.project_set(db, "myproj", repo_path=str(repo))
    return {"db": db, "repo": repo}


def tracker_api(items):
    return lambda s, u, m, j: json.dumps({"projects": items})


GOOD_ITEM = {"name": "myproj", "phase": "part-002 slice-001 進行中",
             "blockers": [], "next_action": "完成功能", "confidence": 0.9}


# ── 全管線 ────────────────────────────────────────────────────────────

def test_full_pipeline_updates_project(env):
    stats = track.run(db=env["db"], _api=tracker_api([GOOD_ITEM]))
    assert stats == {"projects": 1, "scanned": 1, "updated": 1,
                     "rejected": 0, "batches_failed": 0}
    row = stm.project_show(env["db"], "myproj")[0]
    assert row["phase"] == "part-002 slice-001 進行中"
    assert row["next_action"] == "完成功能"
    assert row["blockers"] == []


def test_scan_feeds_real_three_sources_to_llm(env):
    """LLM 收到的 user prompt 含三源真資料(beacon part/git 訊息)。"""
    seen = {}
    def spy(s, u, m, j):
        seen["user"] = u
        return json.dumps({"projects": [GOOD_ITEM]})
    track.run(db=env["db"], _api=spy)
    assert "part-002" in seen["user"]                       # beacon 真資料
    assert "work in progress" in seen["user"]               # git 真資料
    assert "opencode:" in seen["user"]                      # opencode 欄位(空也要有)


def test_projects_without_repo_path_skipped(env):
    stm.project_set(env["db"], "no-repo-proj", phase="manual only")
    stats = track.run(db=env["db"], _api=tracker_api([GOOD_ITEM]))
    assert stats["projects"] == 1                            # 只掃有 repo_path 的


def test_no_projects_noop(tmp_path):
    db = tmp_path / "s.db"
    stm.init(db)
    called = []
    stats = track.run(db=db, _api=lambda *a: called.append(1))
    assert stats["projects"] == 0 and called == []           # 零專案不打 LLM


# ── 幻覺與驗證攔截 ───────────────────────────────────────────────────

def test_hallucinated_project_name_dropped(env):
    api = tracker_api([{**GOOD_ITEM, "name": "ghost-project"}])
    stats = track.run(db=env["db"], _api=api)
    assert stats["updated"] == 0
    rejected = [e for e in stm.event_query(env["db"], actor="coding_tracker")
                if e["action"] == "proposal_rejected"]
    assert rejected                                          # 幻覺名記 log


def test_unregistered_project_rejected_by_writer(env):
    """LLM 名字在掃描清單但 DB 已刪 → writer precheck 攔(不自動建專案)。"""
    pre = writer.precheck({
        "agent": "coding_tracker", "proposal_type": "project_update",
        "target": "never-registered",
        "payload": {"phase": "x", "blockers": [], "next_action": "y"},
        "confidence": 0.9, "evidence": ["scan"]}, env["db"])
    assert not pre.ok and "not registered" in pre.reason


@pytest.mark.parametrize("bad", [
    {"phase": ""},
    {"phase": "x" * 121},
    {"phase": None},
    {"blockers": "not-a-list"},
    {"blockers": [""]},
    {"blockers": ["b"] * 11},
    {"next_action": None},
    {"next_action": "x" * 121},
])
def test_writer_rejects_bad_project_update(env, bad):
    payload = {"phase": "ok", "blockers": [], "next_action": "ok"}
    payload.update(bad)
    pre = writer.precheck({
        "agent": "coding_tracker", "proposal_type": "project_update",
        "target": "myproj", "payload": payload,
        "confidence": 0.9, "evidence": ["scan"]}, env["db"])
    assert not pre.ok


def test_project_update_no_confirmation_needed(env):
    """免確認(DESIGN):Working State 快取,下輪自動修正。"""
    pre = writer.precheck({
        "agent": "coding_tracker", "proposal_type": "project_update",
        "target": "myproj",
        "payload": {"phase": "p", "blockers": [], "next_action": "n"},
        "confidence": 0.9, "evidence": ["scan"]}, env["db"])
    assert pre.ok and not pre.needs_confirm


# ── 失敗容忍 ─────────────────────────────────────────────────────────

def test_llm_failure_batch_skipped(env):
    def boom(s, u, m, j):
        raise ConnectionError("down")
    stats = track.run(db=env["db"], _api=boom)
    assert stats["batches_failed"] == 1 and stats["updated"] == 0
    # 專案原資料不動
    assert stm.project_show(env["db"], "myproj")[0]["phase"] is None


def test_broken_repo_path_still_processed(env, tmp_path):
    """壞 repo_path 的專案:三源給 null,LLM 照樣收到(契約會誠實回報)。"""
    stm.project_set(env["db"], "broken", repo_path=str(tmp_path / "ghost"))
    seen = {}
    def spy(s, u, m, j):
        seen["user"] = u
        return json.dumps({"projects": [GOOD_ITEM]})
    stats = track.run(db=env["db"], _api=spy)
    assert stats["scanned"] == 2                             # 壞的也掃(容錯)
    assert "broken" in seen["user"] and "null" in seen["user"]


def test_groups_not_list_tolerated(env):
    stats = track.run(db=env["db"],
                      _api=lambda s, u, m, j: '{"projects": "not a list"}')
    assert stats["updated"] == 0                             # 不 crash


# ── --job track 接線 + Phase 5 gate ──────────────────────────────────

def test_job_track_records_run(env, monkeypatch):
    from core import agent, track as track_mod
    monkeypatch.setattr(track_mod, "run",
                        lambda **kw: {"projects": 0, "scanned": 0, "updated": 0,
                                      "rejected": 0, "batches_failed": 0})
    rc = agent.job_track(env["db"])
    assert rc == 0
    con = stm.connect(env["db"])
    row = con.execute("SELECT status FROM agent_runs ORDER BY id DESC LIMIT 1").fetchone()
    con.close()
    assert row[0] == "ok"


def test_phase5_gate_three_source_auto_update(env):
    """Phase 5 gate:三源掃描(真 git+真 beacon)→ LLM → projects 表自動更新。"""
    stats = track.run(db=env["db"], _api=tracker_api([{
        "name": "myproj", "phase": "part-002 slice-001 進行中(自動追蹤)",
        "blockers": ["等待 API key"], "next_action": "完成功能後跑 gate",
        "confidence": 0.9}]))
    assert stats["updated"] == 1
    row = stm.project_show(env["db"], "myproj")[0]
    assert "自動追蹤" in row["phase"]
    assert row["blockers"] == ["等待 API key"]               # Phase 5 gate ✅
