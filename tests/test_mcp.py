"""part-006-slice-002:MCP 工具層(傳輸無關)。

core/mcp/tools.py 定義開發迴圈 4 工具 + 助理工具,每個有 JSON schema + handler。
handler 復用既有層(octools/scanners/stm/application),不繞過 writer/確認邊界。
寫入工具回 pending(需確認);confirm 工具落地。
"""

import json

import pytest

from core import stm
from core.mcp import tools as T


@pytest.fixture()
def db(tmp_path):
    path = tmp_path / "state.db"
    stm.init(path)
    return path


GOOD_SCHEDULE = json.dumps({
    "agent": "schedule", "proposal_type": "schedule_change", "target": "new",
    "payload": {"action": "add", "fields": {"title": "開會", "start_at": 1_800_000_000}},
    "confidence": 0.95, "evidence": ["明天開會"]})


def _api(text):
    return lambda s, u, m, j: text


# ── catalog:工具清單 + schema ────────────────────────────────────────

def test_catalog_lists_dev_loop_tools():
    names = {t.name for t in T.all_tools()}
    for expected in ("dev_status", "session_tail", "directive_push", "directive_list"):
        assert expected in names


def test_catalog_lists_assistant_tools():
    names = {t.name for t in T.all_tools()}
    for expected in ("schedule_list", "task_list", "project_status",
                     "schedule_add", "task_add", "confirm"):
        assert expected in names


def test_every_tool_has_schema_and_handler():
    for t in T.all_tools():
        assert t.name and t.description
        assert isinstance(t.input_schema, dict)
        assert t.input_schema.get("type") == "object"
        assert callable(t.handler)


def test_tool_names_unique():
    names = [t.name for t in T.all_tools()]
    assert len(names) == len(set(names))


# ── directive_push / directive_list ──────────────────────────────────

def test_directive_push_creates_pending(db):
    result = T.call("directive_push",
                    {"project": "my-agent", "text": "先跑 audit"}, db=db)
    assert result["ok"] is True
    pending = stm.directive_list(db, status="pending")
    assert len(pending) == 1 and pending[0]["text"] == "先跑 audit"


def test_directive_list_returns_pending(db):
    stm.directive_add(db, "my-agent", "task A")
    result = T.call("directive_list", {"project": "my-agent"}, db=db)
    assert result["ok"] is True
    assert any(d["text"] == "task A" for d in result["directives"])


def test_directive_push_rejects_empty(db):
    result = T.call("directive_push", {"project": "p", "text": ""}, db=db)
    assert result["ok"] is False                          # 空 text 拒絕(不 crash)


# ── 唯讀查詢工具 ─────────────────────────────────────────────────────

def test_schedule_list_tool(db):
    stm.schedule_add(db, "開會", 1_800_000_000)
    result = T.call("schedule_list", {}, db=db)
    assert result["ok"] and "開會" in result["text"]


def test_task_list_tool(db):
    stm.task_add(db, "買貓砂")
    result = T.call("task_list", {}, db=db)
    assert result["ok"] and "買貓砂" in result["text"]


def test_project_status_tool(db):
    stm.project_set(db, "my-agent", phase="part-006")
    result = T.call("project_status", {}, db=db)
    assert result["ok"] and "my-agent" in result["text"]


# ── 寫入工具:回 pending(需確認),不直接落地 ────────────────────────

def test_schedule_add_returns_pending(db):
    result = T.call("schedule_add", {"text": "明天下午兩點開會"}, db=db,
                    _api=_api(GOOD_SCHEDULE))
    assert result["ok"] and result["needs_confirmation"] is True
    assert result["pending_id"] is not None
    assert stm.schedule_list(db) == []                    # 尚未落地


def test_task_add_returns_pending(db):
    result = T.call("task_add", {"text": "買貓砂"}, db=db)
    assert result["needs_confirmation"] is True
    assert result["pending_id"] is not None


# ── confirm 工具:落地 ───────────────────────────────────────────────

