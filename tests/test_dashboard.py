"""part-003.5-slice-001:唯讀網頁儀表板(零依賴 stdlib http.server)。

純函式 route(method, path, query, db, vault) -> (status, content_type, body)。
八個 GET API + 單頁 HTML;非 GET → 405;空 DB 回空陣列不炸;directives 表缺失容錯;
mode=ro 物理唯讀。TestClient 不需要——直接測 route。
"""

import json
from io import BytesIO

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
    assert "JSON.stringify(d, null, 2)" not in body
    assert "活動時間線" in body and "待確認" in body
    assert ".small{min-height:2.75rem" in body
    assert "word-break:keep-all;overflow-wrap:anywhere" in body


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


def test_pending_panel_returns_only_pending(db, vault):
    proposal = {
        "agent": "schedule", "proposal_type": "task_change", "target": "new",
        "payload": {"action": "add", "fields": {"title": "買貓砂"}},
        "confidence": 1.0, "evidence": ["todo 買貓砂"],
    }
    pending_id = stm.pending_add(db, proposal, "新增待辦：買貓砂")
    done_id = stm.pending_add(db, proposal, "已處理")
    stm.pending_set_status(db, done_id, "done")

    data = _json(*D.route("GET", "/api/pending", {}, db=db, vault=vault))

    assert [row["id"] for row in data] == [pending_id]
    assert data[0]["preview"] == "新增待辦：買貓砂"


def test_timeline_merges_runs_and_events(db, vault):
    con = stm.connect(db)
    con.execute(
        "INSERT INTO agent_runs (started_at, finished_at, trigger, status, summary) "
        "VALUES (?,?,?,?,?)", (100, 110, "chat", "ok", "knowledge:answered"))
    con.commit()
    con.close()
    stm.event_append(db, "writer", "state_change", "task done")

    data = _json(*D.route("GET", "/api/timeline", {"limit": "10"}, db=db, vault=vault))

    assert {row["kind"] for row in data} == {"run", "event"}
    assert data == sorted(data, key=lambda row: row["ts"], reverse=True)


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
def test_non_allowlisted_write_returns_405(db, vault, method, path):
    status, _ctype, _body = D.route(method, path, {}, db=db, vault=vault, body={})
    assert status == 405


def test_post_confirm_applies_pending_via_writer(db, vault):
    proposal = {
        "agent": "schedule", "proposal_type": "task_change", "target": "new",
        "payload": {"action": "add", "fields": {"title": "買貓砂"}},
        "confidence": 1.0, "evidence": ["todo 買貓砂"],
    }
    pending_id = stm.pending_add(db, proposal, "新增待辦：買貓砂")

    data = _json(*D.route(
        "POST", "/api/confirm", {}, db=db, vault=vault,
        body={"pending_id": pending_id, "approve": True},
    ))

    assert data["ok"] is True
    assert stm.task_list(db)[0]["title"] == "買貓砂"


def test_post_confirm_rejects_bad_body(db, vault):
    status, ctype, body = D.route(
        "POST", "/api/confirm", {}, db=db, vault=vault,
        body={"pending_id": True, "approve": "yes"},
    )
    assert status == 400 and ctype == "application/json"
    assert json.loads(body)["ok"] is False


def test_post_done_uses_capability_writer_path(db, vault):
    task_id = stm.task_add(db, "買貓砂")

    data = _json(*D.route(
        "POST", "/api/done", {}, db=db, vault=vault,
        body={"reference": f"task {task_id}"},
    ))

    assert data["ok"] is True
    assert stm.task_list(db, status="done")[0]["id"] == task_id


def test_post_done_rejects_bad_body(db, vault):
    status, ctype, body = D.route(
        "POST", "/api/done", {}, db=db, vault=vault, body={"reference": 3},
    )
    assert status == 400 and ctype == "application/json"
    assert json.loads(body)["ok"] is False


