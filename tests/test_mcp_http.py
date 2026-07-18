"""part-006-slice-003:MCP HTTP/JSON-RPC 傳輸 + fail-closed bind guard。

同工具集(core/mcp/tools)的 HTTP 傳輸,綁 Tailscale IP 供遠端 OpenCode。
安全核心:綁公網 IP → 啟動拒絕(fail-closed)。Tailscale(100.64.0.0/10)、
loopback、私網 OK。共用 mcp_stdio.handle_request,不重複工具邏輯。

程式面本機可測;VPS + Tailscale 端到端 QA 標 blocked(等 VPS 階段)。
"""

import json

import pytest

from channels import mcp_http as H
from core import stm


@pytest.fixture()
def db(tmp_path):
    path = tmp_path / "state.db"
    stm.init(path)
    return path


# ── bind guard:公網拒絕、私網/loopback/Tailscale OK ──────────────────

@pytest.mark.parametrize("host", [
    "127.0.0.1",           # loopback
    "localhost",           # loopback name
    "100.64.0.1",          # Tailscale CGNAT 起
    "100.100.100.100",     # Tailscale 中段
    "100.127.255.254",     # Tailscale CGNAT 尾
    "10.0.0.5",            # 私網 A
    "192.168.1.10",        # 私網 C
    "172.16.5.5",          # 私網 B
])
def test_safe_bind_hosts_accepted(host):
    H.assert_safe_bind_host(host)                        # 不拋 = 通過


@pytest.mark.parametrize("host", [
    "0.0.0.0",             # 綁全部介面(含公網)→ 拒絕
    "8.8.8.8",             # 公網
    "1.1.1.1",             # 公網
    "203.0.113.5",         # 公網(TEST-NET-3 但非私網)
    "100.63.255.255",      # 剛好在 Tailscale range 之前(公網)
    "100.128.0.0",         # 剛好在 Tailscale range 之後(公網)
])
def test_public_bind_hosts_rejected(host):
    with pytest.raises(H.UnsafeBindError):
        H.assert_safe_bind_host(host)


def test_bind_guard_rejects_garbage():
    with pytest.raises(H.UnsafeBindError):
        H.assert_safe_bind_host("not-an-ip")


# ── bind host 來源:環境變數,未設 = 127.0.0.1 ───────────────────────

def test_resolve_bind_host_default(monkeypatch):
    import config
    monkeypatch.delenv(config.MCP_BIND_HOST_ENV, raising=False)
    assert H.resolve_bind_host() == "127.0.0.1"


def test_resolve_bind_host_from_env(monkeypatch):
    import config
    monkeypatch.setenv(config.MCP_BIND_HOST_ENV, "100.64.0.9")
    assert H.resolve_bind_host() == "100.64.0.9"


# ── HTTP JSON-RPC handle:共用 handle_request ─────────────────────────

def test_http_handle_tools_list(db):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    status, ctype, resp_body = H.handle_http_body(body, db=db)
    assert status == 200 and ctype == "application/json"
    resp = json.loads(resp_body)
    names = {t["name"] for t in resp["result"]["tools"]}
    assert "dev_status" in names and "directive_push" in names


def test_http_handle_directive_push(db):
    body = json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                       "params": {"name": "directive_push",
                                  "arguments": {"project": "my-agent", "text": "遠端指令"}}})
    status, _ctype, resp_body = H.handle_http_body(body, db=db)
    assert status == 200
    assert stm.directive_list(db, status="pending")[0]["text"] == "遠端指令"


def test_http_handle_bad_json_returns_parse_error(db):
    status, _ctype, resp_body = H.handle_http_body("{bad json", db=db)
    resp = json.loads(resp_body)
    assert resp["error"]["code"] == H.PARSE_ERROR


def test_http_handle_notification_returns_204(db):
    # 無 id = notification → 202/204 無內容
    body = json.dumps({"jsonrpc": "2.0", "method": "initialized"})
    status, _ctype, resp_body = H.handle_http_body(body, db=db)
    assert status in (202, 204) and resp_body == ""


# ── health 端點 ──────────────────────────────────────────────────────

def test_http_health(db):
    status, ctype, body = H.handle_health()
    assert status == 200 and json.loads(body) == {"ok": True}
