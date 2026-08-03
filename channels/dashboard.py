"""Metatron 本機儀表板：唯讀總覽 + 受限 confirm/done 操作。"""

from __future__ import annotations

import json
import sqlite3
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import TypeAlias
from urllib.parse import parse_qs, urlparse

import config
from channels.dashboard_page import PAGE_HTML
from core import chat, ltm
from core.tools import tasks
from core.tools.contracts import CapabilityContext

HOST = "127.0.0.1"
PORT = 7777
MAX_POST_BODY = 65536   # W1: Content-Length upper bound (1 MiB is overkill for JSON)

JsonBody: TypeAlias = dict[str, str | int | bool]
RouteResult: TypeAlias = tuple[int, str, str]


def _connect_ro(db: Path | None) -> sqlite3.Connection | None:
    """以 SQLite mode=ro 開啟 DB；不存在或開啟失敗回 None。"""
    path = db or config.STATE_DB
    if not Path(path).exists():
        return None
    try:
        return sqlite3.connect(
            f"file:{Path(path).as_posix()}?mode=ro", uri=True, timeout=3.0
        )
    except sqlite3.Error:
        return None


def _query_all(db: Path | None, sql: str, params: tuple = ()) -> list[dict]:
    """唯讀查詢；缺表或 SQLite 錯誤時回空陣列。"""
    con = _connect_ro(db)
    if con is None:
        return []
    try:
        cur = con.execute(sql, params)
        cols = [description[0] for description in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]
    except sqlite3.Error:
        return []
    finally:
        con.close()


def _int(query: dict, key: str, default: int) -> int:
    try:
        raw = query.get(key, default)
        return int(raw[0] if isinstance(raw, list) else raw)
    except (TypeError, ValueError):
        return default


def _api_today(db: Path | None) -> dict:
    schedule = _query_all(
        db,
        "SELECT id,title,start_at,remind_at,status FROM schedule "
        "WHERE status='active' ORDER BY start_at",
    )
    task_rows = _query_all(
        db,
        "SELECT id,title,due_at,status FROM tasks "
        "WHERE status IN ('pending','in_progress','waiting_user') "
        "ORDER BY due_at IS NULL,due_at",
    )
    return {"schedule": schedule, "tasks": task_rows}


def _api_projects(db: Path | None) -> list[dict]:
    return _query_all(
        db,
        "SELECT name,phase,blockers,next_action,updated_at FROM projects "
        "ORDER BY updated_at DESC",
    )


def _api_runs(db: Path | None, limit: int) -> list[dict]:
    return _query_all(
        db,
        "SELECT id,started_at,finished_at,trigger,status,summary "
        "FROM agent_runs ORDER BY id DESC LIMIT ?",
        (limit,),
    )


def _api_pipelines(db: Path | None) -> list[dict]:
    return _query_all(
        db,
        "SELECT pipeline,key,value,updated_at FROM cursors ORDER BY updated_at DESC",
    )


def _api_memory(db: Path | None, vault: Path | None) -> dict:
    states = _query_all(db, "SELECT state,COUNT(*) AS n FROM events GROUP BY state")
    try:
        registry_count = len(ltm.registry_entries(vault or config.VAULT_PATH))
    except (OSError, ValueError):
        registry_count = 0
    return {
        "events": {row["state"]: row["n"] for row in states},
        "registry_count": registry_count,
    }


def _api_events(db: Path | None, limit: int) -> list[dict]:
    return _query_all(
        db,
        "SELECT id,ts,actor,action,target,summary FROM events "
        "WHERE state='alive' ORDER BY ts DESC LIMIT ?",
        (limit,),
    )


def _api_directives(db: Path | None) -> list[dict]:
    return _query_all(
        db,
        "SELECT id,project,text,status,created_at,consumed_at FROM directives "
        "WHERE status='pending' ORDER BY created_at",
    )


def _api_pending(db: Path | None) -> list[dict]:
    return _query_all(
        db,
        "SELECT id,preview,status,channel_ref,created_at FROM pending_proposals "
        "WHERE status='pending' ORDER BY created_at,id",
    )


def _api_timeline(db: Path | None, limit: int) -> list[dict]:
    runs = [
        {
            "kind": "run",
            "id": row["id"],
            "ts": row["started_at"],
            "title": f"{row['trigger']} / {row['status'] or 'running'}",
            "detail": row["summary"] or "執行中",
        }
        for row in _api_runs(db, limit)
    ]
    events = [
        {
            "kind": "event",
            "id": row["id"],
            "ts": row["ts"],
            "title": f"{row['actor']} / {row['action']}",
            "detail": row["summary"],
        }
        for row in _api_events(db, limit)
    ]
    return sorted(runs + events, key=lambda row: row["ts"], reverse=True)[:limit]


def _json(status: int, value) -> RouteResult:
    return status, "application/json", json.dumps(value, ensure_ascii=False)