def test_confirm_applies_pending(db):
    add = T.call("schedule_add", {"text": "明天下午兩點開會"}, db=db,
                 _api=_api(GOOD_SCHEDULE))
    pid = add["pending_id"]
    result = T.call("confirm", {"pending_id": pid, "approve": True}, db=db)
    assert result["ok"]
    assert stm.schedule_list(db)[0]["title"] == "開會"     # 確認後落地


def test_confirm_decline_cancels(db):
    add = T.call("task_add", {"text": "不要的事"}, db=db)
    pid = add["pending_id"]
    T.call("confirm", {"pending_id": pid, "approve": False}, db=db)
    assert stm.task_list(db) == []                        # 取消不落地


# ── 未知工具:拒絕 ───────────────────────────────────────────────────

def test_unknown_tool_rejected(db):
    with pytest.raises(T.ToolError):
        T.call("delete_everything", {}, db=db)


# ── dev_status:三源(容錯,無真 opencode.db 也不 crash)────────────────

def test_dev_status_no_crash(db, tmp_path):
    stm.project_set(db, "my-agent", phase="part-006", repo_path=str(tmp_path))
    result = T.call("dev_status", {"project": "my-agent"}, db=db)
    assert result["ok"] is True
    assert "sources" in result                            # 三源結構


def test_dev_status_accepts_direct_path(db, tmp_path):
    """part-012 修:project 直接傳路徑(未註冊)也能查——git/beacon 掃該路徑。"""
    # tmp_path 不是 git repo,但 handler 應嘗試掃描而非因未註冊直接跳過
    result = T.call("dev_status", {"project": str(tmp_path)}, db=db)
    assert result["ok"] is True
    assert "sources" in result
    # repo 有解析到(不是 None)——三源都被嘗試(即使掃描結果為 None)
    assert result["project"] == str(tmp_path)


def test_dev_status_registered_name_still_works(db, tmp_path):
    """已註冊專案名仍走 repo_path(向後相容)。"""
    stm.project_set(db, "reg-proj", phase="p1", repo_path=str(tmp_path))
    result = T.call("dev_status", {"project": "reg-proj"}, db=db)
    assert result["ok"] is True and "phase=p1" in result["text"]


# ── dev_plan:讀 OpenCode session todo 進度(part-014)────────────────────

def test_dev_plan_registered(db, tmp_path, monkeypatch):
    from core import octools
    stm.project_set(db, "myp", phase="p1", repo_path=str(tmp_path))
    monkeypatch.setattr(octools, "recent_sessions",
                        lambda d, **k: [{"id": "ses_1", "title": "做 X 功能",
                                         "updated_at": 1}])
    monkeypatch.setattr(octools, "session_todos",
                        lambda sid, **k: {"total": 5, "completed": 3,
                                          "in_progress": 1,
                                          "items": [{"content": "步驟 A",
                                                     "status": "completed"}]})
    r = T.call("dev_plan", {"project": "myp"}, db=db)
    assert r["ok"] is True
    assert "做 X 功能" in r["text"]
    assert "3/5" in r["text"]                              # 進度


def test_dev_plan_direct_path(db, tmp_path, monkeypatch):
    """未註冊 → 直接傳路徑(同 dev_status fallback)。"""
    from core import octools
    monkeypatch.setattr(octools, "recent_sessions", lambda d, **k: [])
    r = T.call("dev_plan", {"project": str(tmp_path)}, db=db)
    assert r["ok"] is True
    assert r["project"] == str(tmp_path)


def test_dev_plan_no_session_no_crash(db, tmp_path, monkeypatch):
    from core import octools
    stm.project_set(db, "empty-proj", phase="p1", repo_path=str(tmp_path))
    monkeypatch.setattr(octools, "recent_sessions", lambda d, **k: [])
    r = T.call("dev_plan", {"project": "empty-proj"}, db=db)
    assert r["ok"] is True and "沒有" in r["text"]


def test_dev_plan_in_tool_list():
    from channels import mcp_stdio
    resp = mcp_stdio.handle_request(
        {"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    names = [t["name"] for t in resp["result"]["tools"]]
    assert "dev_plan" in names
    assert len(names) == 11                                # 10 + dev_plan
