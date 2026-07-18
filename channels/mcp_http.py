"""MCP HTTP/JSON-RPC 傳輸 + fail-closed bind guard(part-006-slice-003)。

同工具集(core/mcp/tools)的 HTTP 傳輸,供 VPS 上遠端 OpenCode 連線。複用
mcp_stdio.handle_request——工具邏輯寫一次,stdio/http 兩 adapter 共用。

安全核心(Forbidden scope:公網曝露):**綁公網 IP → 啟動拒絕(fail-closed)**。
只允許 loopback、私網(RFC1918)、Tailscale(100.64.0.0/10 CGNAT)。Tailscale 是
WireGuard 加密私網,故不需 token/TLS。

決策:延續 slice-002 的零依賴——stdlib http.server + 同步 JSON-RPC 回應(唯讀 +
確認的用例不需完整 SSE streaming)。純函式可完整單元測試。

用法(VPS):設 MY_AGENT_MCP_BIND_HOST=<Tailscale IP> → `python -m channels.mcp_http`。
"""

from __future__ import annotations

import ipaddress
import json
import os
import socket
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import config
from channels.mcp_stdio import (
    INVALID_REQUEST,
    PARSE_ERROR,
    handle_request,
)

# Tailscale CGNAT range(100.64.0.0/10)
_TAILSCALE_NET = ipaddress.ip_network("100.64.0.0/10")

# 明確允許的私網範圍(RFC1918;不用 ipaddress.is_private——它涵蓋太多保留範圍如
# TEST-NET 203.0.113.0/24,那些不是真正可綁的私網)。
_ALLOWED_NETS = (
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    _TAILSCALE_NET,
)


class UnsafeBindError(ValueError):
    """嘗試綁公網 IP(fail-closed 拒絕)。"""


def _resolve_to_ip(host: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address:
    """host 名 → IP。'localhost' → 127.0.0.1;IP 字串直接解析。"""
    if host in ("localhost",):
        return ipaddress.ip_address("127.0.0.1")
    try:
        return ipaddress.ip_address(host)
    except ValueError:
        # 名稱:解析(但只接受解析到私網/loopback 的)
        try:
            resolved = socket.gethostbyname(host)
            return ipaddress.ip_address(resolved)
        except (socket.gaierror, ValueError) as e:
            raise UnsafeBindError(f"cannot resolve bind host: {host!r}") from e


def assert_safe_bind_host(host: str) -> None:
    """fail-closed:只允許 loopback / 私網 / Tailscale。其餘(含 0.0.0.0)→ 拒絕。"""
    if host == "0.0.0.0":       # noqa: S104 — 明確拒絕綁全部介面
        raise UnsafeBindError("refusing to bind 0.0.0.0 (all interfaces / public)")
    ip = _resolve_to_ip(host)
    if ip.is_loopback:
        return
    if ip.version == 4 and any(ip in net for net in _ALLOWED_NETS):
        return                          # RFC1918 私網 或 Tailscale CGNAT
    raise UnsafeBindError(
        f"refusing to bind public IP {host} — only loopback/private/Tailscale allowed")


def resolve_bind_host() -> str:
    """從環境變數讀綁定 host。未設 = 127.0.0.1(本機)。"""
    return os.environ.get(config.MCP_BIND_HOST_ENV, "127.0.0.1")


# ── HTTP body handlers(純函式,可單元測試)────────────────────────────

def handle_http_body(body: str, *, db: Path | None = None, _api=None
                     ) -> tuple[int, str, str]:
    """處理一個 HTTP JSON-RPC body。回 (status, content_type, response_body)。

    notification(無 id)→ 202 無內容;壞 JSON → parse error;否則同步回 JSON。
    """
    try:
        request = json.loads(body)
    except json.JSONDecodeError:
        err = {"jsonrpc": "2.0", "id": None,
               "error": {"code": PARSE_ERROR, "message": "invalid JSON"}}
        return 200, "application/json", json.dumps(err)

    if not isinstance(request, dict):
        err = {"jsonrpc": "2.0", "id": None,
               "error": {"code": INVALID_REQUEST, "message": "request must be object"}}
        return 200, "application/json", json.dumps(err)

    response = handle_request(request, db=db, _api=_api)
    if response is None:
        return 202, "application/json", ""      # notification:無回應內容
    return 200, "application/json", json.dumps(response, ensure_ascii=False)


def handle_health() -> tuple[int, str, str]:
    return 200, "application/json", json.dumps({"ok": True})


# ── http.server handler(薄 adapter)──────────────────────────────────

class _Handler(BaseHTTPRequestHandler):
    db_path: Path | None = None

    def do_GET(self) -> None:          # noqa: N802 — http.server API
        if self.path == "/health":
            self._write(*handle_health())
        else:
            self._write(404, "application/json",
                        json.dumps({"error": "not found; use POST for JSON-RPC"}))

    def do_POST(self) -> None:         # noqa: N802
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8") if length else ""
        self._write(*handle_http_body(body, db=self.db_path))

    def _write(self, status: int, ctype: str, body: str) -> None:
        payload = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        if payload:
            self.wfile.write(payload)

    def log_message(self, *_args) -> None:
        pass


def serve(host: str | None = None, port: int | None = None, *,
          db: Path | None = None) -> None:
    """啟動 HTTP MCP server(阻塞)。綁定前過 fail-closed bind guard。"""
    bind = host or resolve_bind_host()
    assert_safe_bind_host(bind)                 # 綁公網 → 啟動拒絕
    _Handler.db_path = db
    server = HTTPServer((bind, port or config.MCP_HTTP_PORT), _Handler)
    print(f"MCP HTTP on http://{bind}:{port or config.MCP_HTTP_PORT} "
          f"(JSON-RPC; bind guard passed)")
    server.serve_forever()


if __name__ == "__main__":
    serve()