def _confirm_idx_db(vault: Path | None) -> Path | None:
    """W2: compute paired idx_db when a custom vault is in use.

    Production (vault=None or vault==config.VAULT_PATH) → None so the
    confirm chain falls back to ``config.INDEX_DB``.  A custom vault gets
    its own ``vault.parent / "index.db"`` to prevent K2-style production
    index pollution (KNOWN_ISSUES W2).
    """
    if vault is None:
        return None
    prod_vault = Path(config.VAULT_PATH).resolve() if hasattr(config, 'VAULT_PATH') else None
    if prod_vault is not None and Path(vault).resolve() == prod_vault:
        return None
    return Path(vault).parent / "index.db"


def _post_confirm(body: JsonBody | None, db: Path | None, vault: Path | None) -> RouteResult:
    if body is None:
        return _json(400, {"ok": False, "text": "缺少 JSON body"})
    pending_id = body.get("pending_id")
    approve = body.get("approve")
    if isinstance(pending_id, bool) or not isinstance(pending_id, int) \
            or not isinstance(approve, bool):
        return _json(400, {"ok": False, "text": "pending_id/approve 格式錯誤"})
    reply = chat.confirm(pending_id, approve, db=db, vault=vault,
                         idx_db=_confirm_idx_db(vault))
    # M2: use structured outcome, not display-text parsing
    ok = reply.outcome == "confirmed" or reply.outcome == "cancelled"
    return _json(200, {"ok": ok, "outcome": reply.outcome, "text": reply.text})


def _post_done(body: JsonBody | None, db: Path | None) -> RouteResult:
    if body is None or not isinstance(body.get("reference"), str):
        return _json(400, {"ok": False, "text": "reference 必須是字串"})
    result = tasks.complete(body["reference"], CapabilityContext(db=db))
    ok = result.outcome == "done"
    return _json(200, {"ok": ok, "outcome": result.outcome, "text": result.text})


def route(
    method: str,
    path: str,
    query: dict,
    *,
    db: Path | None = None,
    vault: Path | None = None,
    body: JsonBody | None = None,
) -> RouteResult:
    """純函式 HTTP router；只有兩個 POST path 可改狀態。"""
    if method == "POST" and path == "/api/confirm":
        return _post_confirm(body, db, vault)
    if method == "POST" and path == "/api/done":
        return _post_done(body, db)
    if method != "GET":
        return _json(405, {"error": "method not allowed"})
    if path == "/":
        return 200, "text/html; charset=utf-8", PAGE_HTML
    if path == "/health":
        return _json(200, {"ok": True})

    endpoints = {
        "/api/today": lambda: _api_today(db),
        "/api/projects": lambda: _api_projects(db),
        "/api/runs": lambda: _api_runs(db, _int(query, "limit", 20)),
        "/api/pipelines": lambda: _api_pipelines(db),
        "/api/memory": lambda: _api_memory(db, vault),
        "/api/events": lambda: _api_events(db, _int(query, "limit", 50)),
        "/api/directives": lambda: _api_directives(db),
        "/api/pending": lambda: _api_pending(db),
        "/api/timeline": lambda: _api_timeline(db, _int(query, "limit", 40)),
    }
    handler = endpoints.get(path)
    return _json(200, handler()) if handler is not None else _json(404, {"error": "not found"})


class _Handler(BaseHTTPRequestHandler):
    db_path: Path | None = None
    vault_path: Path | None = None

    def _read_json(self) -> JsonBody | None:
        if self.headers.get("Sec-Fetch-Site", "none") == "cross-site":
            return None
        if self.headers.get("Content-Type", "").split(";", 1)[0] != "application/json":
            return None
        try:
            raw_len = self.headers.get("Content-Length", "")
            if not raw_len:                              # missing / empty header
                return None
            length = int(raw_len)
            if length <= 0 or length > MAX_POST_BODY:   # W1: reject boundary violations
                return None
            raw = self.rfile.read(length).decode("utf-8")
            value = json.loads(raw) if raw else None
        except (UnicodeDecodeError, ValueError, json.JSONDecodeError):
            return None
        return value if isinstance(value, dict) else None

    def _respond(self, method: str) -> None:
        parsed = urlparse(self.path)
        query = {key: values[0] if len(values) == 1 else values
                 for key, values in parse_qs(parsed.query).items()}
        body = self._read_json() if method == "POST" else None
        status, content_type, text = route(
            method, parsed.path, query, db=self.db_path, vault=self.vault_path, body=body
        )
        payload = text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:  # noqa: N802
        self._respond("GET")

    def do_POST(self) -> None:  # noqa: N802
        self._respond("POST")

    def do_PUT(self) -> None:  # noqa: N802
        self._respond("PUT")

    def do_DELETE(self) -> None:  # noqa: N802
        self._respond("DELETE")

    def do_PATCH(self) -> None:  # noqa: N802
        self._respond("PATCH")

    def log_message(self, *_args) -> None:
        pass


def serve(
    host: str = HOST,
    port: int = PORT,
    *,
    db: Path | None = None,
    vault: Path | None = None,
) -> None:
    """啟動只綁 loopback 的儀表板。"""
    _Handler.db_path = db
    _Handler.vault_path = vault
    print(f"dashboard on http://{host}:{port}")
    HTTPServer((host, port), _Handler).serve_forever()


if __name__ == "__main__":
    serve()
