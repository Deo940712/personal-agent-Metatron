"""MCP stdio server(手寫 JSON-RPC 2.0,零依賴;part-006-slice-002)。

決策:專案核心哲學是最小依賴(pyproject 只有 openai + sqlite-vec),官方 `mcp`
SDK 未安裝且過重。JSON-RPC 2.0 協定穩定,手寫零依賴、可完整單元測試,對齊
「薄 adapter」哲學(DESIGN Global Risks:「或手寫 JSON-RPC」)。

支援 MCP 核心方法:initialize / tools/list / tools/call。傳輸只做 JSON-RPC 收發,
所有工具邏輯在 core/mcp/tools.py。寫入仍走 writer/確認邊界(工具回 pending)。

用法:OpenCode config 指向 `python -m channels.mcp_stdio`。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import TextIO

from core.mcp import tools as T

# JSON-RPC 2.0 標準錯誤碼
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603

_PROTOCOL_VERSION = "2024-11-05"
_SERVER_INFO = {"name": "my-agent", "version": "0.1.0"}


def _result(rid, result: dict) -> dict:
    return {"jsonrpc": "2.0", "id": rid, "result": result}


def _error(rid, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": rid, "error": {"code": code, "message": message}}


def _tool_to_mcp(tool: T.Tool) -> dict:
    return {"name": tool.name, "description": tool.description,
            "inputSchema": tool.input_schema}


def handle_request(request: dict, *, db: Path | None = None, _api=None) -> dict | None:
    """處理一個 JSON-RPC request。notification(無 id)→ None(不回應)。"""
    if not isinstance(request, dict):
        return _error(None, INVALID_REQUEST, "request must be an object")
    rid = request.get("id")
    method = request.get("method")

    if not isinstance(method, str):
        # 無 method:若是 notification(無 id)則忽略,否則 invalid
        if rid is None:
            return None
        return _error(rid, INVALID_REQUEST, "missing method")

    # notification(無 id):MCP 的 initialized 等,不回應
    is_notification = "id" not in request
    if is_notification:
        return None

    if method == "initialize":
        return _result(rid, {
            "protocolVersion": _PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": _SERVER_INFO,
        })

    if method == "tools/list":
        return _result(rid, {"tools": [_tool_to_mcp(t) for t in T.all_tools()]})

    if method == "tools/call":
        params = request.get("params", {})
        name = params.get("name", "")
        args = params.get("arguments", {}) or {}
        try:
            out = T.call(name, args, db=db, _api=_api)
        except T.ToolError:
            return _error(rid, METHOD_NOT_FOUND, f"unknown tool: {name}")
        except Exception as e:                      # noqa: BLE001 — 工具內部錯不能拖垮 server
            return _error(rid, INTERNAL_ERROR, f"{type(e).__name__}: {e}")
        text = out.get("text", "")
        return _result(rid, {
            "content": [{"type": "text", "text": text}],
            "isError": not out.get("ok", True),
            "_meta": {k: v for k, v in out.items() if k != "text"},
        })

    return _error(rid, METHOD_NOT_FOUND, f"unknown method: {method}")


def serve(*, stdin: TextIO | None = None, stdout: TextIO | None = None,
          db: Path | None = None) -> None:
    """讀一行 JSON-RPC → 寫一行回應。EOF 結束。壞 JSON 回 parse error。"""
    fin = stdin or sys.stdin
    fout = stdout or sys.stdout
    for line in fin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            _write(fout, _error(None, PARSE_ERROR, "invalid JSON"))
            continue
        response = handle_request(request, db=db)
        if response is not None:
            _write(fout, response)


def _write(fout: TextIO, obj: dict) -> None:
    fout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    fout.flush()


if __name__ == "__main__":
    serve()
