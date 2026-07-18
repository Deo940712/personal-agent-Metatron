"""part-006-slice-002:MCP stdio server(手寫 JSON-RPC 2.0,零依賴)。

純函式 handle_request(dict) -> dict|None 可單元測試(不需 stdin/stdout)。
支援 initialize / tools/list / tools/call。錯誤回標準 JSON-RPC error。
notification(無 id)回 None(不回應)。
"""

import io
import json

import pytest

from channels import mcp_stdio as M
from core import stm


@pytest.fixture()
def db(tmp_path):
    path = tmp_path / "state.db"
    stm.init(path)
    return path


def _req(method, params=None, rid=1):
    r = {"jsonrpc": "2.0", "method": method}
    if params is not None:
        r["params"] = params
    if rid is not None:
        r["id"] = rid
    return r


# ── initialize ───────────────────────────────────────────────────────

def test_initialize_returns_capabilities(db):
    resp = M.handle_request(_req("initialize", {"protocolVersion": "2024-11-05"}), db=db)
    assert resp["jsonrpc"] == "2.0" and resp["id"] == 1
    assert "serverInfo" in resp["result"]
    assert "capabilities" in resp["result"]


# ── tools/list ───────────────────────────────────────────────────────

def test_tools_list_returns_all_tools(db):
    resp = M.handle_request(_req("tools/list"), db=db)
    tools = resp["result"]["tools"]
    names = {t["name"] for t in tools}
    assert "dev_status" in names and "directive_push" in names
    for t in tools:                                       # MCP schema shape
        assert "name" in t and "description" in t and "inputSchema" in t


# ── tools/call ───────────────────────────────────────────────────────

def test_tools_call_directive_push(db):
    resp = M.handle_request(_req("tools/call", {
        "name": "directive_push",
        "arguments": {"project": "my-agent", "text": "先跑 audit"}}), db=db)
    assert "result" in resp
    # MCP content 格式
    content = resp["result"]["content"]
    assert content[0]["type"] == "text"
    assert stm.directive_list(db, status="pending")


def test_tools_call_schedule_list(db):
    stm.schedule_add(db, "開會", 1_800_000_000)
    resp = M.handle_request(_req("tools/call", {
        "name": "schedule_list", "arguments": {}}), db=db)
    assert "開會" in resp["result"]["content"][0]["text"]


def test_tools_call_unknown_tool_returns_error(db):
    resp = M.handle_request(_req("tools/call", {
        "name": "nonexistent", "arguments": {}}), db=db)
    assert "error" in resp
    assert resp["error"]["code"] == M.METHOD_NOT_FOUND or resp["error"]["code"] < 0


# ── 錯誤處理 ─────────────────────────────────────────────────────────

def test_unknown_method_returns_error(db):
    resp = M.handle_request(_req("foo/bar"), db=db)
    assert "error" in resp and resp["error"]["code"] == M.METHOD_NOT_FOUND


def test_notification_returns_none(db):
    # 無 id = notification,不回應
    resp = M.handle_request(_req("initialized", rid=None), db=db)
    assert resp is None


def test_malformed_missing_method_returns_error(db):
    resp = M.handle_request({"jsonrpc": "2.0", "id": 5}, db=db)
    assert "error" in resp and resp["error"]["code"] == M.INVALID_REQUEST


# ── serve loop:讀一行 JSON-RPC → 寫一行回應 ─────────────────────────

def test_serve_processes_one_request(db):
    stdin = io.StringIO(json.dumps(_req("tools/list")) + "\n")
    stdout = io.StringIO()
    M.serve(stdin=stdin, stdout=stdout, db=db)
    lines = [ln for ln in stdout.getvalue().splitlines() if ln.strip()]
    assert len(lines) == 1
    resp = json.loads(lines[0])
    assert resp["id"] == 1 and "result" in resp


def test_serve_skips_blank_and_bad_json(db):
    stdin = io.StringIO("\n" + "not json\n" + json.dumps(_req("tools/list")) + "\n")
    stdout = io.StringIO()
    M.serve(stdin=stdin, stdout=stdout, db=db)
    lines = [ln for ln in stdout.getvalue().splitlines() if ln.strip()]
    # bad json 回 parse error;tools/list 回正常 → 至少有 tools/list 的成功回應
    parsed = [json.loads(ln) for ln in lines]
    assert any("result" in p for p in parsed)


def test_serve_bad_json_returns_parse_error(db):
    stdin = io.StringIO("{bad json\n")
    stdout = io.StringIO()
    M.serve(stdin=stdin, stdout=stdout, db=db)
    lines = [ln for ln in stdout.getvalue().splitlines() if ln.strip()]
    resp = json.loads(lines[0])
    assert resp["error"]["code"] == M.PARSE_ERROR
