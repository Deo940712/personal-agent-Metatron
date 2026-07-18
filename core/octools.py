"""OpenCode session 儲存唯讀讀取器(part-005;兼 part-006 dev_status 資料層)。

讀 `~/.local/share/opencode/opencode.db`(SQLite,WAL)——**只讀,永不寫**:
- URI `mode=ro` 開啟(物理唯讀,同儀表板哲學)
- WAL 模式支援與運行中的 OpenCode 併發讀(part-006 探勘已證)

探勘實證(2026-07-13,DESIGN P1-P5):
- session.time_updated 是 epoch **毫秒** → 統一轉秒(全系統慣例)
- session.directory 用正斜線 → Path.resolve() 正規化比對
- session.model 是 JSON 字串 → 解析失敗容忍
- schema 是 OpenCode 內部實作,版本可能變 → 全面容錯(缺表/缺欄 → 空結果)
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

OPENCODE_DB = Path.home() / ".local" / "share" / "opencode" / "opencode.db"


def _connect_ro(db_path: Path) -> sqlite3.Connection | None:
    """唯讀連線;檔案不存在/開啟失敗 → None(不 crash——schema 屬外部系統)。"""
    if not db_path.exists():
        return None
    try:
        con = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro",
                              uri=True, timeout=3.0)
        return con
    except sqlite3.Error:
        return None


def _norm_dir(p: str | Path) -> str:
    """路徑正規化比對鍵(P2:正斜線 vs 反斜線)。大小寫不敏感(Windows)。"""
    try:
        return Path(p).resolve().as_posix().lower()
    except (OSError, ValueError):
        return str(p).replace("\\", "/").lower()


def recent_sessions(directory: str | Path, *, limit: int = 5,
                    db_path: Path | None = None) -> list[dict]:
    """某專案目錄的最近 sessions:[{id, title, agent, updated_at(秒)}]。

    比對用正規化路徑;子 agent session(parent_id 非空)排除——只看主 session。
    任何 sqlite 錯誤 → 空 list(外部 schema,容錯優先)。
    """
    con = _connect_ro(db_path or OPENCODE_DB)
    if con is None:
        return []
    want = _norm_dir(directory)
    out: list[dict] = []
    try:
        rows = con.execute(
            "SELECT id, directory, title, agent, time_updated, parent_id "
            "FROM session ORDER BY time_updated DESC LIMIT 200").fetchall()
        for sid, sdir, title, agent, updated_ms, parent_id in rows:
            if parent_id:                        # 子 agent session 不算工作記錄
                continue
            if _norm_dir(sdir or "") != want:
                continue
            out.append({
                "id": sid,
                "title": title or "(untitled)",
                "agent": agent or "",
                "updated_at": int(updated_ms or 0) // 1000,   # P1:毫秒 → 秒
            })
            if len(out) >= limit:
                break
    except sqlite3.Error:
        return []
    finally:
        con.close()
    return out


def session_todos(session_id: str, *, db_path: Path | None = None) -> dict:
    """某 session 的 todo 完成率:{total, completed, in_progress, items[:5]}。"""
    con = _connect_ro(db_path or OPENCODE_DB)
    empty = {"total": 0, "completed": 0, "in_progress": 0, "items": []}
    if con is None:
        return empty
    try:
        rows = con.execute(
            "SELECT content, status FROM todo WHERE session_id = ? "
            "ORDER BY position", (session_id,)).fetchall()
    except sqlite3.Error:
        return empty
    finally:
        con.close()
    total = len(rows)
    completed = sum(1 for _, s in rows if s == "completed")
    in_progress = sum(1 for _, s in rows if s == "in_progress")
    items = [{"content": c[:120], "status": s} for c, s in rows[:5]]
    return {"total": total, "completed": completed,
            "in_progress": in_progress, "items": items}


def session_tail(session_id: str, *, n: int = 5,
                 db_path: Path | None = None) -> list[dict]:
    """某 session 最後 n 則對話的 text 摘要:[{role, text, time}](時間升序)。

    join message→part,只取 text part(tool call 等非 text 忽略)。role 來自
    message.data 的 role 欄。任何 sqlite/JSON 錯誤 → 空 list(外部 schema,容錯)。
    """
    con = _connect_ro(db_path or OPENCODE_DB)
    if con is None:
        return []
    try:
        rows = con.execute(
            "SELECT m.time_created, m.data, p.data "
            "FROM message m JOIN part p ON p.message_id = m.id "
            "WHERE m.session_id = ? "
            "ORDER BY m.time_created, p.time_created", (session_id,)).fetchall()
    except sqlite3.Error:
        return []
    finally:
        con.close()

    out: list[dict] = []
    for m_time, m_data, p_data in rows:
        try:
            part = json.loads(p_data) if p_data else {}
        except (json.JSONDecodeError, TypeError):
            continue
        if part.get("type") != "text":
            continue
        text = str(part.get("text", "")).strip()
        if not text:
            continue
        try:
            role = json.loads(m_data).get("role", "") if m_data else ""
        except (json.JSONDecodeError, TypeError):
            role = ""
        out.append({"role": role, "text": text[:500],
                    "time": int(m_time or 0)})
    return out[-n:] if n > 0 else []


def project_activity(directory: str | Path, *,
                     db_path: Path | None = None) -> dict:
    """coding_tracker 用的彙總:最近 session + 其 todo 完成率。單一入口。"""
    sessions = recent_sessions(directory, limit=3, db_path=db_path)
    todos = session_todos(sessions[0]["id"], db_path=db_path) if sessions else \
        {"total": 0, "completed": 0, "in_progress": 0, "items": []}
    return {"sessions": sessions, "latest_todos": todos}
