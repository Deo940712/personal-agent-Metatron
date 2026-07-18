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

-- 個人模型 facets (part-007:證據驅動 stability;免疫衰減同 events immune 類)
-- 生命週期:provisional → stable → superseded/forgotten;pinned/forgotten 是
-- user_state 硬覆蓋(使用者永遠贏)。forgotten = 停用不刪;證據仍可回水。
CREATE TABLE IF NOT EXISTS profile_facets (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  facet_class    TEXT    NOT NULL
                 CHECK (facet_class IN ('preference','identity','routine',
                                        'workflow','veto','goal','tooling','style')),
  facet_key      TEXT    NOT NULL,   -- 類內唯一鍵,如 'work_hours' / 'reply_lang'
  value          TEXT    NOT NULL,   -- 目前值(文字;結構化走 JSON)
  confidence     REAL    NOT NULL DEFAULT 0.0,
  stability      REAL    NOT NULL DEFAULT 0.0,
  evidence_count INTEGER NOT NULL DEFAULT 0,
  evidence_ids   TEXT,               -- JSON array:冷儲存 entry_id(溯源,可回水)
  state          TEXT    NOT NULL DEFAULT 'provisional'
                 CHECK (state IN ('provisional','stable','superseded','forgotten')),
  user_state     TEXT    NOT NULL DEFAULT 'auto'
                 CHECK (user_state IN ('auto','pinned','forgotten')),
  superseded_by  INTEGER,            -- 指向新 facet(矛盾修正,不刪舊)
  first_seen_at  INTEGER NOT NULL,
  last_seen_at   INTEGER NOT NULL,
  created_at     INTEGER NOT NULL
);
-- 同 class+key 只一個 active(partial unique:superseded/forgotten 歷史可多筆)
CREATE UNIQUE INDEX IF NOT EXISTS idx_facets_unique_active
  ON profile_facets(facet_class, facet_key)
  WHERE state IN ('provisional','stable');
CREATE INDEX IF NOT EXISTS idx_facets_active ON profile_facets(facet_class, state)
  WHERE state IN ('provisional','stable');