def test_handler_rejects_cross_site_post():
    handler = object.__new__(D._Handler)
    handler.headers = {"Content-Type": "application/json", "Sec-Fetch-Site": "cross-site"}
    handler.rfile = BytesIO(b'{"reference":"task 1"}')
    assert handler._read_json() is None


def test_handler_requires_json_content_type():
    handler = object.__new__(D._Handler)
    handler.headers = {"Content-Type": "text/plain", "Content-Length": "22"}
    handler.rfile = BytesIO(b'{"reference":"task 1"}')
    assert handler._read_json() is None


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
    for writer in ("stm.schedule_add", "stm.task_add", "stm.directive_add", "stm.project_set",
                   "stm.event_append", "stm.pending_add", "stm.cursor_set",
                   "stm.directive_consume"):
        assert writer not in src, f"dashboard must not call stm.{writer}"


# ── W1: Content-Length boundary checks ─────────────────────────────

@pytest.mark.parametrize('raw_len, body, label', [
    ('',        None, 'missing header'),
    ('0',       None, 'zero'),
    ('-1',      None, 'negative'),
    ('9999999', None, 'oversize'),
    ('abc',     None, 'non-numeric'),
    ('22',      b'{"reference":"task 1"}', 'valid'),
])
def test_read_json_content_length_bounds(raw_len, body, label):
    handler = object.__new__(D._Handler)
    headers = {'Content-Type': 'application/json'}
    if raw_len:
        headers['Content-Length'] = raw_len
    handler.headers = headers
    if body is not None:
        handler.rfile = BytesIO(body)
    result = handler._read_json()
    if body is not None:
        assert result is not None, f'valid body should parse ({label})'
    else:
        assert result is None, f'invalid Content-Length returned {result!r} ({label})'


# ── M2: structured outcomes ───────────────────────────────────────

def test_confirm_uses_structured_outcome(db, vault):
    proposal = {
        'agent': 'schedule', 'proposal_type': 'task_change', 'target': 'new',
        'payload': {'action': 'add', 'fields': {'title': 'M2 test'}},
        'confidence': 1.0, 'evidence': ['todo test'],
    }
    pending_id = stm.pending_add(db, proposal, 'add M2')
    data = _json(*D.route(
        'POST', '/api/confirm', {}, db=db, vault=vault,
        body={'pending_id': pending_id, 'approve': True},
    ))
    assert data['ok'] is True
    assert data['outcome'] == 'confirmed'
    assert stm.task_list(db)[0]['title'] == 'M2 test'


def test_done_uses_structured_outcome(db, vault):
    task_id = stm.task_add(db, 'done M2 test')
    data = _json(*D.route(
        'POST', '/api/done', {}, db=db, vault=vault,
        body={'reference': f'task {task_id}'},
    ))
    assert data['ok'] is True
    assert data['outcome'] == 'done'



def test_post_confirm_custom_vault_uses_paired_index(db, tmp_path, monkeypatch):
    """W2: custom-vault confirmation must not write production index.db."""
    from core import ltm
    custom_vault = tmp_path / "custom-vault"
    ltm.init_vault(custom_vault)
    production_index = tmp_path / "production-index.db"
    monkeypatch.setattr(D.config, "INDEX_DB", production_index)
    proposal = {
        "agent": "orchestrator", "proposal_type": "note_write", "target": "new",
        "payload": {"action": "create", "title": "隔離測試", "body": "custom vault", "tags": ["misc"]},
        "confidence": 1.0, "evidence": ["隔離測試"],
    }
    pending_id = stm.pending_add(db, proposal, "新增隔離測試")
    data = _json(*D.route(
        "POST", "/api/confirm", {}, db=db, vault=custom_vault,
        body={"pending_id": pending_id, "approve": True},
    ))
    assert data["ok"] is True
    assert (custom_vault.parent / "index.db").exists()
    assert not production_index.exists()
