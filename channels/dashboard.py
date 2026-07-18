"""唯讀網頁儀表板(零依賴 stdlib http.server;part-003.5-slice-001)。

INTERFACES §5 介面權威。127.0.0.1:7777、SQLite `mode=ro` 物理唯讀、單頁 htmx。
六版塊:今日行程/待辦、專案進度、最近執行、管線游標、記憶狀態、事件流、指令佇列。

唯讀三層保證:
1. handler 只處理 GET;POST/PUT/DELETE/PATCH → 405(方法級)
2. SQLite `mode=ro` URI(連線級——寫入 = sqlite 錯誤)
3. 本模組不呼叫任何 stm 寫入函式(靜態保證,測試斷言)

決策:用標準庫 http.server 而非 FastAPI——對齊專案最小依賴哲學(同 slice-002
手寫 JSON-RPC)。核心是純函式 route(),可完整單元測試,不起真 server。

用法:`python -m channels.dashboard` → 綁 127.0.0.1:7777。
"""

from __future__ import annotations

import json
import sqlite3
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import config
from core import ltm

HOST = "127.0.0.1"
PORT = 7777


def _connect_ro(db: Path | None) -> sqlite3.Connection | None:
    """唯讀連線(mode=ro,物理唯讀)。檔案不存在/開啟失敗 → None。"""
    path = db or config.STATE_DB
    if not Path(path).exists():
        return None
    try:
        return sqlite3.connect(f"file:{Path(path).as_posix()}?mode=ro",
                               uri=True, timeout=3.0)
    except sqlite3.Error:
        return None


def _query_all(db: Path | None, sql: str, params: tuple = ()) -> list[dict]:
    """唯讀查詢 → list[dict]。表缺失/任何 sqlite 錯誤 → 空 list(容錯)。"""
    con = _connect_ro(db)
    if con is None:
        return []
    try:
        cur = con.execute(sql, params)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]
    except sqlite3.Error:
        return []
    finally:
        con.close()


def _int(query: dict, key: str, default: int) -> int:
    try:
        return int(query.get(key, [default])[0] if isinstance(query.get(key), list)
                   else query.get(key, default))
    except (ValueError, TypeError):
        return default


# ── API handlers(全唯讀)─────────────────────────────────────────────

def _api_today(db: Path | None) -> dict:
    schedule = _query_all(
        db, "SELECT id, title, start_at, remind_at, status FROM schedule "
            "WHERE status = 'active' ORDER BY start_at")
    tasks = _query_all(
        db, "SELECT id, title, due_at, status FROM tasks "
            "WHERE status IN ('pending','in_progress','waiting_user') "
            "ORDER BY due_at IS NULL, due_at")
    return {"schedule": schedule, "tasks": tasks}


def _api_projects(db: Path | None) -> list[dict]:
    return _query_all(
        db, "SELECT name, phase, blockers, next_action, updated_at FROM projects "
            "ORDER BY updated_at DESC")


def _api_runs(db: Path | None, limit: int) -> list[dict]:
    return _query_all(
        db, "SELECT id, started_at, finished_at, trigger, status, summary "
            "FROM agent_runs ORDER BY id DESC LIMIT ?", (limit,))


def _api_pipelines(db: Path | None) -> list[dict]:
    return _query_all(
        db, "SELECT pipeline, key, value, updated_at FROM cursors "
            "ORDER BY updated_at DESC")


def _api_memory(db: Path | None, vault: Path | None) -> dict:
    states = _query_all(
        db, "SELECT state, COUNT(*) AS n FROM events GROUP BY state")
    try:
        registry_count = len(ltm.registry_entries(vault or config.VAULT_PATH))
    except (OSError, ValueError):
        registry_count = 0
    return {"events": {s["state"]: s["n"] for s in states},
            "registry_count": registry_count}


def _api_events(db: Path | None, limit: int) -> list[dict]:
    return _query_all(
        db, "SELECT id, ts, actor, action, target, summary FROM events "
            "WHERE state = 'alive' ORDER BY ts DESC LIMIT ?", (limit,))


def _api_directives(db: Path | None) -> list[dict]:
    # directives 表缺失(part-006 未跑)→ _query_all 容錯回空
    return _query_all(
        db, "SELECT id, project, text, status, created_at, consumed_at "
            "FROM directives WHERE status = 'pending' ORDER BY created_at")


# ── route:純函式(可單元測試)─────────────────────────────────────────