-- 主動建議 (part-009:world-diff 反思產出的可過期建議;只建議不行動)
-- state:pending(剛產)→ pushed(已推 Discord)→ accepted/ignored(使用者回饋)
--   / expired(過期作廢)。dedup_key:同觀察短期不重推。
CREATE TABLE IF NOT EXISTS advices (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  priority      TEXT    NOT NULL DEFAULT 'low'
                CHECK (priority IN ('low','medium','high')),
  observation   TEXT    NOT NULL,          -- 觀察到什麼(world-diff 事實)
  suggestion    TEXT    NOT NULL,          -- 建議做什麼
  evidence_ids  TEXT,                      -- JSON array:冷儲存 entry_id(溯源)
  actions       TEXT,                      -- JSON array:可選一鍵動作(標準 proposal)
  state         TEXT    NOT NULL DEFAULT 'pending'
                CHECK (state IN ('pending','pushed','accepted','ignored','expired')),
  dedup_key     TEXT,                      -- 去重鍵(同觀察短期不重推)
  expires_at    INTEGER NOT NULL,          -- 過期即作廢(不堆積)
  created_at    INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_advices_state ON advices(state, priority);
CREATE INDEX IF NOT EXISTS idx_advices_dedup ON advices(dedup_key, created_at);

-- 知識偵察 watchlist (part-008:訂閱主題,低頻自動研究;可動態增減)
CREATE TABLE IF NOT EXISTS watchlist (
  id               INTEGER PRIMARY KEY AUTOINCREMENT,
  topic            TEXT    NOT NULL,          -- 追蹤主題(如 'RAG 最新做法')
  source_url       TEXT    NOT NULL,          -- 來源 URL(必在 allowlist 內)
  interval_days    INTEGER NOT NULL DEFAULT 7,-- 複查間隔(低頻)
  last_checked_at  INTEGER,                   -- 最後研究時間(NULL = 未查過)
  state            TEXT    NOT NULL DEFAULT 'active'
                   CHECK (state IN ('active','paused')),
  created_at       INTEGER NOT NULL,
  UNIQUE (topic, source_url)
);
CREATE INDEX IF NOT EXISTS idx_watchlist_active
  ON watchlist(state, last_checked_at);
"""

TABLES = ("schedule", "tasks", "projects", "cursors", "agent_runs", "events",
          "pending_proposals", "directives", "profile_facets", "advices",
          "watchlist")


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


# ── profile_facets CRUD(part-007-slice-000:資料層)────────────────────
# 寫入紀律:slice-000 只提供資料層原語;正式建立/升級/supersede 提案路徑在
# slice-001 經 writer 欄位級驗證。pinned/forgotten 硬覆蓋在此層即擋(雙層防線)。

FACET_CLASSES = ("preference", "identity", "routine", "workflow",
                 "veto", "goal", "tooling", "style")
_FACET_ACTIVE_STATES = ("provisional", "stable")


def facet_get(db: Path | None, facet_id: int) -> dict | None:
    con = connect(db)
    try:
        rows = _row_dicts(con.execute(
            "SELECT * FROM profile_facets WHERE id = ?", (facet_id,)))
        return rows[0] if rows else None
    finally:
        con.close()


def facet_get_active(db: Path | None, facet_class: str, facet_key: str) -> dict | None:
    """取同 class+key 的 active(provisional/stable)列;至多一筆(partial unique)。"""
    con = connect(db)
    try:
        rows = _row_dicts(con.execute(
            "SELECT * FROM profile_facets WHERE facet_class = ? AND facet_key = ? "
            "AND state IN ('provisional','stable')",
            (facet_class, facet_key)))
        return rows[0] if rows else None
    finally:
        con.close()


def facet_list(db: Path | None, *, facet_class: str | None = None,
               include_inactive: bool = False) -> list[dict]:
    """列 facets。預設只列 active(provisional/stable);include_inactive 含歷史。"""
    con = connect(db)
    try:
        sql = "SELECT * FROM profile_facets"
        clauses, vals = [], []
        if not include_inactive:
            clauses.append("state IN ('provisional','stable')")
        if facet_class is not None:
            clauses.append("facet_class = ?")
            vals.append(facet_class)
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY facet_class, facet_key, id"
        return _row_dicts(con.execute(sql, vals))
    finally:
        con.close()


def facet_insert(db: Path | None, facet_class: str, facet_key: str, value: str, *,
                 confidence: float = 0.0, evidence_ids: list[str] | None = None,
                 seen_at: int | None = None) -> int:
    """建立 provisional facet(單次證據起點)。同 key 已有 active → IntegrityError。

    fail-closed 驗證:class 合法、key/value 非空、confidence 界內。
    """
    if facet_class not in FACET_CLASSES:
        raise ValueError(f"invalid facet_class: {facet_class!r}")
    if not isinstance(facet_key, str) or not facet_key.strip():
        raise ValueError("facet_key must be a non-empty string")
    if not isinstance(value, str) or not value.strip():
        raise ValueError("facet value must be a non-empty string")
    if not 0.0 <= confidence <= 1.0:
        raise ValueError(f"confidence out of range: {confidence}")
    ts = seen_at if seen_at is not None else now()
    con = connect(db)
    try:
        cur = con.execute(
            "INSERT INTO profile_facets (facet_class, facet_key, value, confidence, "
            "evidence_count, evidence_ids, first_seen_at, last_seen_at, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (facet_class, facet_key.strip(), value.strip(), confidence,
             1 if evidence_ids else 0,
             json.dumps(evidence_ids) if evidence_ids else None,
             ts, ts, now()))
        con.commit()
        return cur.lastrowid
    finally:
        con.close()


def facet_touch_evidence(db: Path | None, facet_id: int,
                         evidence_ids: list[str], *,
                         seen_at: int | None = None,
                         confidence: float | None = None) -> bool:
    """累積證據:append evidence_ids、evidence_count+1、更新 last_seen_at。

    只作用於 active 列;superseded/forgotten 或 user_state='forgotten' → False
    (forgotten ⇒ 阻止再升級的資料層防線)。不改 state——升級決策屬 detector
    (core/facets.py)+ writer(slice-001)。
    """
    if not evidence_ids:
        raise ValueError("evidence_ids must be non-empty")
    con = connect(db)
    try:
        rows = _row_dicts(con.execute(
            "SELECT * FROM profile_facets WHERE id = ?", (facet_id,)))
        if not rows:
            return False
        row = rows[0]
        if row["state"] not in _FACET_ACTIVE_STATES or row["user_state"] == "forgotten":
            return False
        merged = json.loads(row["evidence_ids"]) if row["evidence_ids"] else []
        merged.extend(e for e in evidence_ids if e not in merged)
        sets = ["evidence_count = evidence_count + 1", "evidence_ids = ?",
                "last_seen_at = ?"]
        vals: list = [json.dumps(merged), seen_at if seen_at is not None else now()]
        if confidence is not None:
            if not 0.0 <= confidence <= 1.0:
                raise ValueError(f"confidence out of range: {confidence}")
            sets.append("confidence = ?")
            vals.append(confidence)
        vals.append(facet_id)
        cur = con.execute(
            f"UPDATE profile_facets SET {', '.join(sets)} WHERE id = ?", vals)
        con.commit()
        return cur.rowcount == 1
    finally:
        con.close()


def facet_promote(db: Path | None, facet_id: int, stability: float) -> bool:
    """provisional → stable(detector 判定通過後呼叫)。

    只從 provisional 轉出;pinned 免動(已是使用者裁決,評分無效化)、
    forgotten 擋死。stability 界內檢查。
    """
    if not 0.0 <= stability <= 1.0:
        raise ValueError(f"stability out of range: {stability}")
    con = connect(db)
    try:
        cur = con.execute(
            "UPDATE profile_facets SET state = 'stable', stability = ? "
            "WHERE id = ? AND state = 'provisional' AND user_state = 'auto'",
            (stability, facet_id))
        con.commit()
        return cur.rowcount == 1
    finally:
        con.close()


def facet_set_user_state(db: Path | None, facet_id: int, user_state: str) -> bool:
    """使用者硬覆蓋:pin / forget / 回 auto。

    pin ⇒ user_state='pinned' 且 provisional 直升 stable(使用者確認即穩定)。
    forget ⇒ user_state='forgotten' 且 state='forgotten'(停用,不再載入;不刪)。
    auto ⇒ 解除覆蓋(state 不回滾——forgotten 的 facet 需重新走建立路徑)。
    """
    if user_state not in ("auto", "pinned", "forgotten"):
        raise ValueError(f"invalid user_state: {user_state!r}")
    con = connect(db)
    try:
        if user_state == "pinned":
            cur = con.execute(
                "UPDATE profile_facets SET user_state = 'pinned', state = 'stable', "
                "stability = 1.0 WHERE id = ? AND state IN ('provisional','stable')",
                (facet_id,))
        elif user_state == "forgotten":
            cur = con.execute(
                "UPDATE profile_facets SET user_state = 'forgotten', "
                "state = 'forgotten' WHERE id = ? AND state != 'forgotten'",
                (facet_id,))
        else:
            cur = con.execute(
                "UPDATE profile_facets SET user_state = 'auto' WHERE id = ?",
                (facet_id,))
        con.commit()
        return cur.rowcount == 1
    finally:
        con.close()


def facet_supersede_mark(db: Path | None, old_id: int) -> bool:
    """supersede 第一步:舊 facet → superseded(尚未指向新 facet)。

    釋放 unique active 槽,讓同 class+key 的新值可插入;第二步用
    facet_link_supersede 補 superseded_by。防線同 facet_supersede:
    只從 active 轉出、pinned 擋死。
    """
    con = connect(db)
    try:
        cur = con.execute(
            "UPDATE profile_facets SET state = 'superseded' "
            "WHERE id = ? AND state IN ('provisional','stable') "
            "AND user_state != 'pinned'",
            (old_id,))
        con.commit()
        return cur.rowcount == 1
    finally:
        con.close()


def facet_link_supersede(db: Path | None, old_id: int, new_id: int) -> bool:
    """supersede 第二步:補上 superseded_by 指標(舊 → 新)。"""
    if old_id == new_id:
        raise ValueError("facet cannot supersede itself")
    con = connect(db)
    try:
        cur = con.execute(
            "UPDATE profile_facets SET superseded_by = ? "
            "WHERE id = ? AND state = 'superseded'",
            (new_id, old_id))
        con.commit()
        return cur.rowcount == 1
    finally:
        con.close()


def facet_supersede(db: Path | None, old_id: int, new_id: int) -> bool:
    """舊 facet → superseded 並指向新 facet。不刪舊(Mneme 雙側保留)。

    防線:old 必須 active、不得 pinned(pinned 由使用者手動解除才可換)、
    new 必須存在且 active、不得自我取代。
    """
    if old_id == new_id:
        raise ValueError("facet cannot supersede itself")
    con = connect(db)
    try:
        new_rows = _row_dicts(con.execute(
            "SELECT id, state FROM profile_facets WHERE id = ?", (new_id,)))
        if not new_rows or new_rows[0]["state"] not in _FACET_ACTIVE_STATES:
            return False
        cur = con.execute(
            "UPDATE profile_facets SET state = 'superseded', superseded_by = ? "
            "WHERE id = ? AND state IN ('provisional','stable') "
            "AND user_state != 'pinned'",
            (new_id, old_id))
        con.commit()
        return cur.rowcount == 1
    finally:
        con.close()


# ── advices CRUD(part-009-slice-000:主動建議)──────────────────────────

ADVICE_PRIORITIES = ("low", "medium", "high")
_ADVICE_STATES = ("pending", "pushed", "accepted", "ignored", "expired")


def advice_add(db: Path | None, *, priority: str, observation: str,
               suggestion: str, expires_at: int,
               evidence_ids: list[str] | None = None,
               actions: list[dict] | None = None,
               dedup_key: str | None = None,
               created_at: int | None = None) -> int:
    """新增一則 pending advice。fail-closed:priority/文字/expires_at 驗證。

    created_at 可由呼叫端傳入(advisor tick 用邏輯時間,確保配額/去重視窗一致)。
    """
    if priority not in ADVICE_PRIORITIES:
        raise ValueError(f"invalid priority: {priority!r}")
    if not isinstance(observation, str) or not observation.strip():
        raise ValueError("observation must be a non-empty string")
    if not isinstance(suggestion, str) or not suggestion.strip():
        raise ValueError("suggestion must be a non-empty string")
    if not isinstance(expires_at, int) or isinstance(expires_at, bool):
        raise ValueError("expires_at must be an int epoch")
    con = connect(db)
    try:
        cur = con.execute(
            "INSERT INTO advices (priority, observation, suggestion, evidence_ids, "
            "actions, dedup_key, expires_at, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (priority, observation.strip(), suggestion.strip(),
             json.dumps(evidence_ids) if evidence_ids else None,
             json.dumps(actions, ensure_ascii=False) if actions else None,
             dedup_key, expires_at, created_at if created_at is not None else now()))
        con.commit()
        return cur.lastrowid
    finally:
        con.close()


def advice_get(db: Path | None, advice_id: int) -> dict | None:
    con = connect(db)
    try:
        rows = _row_dicts(con.execute(
            "SELECT * FROM advices WHERE id = ?", (advice_id,)))
        return rows[0] if rows else None
    finally:
        con.close()


def advice_list(db: Path | None, *, state: str | None = None,
                priority: str | None = None,
                now_ts: int | None = None) -> list[dict]:
    """列 advice。state/priority 過濾;預設排除已過期(now > expires_at)。"""
    con = connect(db)
    try:
        sql = "SELECT * FROM advices"
        clauses, vals = [], []
        if state is not None:
            clauses.append("state = ?")
            vals.append(state)
        if priority is not None:
            clauses.append("priority = ?")
            vals.append(priority)
        if now_ts is not None:
            clauses.append("expires_at > ?")
            vals.append(now_ts)
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY created_at DESC, id DESC"
        return _row_dicts(con.execute(sql, vals))
    finally:
        con.close()


def advice_set_state(db: Path | None, advice_id: int, state: str) -> bool:
    """轉 advice 狀態(pending→pushed→accepted/ignored)。非法 state → ValueError。"""
    if state not in _ADVICE_STATES:
        raise ValueError(f"invalid advice state: {state!r}")
    con = connect(db)
    try:
        cur = con.execute("UPDATE advices SET state = ? WHERE id = ?",
                          (state, advice_id))
        con.commit()
        return cur.rowcount == 1
    finally:
        con.close()


def advice_dedup_recent(db: Path | None, dedup_key: str, since_ts: int) -> bool:
    """since_ts 之後是否已有同 dedup_key 的 advice(去重判定)。"""
    if not dedup_key:
        return False
    con = connect(db)
    try:
        row = con.execute(
            "SELECT 1 FROM advices WHERE dedup_key = ? AND created_at >= ? LIMIT 1",
            (dedup_key, since_ts)).fetchone()
        return row is not None
    finally:
        con.close()


def advice_count_since(db: Path | None, since_ts: int) -> int:
    """since_ts 之後產生的 advice 數(每日配額判定)。"""
    con = connect(db)
    try:
        return con.execute(
            "SELECT COUNT(*) FROM advices WHERE created_at >= ?",
            (since_ts,)).fetchone()[0]
    finally:
        con.close()


def advice_expire_due(db: Path | None, now_ts: int) -> int:
    """把 expires_at 已過且仍 pending/pushed 的 advice 標 expired。回傳筆數。"""
    con = connect(db)
    try:
        cur = con.execute(
            "UPDATE advices SET state = 'expired' "
            "WHERE expires_at <= ? AND state IN ('pending','pushed')",
            (now_ts,))
        con.commit()
        return cur.rowcount
    finally:
        con.close()


# ── watchlist CRUD(part-008-slice-000:知識偵察訂閱)─────────────────────

def watchlist_add(db: Path | None, topic: str, source_url: str, *,
                  interval_days: int = 7) -> int:
    """新增 watchlist 主題。topic/source_url 空 → ValueError(fail-closed)。

    allowlist 檢查在 scout 層(呼叫端);此處只做結構驗證。
    """
    if not isinstance(topic, str) or not topic.strip():
        raise ValueError("topic must be a non-empty string")
    if not isinstance(source_url, str) or not source_url.strip():
        raise ValueError("source_url must be a non-empty string")
    if not isinstance(interval_days, int) or isinstance(interval_days, bool) \
            or interval_days < 1:
        raise ValueError("interval_days must be a positive int")
    con = connect(db)
    try:
        cur = con.execute(
            "INSERT INTO watchlist (topic, source_url, interval_days, created_at) "
            "VALUES (?, ?, ?, ?)",
            (topic.strip(), source_url.strip(), interval_days, now()))
        con.commit()
        return cur.lastrowid
    finally:
        con.close()


def watchlist_list(db: Path | None, *, state: str | None = None) -> list[dict]:
    con = connect(db)
    try:
        sql = "SELECT * FROM watchlist"
        vals: list = []
        if state is not None:
            sql += " WHERE state = ?"
            vals.append(state)
        sql += " ORDER BY id"
        return _row_dicts(con.execute(sql, vals))
    finally:
        con.close()


def watchlist_set_state(db: Path | None, watch_id: int, state: str) -> bool:
    if state not in ("active", "paused"):
        raise ValueError(f"invalid watchlist state: {state!r}")
    con = connect(db)
    try:
        cur = con.execute("UPDATE watchlist SET state = ? WHERE id = ?",
                          (state, watch_id))
        con.commit()
        return cur.rowcount == 1
    finally:
        con.close()


def watchlist_touch_checked(db: Path | None, watch_id: int,
                            now_ts: int | None = None) -> bool:
    """標記某 watchlist 已研究(更新 last_checked_at)。"""
    con = connect(db)
    try:
        cur = con.execute("UPDATE watchlist SET last_checked_at = ? WHERE id = ?",
                          (now_ts if now_ts is not None else now(), watch_id))
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

    p_f = sub.add_parser("facets", help="個人模型 facets(part-007)").add_subparsers(
        dest="verb", required=True)
    fl = p_f.add_parser("list")
    fl.add_argument("--class", dest="facet_class", default=None,
                    choices=list(FACET_CLASSES))
    fl.add_argument("--all", action="store_true", help="含 superseded/forgotten 歷史")
    fp = p_f.add_parser("pin", help="使用者確認:直升 stable 且評分免動")
    fp.add_argument("id", type=int)
    ff = p_f.add_parser("forget", help="停用不刪;證據仍在,不再載入/升級")
    ff.add_argument("id", type=int)

    p_w = sub.add_parser("watchlist", help="知識偵察訂閱(part-008)").add_subparsers(
        dest="verb", required=True)
    wa = p_w.add_parser("add")
    wa.add_argument("topic")
    wa.add_argument("source_url")
    wa.add_argument("--interval", type=int, default=7, dest="interval_days")
    p_w.add_parser("list")
    wp = p_w.add_parser("pause")
    wp.add_argument("id", type=int)
    wr = p_w.add_parser("resume")
    wr.add_argument("id", type=int)

    p_a = sub.add_parser("advices", help="主動建議(part-009)").add_subparsers(
        dest="verb", required=True)
    al = p_a.add_parser("list")
    al.add_argument("--state", default=None,
                    choices=["pending", "pushed", "accepted", "ignored", "expired"])
    al.add_argument("--priority", default=None, choices=["low", "medium", "high"])

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

    if args.domain == "facets":
        if args.verb == "list":
            _print_rows(facet_list(db, facet_class=args.facet_class,
                                   include_inactive=args.all),
                        [("id", "#"), ("facet_class", "class"), ("facet_key", "key"),
                         ("value", "value"), ("state", "state"),
                         ("user_state", "user"), ("evidence_count", "evidence"),
                         ("last_seen_at", "last_seen")])
        elif args.verb == "pin":
            ok = facet_set_user_state(db, args.id, "pinned")
            print(f"OK: facet #{args.id} pinned" if ok
                  else f"NOT ACTIVE: #{args.id}")
            return 0 if ok else 1
        elif args.verb == "forget":
            ok = facet_set_user_state(db, args.id, "forgotten")
            print(f"OK: facet #{args.id} forgotten" if ok
                  else f"NOT FOUND / already forgotten: #{args.id}")
            return 0 if ok else 1
        return 0

    if args.domain == "watchlist":
        if args.verb == "add":
            wid = watchlist_add(db, args.topic, args.source_url,
                                interval_days=args.interval_days)
            print(f"OK: watchlist #{wid}")
        elif args.verb == "list":
            _print_rows(watchlist_list(db),
                        [("id", "#"), ("topic", "topic"), ("source_url", "url"),
                         ("interval_days", "every"), ("state", "state"),
                         ("last_checked_at", "last")])
        elif args.verb in ("pause", "resume"):
            state = "paused" if args.verb == "pause" else "active"
            ok = watchlist_set_state(db, args.id, state)
            print(f"OK: watchlist #{args.id} {state}" if ok
                  else f"NOT FOUND: #{args.id}")
            return 0 if ok else 1
        return 0

    if args.domain == "advices":
        if args.verb == "list":
            _print_rows(advice_list(db, state=args.state, priority=args.priority),
                        [("id", "#"), ("priority", "prio"), ("state", "state"),
                         ("observation", "observation"), ("suggestion", "suggestion"),
                         ("expires_at", "expires")])
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
