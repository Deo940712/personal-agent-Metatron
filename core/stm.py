"""DB1 (state.db) 存取層:schema DDL、idempotent 初始化、typed CRUD 與 CLI。

DDL 權威:ARCHITECTURE.md §5.1(六張表)。時間一律 UTC epoch 秒 (int)。

用法:
    python -m core.stm init                              # 建 state.db(重跑為 no-op)
    python -m core.stm schedule add "標題" --start 2026-07-15T14:00 [--end ...] [--remind ...]
    python -m core.stm schedule list [--all]
    python -m core.stm schedule done <id>
    python -m core.stm tasks add "標題" [--due ...] [--detail ...]
    python -m core.stm tasks list [--status pending]
    python -m core.stm tasks done <id>
    python -m core.stm projects set <name> [--phase ...] [--blockers a,b] [--next ...] [--repo PATH]
    python -m core.stm projects show [<name>]
所有子命令支援 --db PATH(測試用;預設 config.STATE_DB)。
時間參數接受 ISO 格式(視為本地時區)或純 epoch 整數;顯示時轉回本地時間。
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path

import config

# ── ARCHITECTURE.md §5.1 完整 DDL(六張表)──────────────────────────
# CREATE TABLE/INDEX 皆帶 IF NOT EXISTS → init 天然 idempotent。

DDL = """
-- 行程 (免疫衰減)
CREATE TABLE IF NOT EXISTS schedule (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  title        TEXT    NOT NULL,
  detail       TEXT,
  start_at     INTEGER NOT NULL,             -- UTC epoch 秒
  end_at       INTEGER,                      -- NULL = 無結束時間
  remind_at    INTEGER,                      -- NULL = 不提醒
  reminded_at  INTEGER,                      -- 已發提醒的時間,NULL = 未發 (防重複提醒)
  rrule        TEXT,                         -- NULL = 單次;重複行程存 RRULE 字串 (RFC 5545 子集)
  status       TEXT    NOT NULL DEFAULT 'active'
               CHECK (status IN ('active','done','cancelled')),
  created_at   INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_schedule_remind ON schedule(remind_at)
  WHERE status = 'active' AND reminded_at IS NULL;

-- 待辦 (Working State)
CREATE TABLE IF NOT EXISTS tasks (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  title       TEXT    NOT NULL,
  detail      TEXT,
  due_at      INTEGER,
  status      TEXT    NOT NULL DEFAULT 'pending'
              CHECK (status IN ('pending','in_progress','waiting_user','done','archived')),
  created_at  INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);

-- vibe coding 專案進度 (Working State)
CREATE TABLE IF NOT EXISTS projects (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  name         TEXT    NOT NULL UNIQUE,
  repo_path    TEXT,                         -- 本機 repo 路徑 (coding_tracker 掃描用)
  phase        TEXT,                         -- 自由文字,如 'phase-2' / 'MVP'
  blockers     TEXT,                         -- JSON array 字串
  next_action  TEXT,
  updated_at   INTEGER NOT NULL,
  created_at   INTEGER NOT NULL
);

-- skill 管線游標/去重狀態 (threads-sync store.py 模式)
CREATE TABLE IF NOT EXISTS cursors (
  pipeline    TEXT NOT NULL,
  key         TEXT NOT NULL,
  value       TEXT,
  updated_at  INTEGER NOT NULL,
  PRIMARY KEY (pipeline, key)
);

-- 每次 agent 呼叫的執行記錄 (斷點/靜默壞掉偵測)
CREATE TABLE IF NOT EXISTS agent_runs (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  started_at   INTEGER NOT NULL,
  finished_at  INTEGER,                      -- NULL = 執行中或異常終止
  trigger      TEXT NOT NULL CHECK (trigger IN ('cli','scheduler','chat')),
  status       TEXT NOT NULL DEFAULT 'running'
               CHECK (status IN ('running','ok','error','login_expired','partial')),
  summary      TEXT,
  error        TEXT
);

-- 情節記憶短期緩衝 (Episodic)
CREATE TABLE IF NOT EXISTS events (
  id                INTEGER PRIMARY KEY AUTOINCREMENT,
  ts                INTEGER NOT NULL,        -- 事件發生時間
  actor             TEXT    NOT NULL,
  action            TEXT    NOT NULL,
  target            TEXT,
  summary           TEXT    NOT NULL,
  source_ids        TEXT,                    -- JSON array: 冷儲存 entry_id (回水指標)
  health            REAL    NOT NULL DEFAULT 1.0,
  last_accessed_at  INTEGER,
  immune            INTEGER NOT NULL DEFAULT 0,
  state             TEXT    NOT NULL DEFAULT 'alive'
                    CHECK (state IN ('alive','trash','archived')),
  trashed_at        INTEGER,
  created_at        INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts);
CREATE INDEX IF NOT EXISTS idx_events_state_health ON events(state, health);

-- 待確認提案 (part-002.5:非同步確認流;bot 重啟不丟)
CREATE TABLE IF NOT EXISTS pending_proposals (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  proposal     TEXT    NOT NULL,          -- JSON 序列化的提案信封
  preview      TEXT    NOT NULL,          -- 已算好的預覽文
  status       TEXT    NOT NULL DEFAULT 'pending'
               CHECK (status IN ('pending','applying','done','cancelled','expired')),
  channel_ref  TEXT,                      -- 回覆定址 (Discord user/channel id)
  created_at   INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_pending_status ON pending_proposals(status);

-- 遠端下指令佇列 (part-006-slice-002:遠端讀開發進度 + 下一步指令)
-- 遠端 directive_push → pending → 下次 OpenCode session 開場讀取 → consume。
CREATE TABLE IF NOT EXISTS directives (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  project      TEXT    NOT NULL,          -- 專案代號 (對應 projects.name / repo)
  text         TEXT    NOT NULL,          -- 指令內容
  status       TEXT    NOT NULL DEFAULT 'pending'
               CHECK (status IN ('pending','consumed','cancelled')),
  created_at   INTEGER NOT NULL,
  consumed_at  INTEGER                    -- consume 時間 (NULL = 未消費)
);
CREATE INDEX IF NOT EXISTS idx_directives_project_status
  ON directives(project, status);
"""

TABLES = ("schedule", "tasks", "projects", "cursors", "agent_runs", "events",
          "pending_proposals", "directives")


def connect(db_path: Path | None = None) -> sqlite3.Connection:
    """開啟 DB1 連線(WAL、外鍵開啟)。呼叫者負責 close。"""
    path = db_path or config.STATE_DB
    con = sqlite3.connect(path)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA foreign_keys=ON")
    return con


def init(db_path: Path | None = None) -> Path:
    """建立 state.db 與六張表。idempotent:重跑不報錯、不重建。"""
    path = db_path or config.STATE_DB
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    try:
        con.executescript(DDL)
        con.commit()
    finally:
        con.close()
    return path


def existing_tables(db_path: Path | None = None) -> list[str]:
    con = connect(db_path)
    try:
        rows = con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
        return [r[0] for r in rows]
    finally:
        con.close()


# ── 時間輔助 ─────────────────────────────────────────────────────────

def now() -> int:
    return int(time.time())


def parse_when(text: str) -> int:
    """ISO 字串(本地時區)或 epoch 整數 → UTC epoch 秒。壞格式 → ValueError(帶提示)。"""
    if text.isdigit():
        return int(text)
    try:
        return int(datetime.fromisoformat(text).timestamp())
    except ValueError:
        raise ValueError(
            f"無法解析時間 {text!r}:請用 ISO 格式(如 2026-07-15T14:00)或 epoch 秒") from None


def fmt_when(epoch: int | None) -> str:
    if epoch is None:
        return "-"
    try:
        return datetime.fromtimestamp(epoch).strftime("%Y-%m-%d %H:%M")
    except (OverflowError, OSError, ValueError):
        # B3 防禦層:一筆界外值不可癱瘓整個 list 顯示
        return f"?invalid({epoch})"


def _row_dicts(cur: sqlite3.Cursor) -> list[dict]:
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


# ── schedule CRUD ────────────────────────────────────────────────────

def schedule_add(db: Path | None, title: str, start_at: int, *,
                 end_at: int | None = None, remind_at: int | None = None,
                 rrule: str | None = None, detail: str | None = None) -> int:
    con = connect(db)
    try:
        cur = con.execute(
            "INSERT INTO schedule (title, detail, start_at, end_at, remind_at, rrule, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (title, detail, start_at, end_at, remind_at, rrule, now()))
        con.commit()
        return cur.lastrowid
    finally:
        con.close()


def schedule_list(db: Path | None, *, include_done: bool = False) -> list[dict]:
    con = connect(db)
    try:
        sql = "SELECT * FROM schedule"
        if not include_done:
            sql += " WHERE status = 'active'"
        return _row_dicts(con.execute(sql + " ORDER BY start_at"))
    finally:
        con.close()


def schedule_set_status(db: Path | None, item_id: int, status: str) -> bool:
    """status: done / cancelled。回傳是否有列被更新。"""
    con = connect(db)
    try:
        cur = con.execute("UPDATE schedule SET status = ? WHERE id = ?", (status, item_id))
        con.commit()
        return cur.rowcount > 0
    finally:
        con.close()


# ── tasks CRUD ───────────────────────────────────────────────────────

def task_add(db: Path | None, title: str, *,
             due_at: int | None = None, detail: str | None = None) -> int:
    con = connect(db)
    try:
        cur = con.execute(
            "INSERT INTO tasks (title, detail, due_at, created_at) VALUES (?, ?, ?, ?)",
            (title, detail, due_at, now()))
        con.commit()
        return cur.lastrowid
    finally:
        con.close()


def task_list(db: Path | None, *, status: str | None = None) -> list[dict]:
    """status=None → 未完結(pending/in_progress/waiting_user)。"""
    con = connect(db)
    try:
        if status:
            cur = con.execute(
                "SELECT * FROM tasks WHERE status = ? ORDER BY due_at IS NULL, due_at", (status,))
        else:
            cur = con.execute(
                "SELECT * FROM tasks WHERE status IN ('pending','in_progress','waiting_user') "
                "ORDER BY due_at IS NULL, due_at")
        return _row_dicts(cur)
    finally:
        con.close()


def task_set_status(db: Path | None, task_id: int, status: str) -> bool:
    con = connect(db)
    try:
        cur = con.execute("UPDATE tasks SET status = ? WHERE id = ?", (status, task_id))
        con.commit()
        return cur.rowcount > 0
    finally:
        con.close()


# ── projects CRUD(upsert by name)───────────────────────────────────

def project_set(db: Path | None, name: str, *,
                phase: str | None = None, blockers: list[str] | None = None,
                next_action: str | None = None, repo_path: str | None = None) -> int:
    """upsert:不存在則建立;存在則只更新有給的欄位。回傳 project id。"""
    con = connect(db)
    try:
        ts = now()
        row = con.execute("SELECT id FROM projects WHERE name = ?", (name,)).fetchone()
        blockers_json = json.dumps(blockers, ensure_ascii=False) if blockers is not None else None
        if row is None:
            cur = con.execute(
                "INSERT INTO projects (name, repo_path, phase, blockers, next_action, updated_at, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (name, repo_path, phase, blockers_json, next_action, ts, ts))
            con.commit()
            return cur.lastrowid
        sets, vals = ["updated_at = ?"], [ts]
        for col, val in (("phase", phase), ("blockers", blockers_json),
                         ("next_action", next_action), ("repo_path", repo_path)):
            if val is not None:
                sets.append(f"{col} = ?")
                vals.append(val)
        vals.append(row[0])
        con.execute(f"UPDATE projects SET {', '.join(sets)} WHERE id = ?", vals)
        con.commit()
        return row[0]
    finally:
        con.close()


def project_show(db: Path | None, name: str | None = None) -> list[dict]:
    con = connect(db)
    try:
        if name:
            cur = con.execute("SELECT * FROM projects WHERE name = ?", (name,))
        else:
            cur = con.execute("SELECT * FROM projects ORDER BY updated_at DESC")
        rows = _row_dicts(cur)
        for r in rows:
            r["blockers"] = json.loads(r["blockers"]) if r["blockers"] else []
        return rows
    finally:
        con.close()


# ── cursors get/set ──────────────────────────────────────────────────

def cursor_get(db: Path | None, pipeline: str, key: str) -> str | None:
    con = connect(db)
    try:
        row = con.execute(
            "SELECT value FROM cursors WHERE pipeline = ? AND key = ?", (pipeline, key)).fetchone()
        return row[0] if row else None
    finally:
        con.close()


def cursor_set(db: Path | None, pipeline: str, key: str, value: str) -> None:
    con = connect(db)
    try:
        con.execute(
            "INSERT INTO cursors (pipeline, key, value, updated_at) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(pipeline, key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at",
            (pipeline, key, value, now()))
        con.commit()
    finally:
        con.close()


# ── events append / 查詢 ─────────────────────────────────────────────

def event_append(db: Path | None, actor: str, action: str, summary: str, *,
                 target: str | None = None, source_ids: list[str] | None = None,
                 immune: bool = False) -> int:
    con = connect(db)
    try:
        cur = con.execute(
            "INSERT INTO events (ts, actor, action, target, summary, source_ids, immune, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (now(), actor, action, target, summary,
             json.dumps(source_ids, ensure_ascii=False) if source_ids else None,
             1 if immune else 0, now()))
        con.commit()
        return cur.lastrowid
    finally:
        con.close()


def event_query(db: Path | None, *, target: str | None = None,
                actor: str | None = None, limit: int = 50) -> list[dict]:
    """只查 alive(蒸餾封存後不再主動載入——§4.1 遺忘語意)。"""
    con = connect(db)
    try:
        sql = "SELECT * FROM events WHERE state = 'alive'"
        vals: list = []
        if target:
            sql += " AND target = ?"
            vals.append(target)
        if actor:
            sql += " AND actor = ?"
            vals.append(actor)
        sql += " ORDER BY ts DESC LIMIT ?"
        vals.append(limit)
        return _row_dicts(con.execute(sql, vals))
    finally:
        con.close()


# ── pending_proposals CRUD(part-002.5:非同步確認)──────────────────

def pending_add(db: Path | None, proposal: dict, preview: str,
                channel_ref: str | None = None) -> int:
    con = connect(db)
    try:
        cur = con.execute(
            "INSERT INTO pending_proposals (proposal, preview, channel_ref, created_at) "
            "VALUES (?, ?, ?, ?)",
            (json.dumps(proposal, ensure_ascii=False), preview, channel_ref, now()))
        con.commit()
        return cur.lastrowid
    finally:
        con.close()


def pending_get(db: Path | None, pending_id: int) -> dict | None:
    """回 {id, proposal(dict), preview, status, channel_ref, created_at} 或 None。"""
    con = connect(db)
    try:
        cur = con.execute("SELECT * FROM pending_proposals WHERE id = ?", (pending_id,))
        row = cur.fetchone()
        if not row:
            return None
        d = dict(zip([c[0] for c in cur.description], row))
        d["proposal"] = json.loads(d["proposal"])
        return d
    finally:
        con.close()


def pending_set_status(db: Path | None, pending_id: int, status: str) -> bool:
    """只允許從 pending 轉出(done/cancelled/expired);非 pending → 不動回 False。"""
    con = connect(db)
    try:
        cur = con.execute(
            "UPDATE pending_proposals SET status = ? WHERE id = ? AND status = 'pending'",
            (status, pending_id))
        con.commit()
        return cur.rowcount > 0
    finally:
        con.close()


def pending_claim(db: Path | None, pending_id: int) -> bool:
    """原子認領:pending → applying。回傳是否由本呼叫者認領成功。

    part-006-slice-001 裂縫2:取代「讀 → 檢查 status → apply」的競態。單一原子
    UPDATE 保證雙擊/跨介面同時確認時,只有一個呼叫者拿到 rowcount==1 得以落地;
    其餘拿 False 不執行。applying 是 confirm 落地過程中的暫態。
    """
    con = connect(db)
    try:
        cur = con.execute(
            "UPDATE pending_proposals SET status = 'applying' "
            "WHERE id = ? AND status = 'pending'",
            (pending_id,))
        con.commit()
        return cur.rowcount == 1
    finally:
        con.close()


def pending_finish(db: Path | None, pending_id: int, status: str) -> bool:
    """認領後的終態轉移:applying → done/cancelled。回傳是否有列被更新。

    part-006-slice-001 裂縫2:claim 已把 pending 轉 applying;收尾只能從 applying
    轉出,確保未經 claim 不能直接標記,雙擊的第二次(claim 失敗)也不會誤收尾。
    """
    if status not in ("done", "cancelled"):
        raise ValueError(f"pending_finish status must be done/cancelled: {status!r}")
    con = connect(db)
    try:
        cur = con.execute(
            "UPDATE pending_proposals SET status = ? WHERE id = ? AND status = 'applying'",
            (status, pending_id))
        con.commit()
        return cur.rowcount == 1
    finally:
        con.close()


def pending_expire_due(db: Path | None, ttl_seconds: int,
                       now_ts: int | None = None) -> list[int]:
    """把超過 TTL 的 pending 標 expired。回傳被清的 id。"""
    ts = now_ts or now()
    cutoff = ts - ttl_seconds
    con = connect(db)
    try:
        ids = [r[0] for r in con.execute(
            "SELECT id FROM pending_proposals WHERE status = 'pending' AND created_at <= ?",
            (cutoff,)).fetchall()]
        if ids:
            marks = ",".join("?" * len(ids))
            con.execute(
                f"UPDATE pending_proposals SET status = 'expired' WHERE id IN ({marks})", ids)
            con.commit()
        return ids
    finally:
        con.close()


# ── directives CRUD(part-006-slice-002:遠端下指令佇列)──────────────

def directive_add(db: Path | None, project: str, text: str) -> int:
    """新增一則 pending 指令。project/text 空 → ValueError(fail-closed)。"""
    if not isinstance(project, str) or not project.strip():
        raise ValueError("directive project must be a non-empty string")
    if not isinstance(text, str) or not text.strip():
        raise ValueError("directive text must be a non-empty string")
    con = connect(db)
    try:
        cur = con.execute(
            "INSERT INTO directives (project, text, created_at) VALUES (?, ?, ?)",
            (project.strip(), text.strip(), now()))
        con.commit()
        return cur.lastrowid
    finally:
        con.close()


def directive_list(db: Path | None, *, project: str | None = None,
                   status: str | None = None) -> list[dict]:
    """列指令。project/status 為 None = 不過濾。按 created_at 排序。"""
    con = connect(db)
    try:
        sql = "SELECT * FROM directives"
        clauses, vals = [], []
        if project is not None:
            clauses.append("project = ?")
            vals.append(project)
        if status is not None:
            clauses.append("status = ?")
            vals.append(status)
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY created_at, id"
        return _row_dicts(con.execute(sql, vals))
    finally:
        con.close()


def directive_consume(db: Path | None, directive_id: int) -> bool:
    """pending → consumed(記 consumed_at)。只從 pending 轉出;非 pending → False。"""
    con = connect(db)
    try:
        cur = con.execute(
            "UPDATE directives SET status = 'consumed', consumed_at = ? "
            "WHERE id = ? AND status = 'pending'",
            (now(), directive_id))
        con.commit()
        return cur.rowcount == 1
    finally:
        con.close()


def directive_cancel(db: Path | None, directive_id: int) -> bool:
    """pending → cancelled。只從 pending 轉出;非 pending → False。"""
    con = connect(db)
    try:
        cur = con.execute(
            "UPDATE directives SET status = 'cancelled' "
            "WHERE id = ? AND status = 'pending'",
            (directive_id,))
        con.commit()
        return cur.rowcount == 1
    finally:
        con.close()


# ── CLI ──────────────────────────────────────────────────────────────

def _print_rows(rows: list[dict], cols: list[tuple[str, str]]) -> None:
    """cols: [(欄位名, 顯示標題)];時間欄位自動格式化。"""
    if not rows:
        print("(empty)")
        return
    for r in rows:
        parts = []
        for col, label in cols:
            v = r.get(col)
            if col.endswith("_at") and isinstance(v, int):
                v = fmt_when(v)
            parts.append(f"{label}={v if v not in (None, '') else '-'}")
        print("  ".join(parts))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m core.stm", description="DB1 存取層 CLI")
    parser.add_argument("--db", type=Path, default=None, help="db 路徑(預設 config.STATE_DB)")
    sub = parser.add_subparsers(dest="domain", required=True)

    sub.add_parser("init", help="建立 state.db(idempotent)")

    p_sch = sub.add_parser("schedule", help="行程").add_subparsers(dest="verb", required=True)
    a = p_sch.add_parser("add")
    a.add_argument("title")
    a.add_argument("--start", required=True, help="ISO 或 epoch")
    a.add_argument("--end", default=None)
    a.add_argument("--remind", default=None)
    a.add_argument("--rrule", default=None)
    a.add_argument("--detail", default=None)
    ls = p_sch.add_parser("list")
    ls.add_argument("--all", action="store_true", help="含 done/cancelled")
    d = p_sch.add_parser("done")
    d.add_argument("id", type=int)

    p_t = sub.add_parser("tasks", help="待辦").add_subparsers(dest="verb", required=True)
    a = p_t.add_parser("add")
    a.add_argument("title")
    a.add_argument("--due", default=None)
    a.add_argument("--detail", default=None)
    ls = p_t.add_parser("list")
    ls.add_argument("--status", default=None,
                    choices=["pending", "in_progress", "waiting_user", "done", "archived"])
    d = p_t.add_parser("done")
    d.add_argument("id", type=int)

    p_p = sub.add_parser("projects", help="專案進度").add_subparsers(dest="verb", required=True)
    s = p_p.add_parser("set")
    s.add_argument("name")
    s.add_argument("--phase", default=None)
    s.add_argument("--blockers", default=None, help="逗號分隔")
    s.add_argument("--next", dest="next_action", default=None)
    s.add_argument("--repo", dest="repo_path", default=None)
    sh = p_p.add_parser("show")
    sh.add_argument("name", nargs="?", default=None)

    p_d = sub.add_parser("directives", help="遠端下指令佇列").add_subparsers(
        dest="verb", required=True)
    da = p_d.add_parser("add")
    da.add_argument("project")
    da.add_argument("text")
    dl = p_d.add_parser("list")
    dl.add_argument("--project", default=None)
    dl.add_argument("--status", default=None,
                    choices=["pending", "consumed", "cancelled"])
    dp = p_d.add_parser("pending", help="列出某專案的 pending 指令(session 開場用)")
    dp.add_argument("--project", default=None)
    dc = p_d.add_parser("consume")
    dc.add_argument("id", type=int)
    dx = p_d.add_parser("cancel")
    dx.add_argument("id", type=int)

    args = parser.parse_args(argv)
    db = args.db

    if args.domain == "init":
        path = init(db)
        print(f"OK: {path} tables={existing_tables(db)}")
        return 0

    # B5:CLI 時間參數壞格式 → 友善訊息 + exit 2(不裸 traceback)
    try:
        return _dispatch(args, db)
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2


def _dispatch(args, db: Path | None) -> int:
    if args.domain == "schedule":
        if args.verb == "add":
            rowid = schedule_add(
                db, args.title, parse_when(args.start),
                end_at=parse_when(args.end) if args.end else None,
                remind_at=parse_when(args.remind) if args.remind else None,
                rrule=args.rrule, detail=args.detail)
            print(f"OK: schedule #{rowid}")
        elif args.verb == "list":
            _print_rows(schedule_list(db, include_done=args.all),
                        [("id", "#"), ("start_at", "start"), ("title", "title"),
                         ("remind_at", "remind"), ("status", "status")])
        elif args.verb == "done":
            ok = schedule_set_status(db, args.id, "done")
            print(f"OK: schedule #{args.id} done" if ok else f"NOT FOUND: #{args.id}")
            return 0 if ok else 1
        return 0

    if args.domain == "tasks":
        if args.verb == "add":
            rowid = task_add(db, args.title,
                             due_at=parse_when(args.due) if args.due else None,
                             detail=args.detail)
            print(f"OK: task #{rowid}")
        elif args.verb == "list":
            _print_rows(task_list(db, status=args.status),
                        [("id", "#"), ("title", "title"), ("due_at", "due"), ("status", "status")])
        elif args.verb == "done":
            ok = task_set_status(db, args.id, "done")
            print(f"OK: task #{args.id} done" if ok else f"NOT FOUND: #{args.id}")
            return 0 if ok else 1
        return 0

    if args.domain == "projects":
        if args.verb == "set":
            blockers = args.blockers.split(",") if args.blockers else None
            pid = project_set(db, args.name, phase=args.phase, blockers=blockers,
                              next_action=args.next_action, repo_path=args.repo_path)
            print(f"OK: project #{pid} {args.name}")
        elif args.verb == "show":
            _print_rows(project_show(db, args.name),
                        [("name", "name"), ("phase", "phase"), ("blockers", "blockers"),
                         ("next_action", "next"), ("updated_at", "updated")])
        return 0

    if args.domain == "directives":
        if args.verb == "add":
            did = directive_add(db, args.project, args.text)
            print(f"OK: directive #{did}")
        elif args.verb in ("list", "pending"):
            status = "pending" if args.verb == "pending" else args.status
            _print_rows(directive_list(db, project=args.project, status=status),
                        [("id", "#"), ("project", "project"), ("text", "text"),
                         ("status", "status"), ("created_at", "created")])
        elif args.verb == "consume":
            ok = directive_consume(db, args.id)
            print(f"OK: directive #{args.id} consumed" if ok
                  else f"NOT PENDING: #{args.id}")
            return 0 if ok else 1
        elif args.verb == "cancel":
            ok = directive_cancel(db, args.id)
            print(f"OK: directive #{args.id} cancelled" if ok
                  else f"NOT PENDING: #{args.id}")
            return 0 if ok else 1
        return 0

    return 2


if __name__ == "__main__":
    sys.exit(main())
