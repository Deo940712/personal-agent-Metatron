"""part-003.5-slice-001:唯讀網頁儀表板(零依賴 stdlib http.server)。

純函式 route(method, path, query, db, vault) -> (status, content_type, body)。
八個 GET API + 單頁 HTML;非 GET → 405;空 DB 回空陣列不炸;directives 表缺失容錯;
mode=ro 物理唯讀。TestClient 不需要——直接測 route。
"""

import json

import pytest

from channels import dashboard as D
from core import stm


@pytest.fixture()
def db(tmp_path):
    path = tmp_path / "state.db"
    stm.init(path)
    return path


@pytest.fixture()
def vault(tmp_path):
    from core import ltm
    v = tmp_path / "vault"
    ltm.init_vault(v)
    return v


def _json(status, ctype, body):
    assert status == 200 and ctype == "application/json"
    return json.loads(body)


# ── 單頁 HTML ─────────────────────────────────────────────────────────

def test_root_returns_html(db, vault):
    status, ctype, body = D.route("GET", "/", {}, db=db, vault=vault)
    assert status == 200 and ctype.startswith("text/html")
    assert "<html" in body.lower() and "儀表板" in body


def test_health(db, vault):
    status, ctype, body = D.route("GET", "/health", {}, db=db, vault=vault)
    data = _json(status, ctype, body)
    assert data == {"ok": True}


# ── GET API:真資料 ──────────────────────────────────────────────────

def test_today_returns_schedule_and_tasks(db, vault):
    stm.schedule_add(db, "開會", 1_800_000_000)
    stm.task_add(db, "買貓砂")
    data = _json(*D.route("GET", "/api/today", {}, db=db, vault=vault))
    titles = [s["title"] for s in data["schedule"]] + [t["title"] for t in data["tasks"]]
    assert "開會" in titles and "買貓砂" in titles


def test_projects(db, vault):
    stm.project_set(db, "my-agent", phase="part-003.5")
    data = _json(*D.route("GET", "/api/projects", {}, db=db, vault=vault))
    assert any(p["name"] == "my-agent" for p in data)


def test_runs_with_limit(db, vault):
    con = stm.connect(db)
    for _ in range(3):
        con.execute("INSERT INTO agent_runs (started_at, trigger, status) VALUES (?,?,?)",
                    (stm.now(), "cli", "ok"))
    con.commit()
    con.close()
    data = _json(*D.route("GET", "/api/runs", {"limit": "2"}, db=db, vault=vault))
    assert len(data) == 2                                 # limit 生效


def test_pipelines(db, vault):
    stm.cursor_set(db, "threads", "last_id", "abc")
    data = _json(*D.route("GET", "/api/pipelines", {}, db=db, vault=vault))
    assert any(c["pipeline"] == "threads" for c in data)


def test_memory_stats(db, vault):
    stm.event_append(db, "user", "decision", "定案")
    data = _json(*D.route("GET", "/api/memory", {}, db=db, vault=vault))
    assert "events" in data and "registry_count" in data


def test_events_stream(db, vault):
    stm.event_append(db, "user", "note", "事件一")
    data = _json(*D.route("GET", "/api/events", {"limit": "10"}, db=db, vault=vault))
    assert any("事件一" in e["summary"] for e in data)


def test_directives_panel(db, vault):
    stm.directive_add(db, "my-agent", "先跑 audit")
    data = _json(*D.route("GET", "/api/directives", {}, db=db, vault=vault))
    assert any(d["text"] == "先跑 audit" for d in data)


# ── 空 DB:回空陣列不炸 ──────────────────────────────────────────────

def test_empty_db_returns_empty(db, vault):
    for path in ("/api/today", "/api/projects", "/api/runs", "/api/pipelines",
                 "/api/events", "/api/directives"):
        status, ctype, body = D.route("GET", path, {}, db=db, vault=vault)
        assert status == 200                              # 不炸
        json.loads(body)                                  # 合法 JSON


# ── directives 表缺失(part-006 未跑情境)→ 容錯回空 ───────────────────

def test_directives_missing_table_tolerated(tmp_path, vault):
    """建一個只有部分表的 DB(無 directives)→ /api/directives 回空不炸。"""
    import sqlite3
    partial = tmp_path / "partial.db"
    con = sqlite3.connect(partial)
    con.execute("CREATE TABLE schedule (id INTEGER PRIMARY KEY, title TEXT, "
                "start_at INTEGER, status TEXT DEFAULT 'active')")
    con.commit()
    con.close()
    status, ctype, body = D.route("GET", "/api/directives", {}, db=partial, vault=vault)
    assert status == 200 and json.loads(body) == []       # 容錯


# ── 唯讀:非 GET → 405 ───────────────────────────────────────────────

@pytest.mark.parametrize("method", ["POST", "PUT", "DELETE", "PATCH"])
@pytest.mark.parametrize("path", ["/api/today", "/api/directives", "/health", "/"])
def test_non_get_returns_405(db, vault, method, path):
    status, _ctype, _body = D.route(method, path, {}, db=db, vault=vault)
    assert status == 405


# ── 未知路徑 → 404 ───────────────────────────────────────────────────

def test_unknown_path_404(db, vault):
    status, _ctype, _body = D.route("GET", "/api/nonexistent", {}, db=db, vault=vault)
    assert status == 404


# ── mode=ro 物理唯讀實證 ─────────────────────────────────────────────

def test_dashboard_connection_is_readonly(db, vault):
    """dashboard 的連線嘗試寫入 → sqlite 錯誤(mode=ro 保證)。"""
    import sqlite3
    con = D._connect_ro(db)
    assert con is not None
    with pytest.raises(sqlite3.OperationalError):
        con.execute("INSERT INTO tasks (title, created_at) VALUES ('x', 1)")
        con.commit()
    con.close()


def test_module_has_no_stm_write_calls():
    """dashboard 模組不呼叫任何 stm 寫入函式(靜態保證)。"""
    import inspect
    src = inspect.getsource(D)
    for writer in ("schedule_add", "task_add", "directive_add", "project_set",
                   "event_append", "pending_add", "cursor_set", "directive_consume"):
        assert writer not in src, f"dashboard must not call stm.{writer}"