_HTTP_STATUS = {200: "OK", 404: "Not Found", 405: "Method Not Allowed"}


def route(method: str, path: str, query: dict, *,
          db: Path | None = None, vault: Path | None = None
          ) -> tuple[int, str, str]:
    """回 (status, content_type, body)。非 GET → 405;未知路徑 → 404。"""
    if method != "GET":
        return 405, "application/json", json.dumps({"error": "read-only dashboard"})

    if path == "/":
        return 200, "text/html; charset=utf-8", _PAGE_HTML
    if path == "/health":
        return 200, "application/json", json.dumps({"ok": True})

    def j(obj) -> tuple[int, str, str]:
        return 200, "application/json", json.dumps(obj, ensure_ascii=False)

    if path == "/api/today":
        return j(_api_today(db))
    if path == "/api/projects":
        return j(_api_projects(db))
    if path == "/api/runs":
        return j(_api_runs(db, _int(query, "limit", 20)))
    if path == "/api/pipelines":
        return j(_api_pipelines(db))
    if path == "/api/memory":
        return j(_api_memory(db, vault))
    if path == "/api/events":
        return j(_api_events(db, _int(query, "limit", 50)))
    if path == "/api/directives":
        return j(_api_directives(db))

    return 404, "application/json", json.dumps({"error": "not found"})


# ── http.server handler(薄 adapter)──────────────────────────────────

class _Handler(BaseHTTPRequestHandler):
    db_path: Path | None = None
    vault_path: Path | None = None

    def _respond(self, method: str) -> None:
        parsed = urlparse(self.path)
        query = {k: v[0] if len(v) == 1 else v
                 for k, v in parse_qs(parsed.query).items()}
        status, ctype, body = route(method, parsed.path, query,
                                    db=self.db_path, vault=self.vault_path)
        payload = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:          # noqa: N802 — http.server API
        self._respond("GET")

    def do_POST(self) -> None:         # noqa: N802
        self._respond("POST")

    def do_PUT(self) -> None:          # noqa: N802
        self._respond("PUT")

    def do_DELETE(self) -> None:       # noqa: N802
        self._respond("DELETE")

    def log_message(self, *_args) -> None:   # 靜音預設 stderr log
        pass


def serve(host: str = HOST, port: int = PORT, *,
          db: Path | None = None, vault: Path | None = None) -> None:
    """啟動儀表板(阻塞)。綁 127.0.0.1——本機自用,不上公網。"""
    _Handler.db_path = db
    _Handler.vault_path = vault
    server = HTTPServer((host, port), _Handler)
    print(f"dashboard on http://{host}:{port} (read-only)")
    server.serve_forever()


_PAGE_HTML = """<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<title>Metatron 儀表板</title>
<style>
  body { font-family: system-ui, sans-serif; margin: 1.5rem; background: #f7f7f8; }
  h1 { font-size: 1.3rem; }
  .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 1rem; }
  .card { background: #fff; border-radius: 8px; padding: 1rem; box-shadow: 0 1px 3px rgba(0,0,0,.1); }
  .card h2 { font-size: 1rem; margin: 0 0 .5rem; color: #444; }
  pre { font-size: .8rem; white-space: pre-wrap; word-break: break-all; margin: 0; }
</style>
</head>
<body>
<h1>Metatron 儀表板 <small>(唯讀 · 127.0.0.1)</small></h1>
<div class="grid">
  <div class="card"><h2>今日行程/待辦</h2><pre id="today">載入中…</pre></div>
  <div class="card"><h2>專案進度</h2><pre id="projects">載入中…</pre></div>
  <div class="card"><h2>最近執行</h2><pre id="runs">載入中…</pre></div>
  <div class="card"><h2>管線游標</h2><pre id="pipelines">載入中…</pre></div>
  <div class="card"><h2>記憶狀態</h2><pre id="memory">載入中…</pre></div>
  <div class="card"><h2>事件流</h2><pre id="events">載入中…</pre></div>
  <div class="card"><h2>指令佇列</h2><pre id="directives">載入中…</pre></div>
</div>
<script>
  const panels = ["today","projects","runs","pipelines","memory","events","directives"];
  for (const p of panels) {
    fetch("/api/" + p)
      .then(r => r.json())
      .then(d => { document.getElementById(p).textContent = JSON.stringify(d, null, 2); })
      .catch(() => { document.getElementById(p).textContent = "(讀取失敗)"; });
  }
</script>
</body>
</html>
"""
