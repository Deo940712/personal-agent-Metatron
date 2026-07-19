"""檢索索引(docs/MEMORY-zh.md §4;探針實證行為,勿憑直覺改)。

index.db = 衍生物:不存唯一資料,可整檔刪除重建。
平台行為(probe-verified 2026-07-13):
- P1: sqlite-vec 每條連線都要 enable_load_extension + load → 自帶 _connect
- P2: vec0 不支援 INSERT OR REPLACE → upsert = DELETE + INSERT
- P3: vec0 rowid 只接受 INTEGER → note_map(TEXT note_id ↔ INT rowid)
- P4: FTS5 unicode61 對中文不命中;trigram 需 ≥3 字;LIKE 可用 → 查詢降級策略
- P5: embedding 存 binary blob(float32 LE),不存 JSON 字串
"""

from __future__ import annotations

import sqlite3
import struct
from pathlib import Path

import config

_SCHEMA = f"""
CREATE TABLE IF NOT EXISTS note_map (
  rowid    INTEGER PRIMARY KEY AUTOINCREMENT,
  note_id  TEXT NOT NULL UNIQUE
);
CREATE VIRTUAL TABLE IF NOT EXISTS notes_fts USING fts5(
  note_id, title, summary, tags, tokenize='trigram'
);
CREATE TABLE IF NOT EXISTS meta (
  key TEXT PRIMARY KEY, value TEXT
);
"""
# notes_vec 的維度來自 config,單獨建(需 extension 已載入)
_VEC_TABLE = "CREATE VIRTUAL TABLE IF NOT EXISTS notes_vec USING vec0(embedding float[{dim}])"


def _connect(idx_db: Path) -> sqlite3.Connection:
    """P1:每條連線都要 load sqlite-vec。不共用 stm.connect。"""
    import sqlite_vec
    idx_db.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(idx_db)
    con.enable_load_extension(True)
    sqlite_vec.load(con)
    con.enable_load_extension(False)
    con.executescript(_SCHEMA)
    con.execute(_VEC_TABLE.format(dim=config.EMBED_DIM))
    return con


def pack_vector(vec: list[float]) -> bytes:
    """P5:float32 LE binary blob。維度錯 → ValueError(呼叫端程式錯)。"""
    if len(vec) != config.EMBED_DIM:
        raise ValueError(f"vector dim {len(vec)} != EMBED_DIM {config.EMBED_DIM}")
    return struct.pack(f"{len(vec)}f", *vec)


def _get_or_create_rowid(con: sqlite3.Connection, note_id: str) -> int:
    row = con.execute("SELECT rowid FROM note_map WHERE note_id = ?", (note_id,)).fetchone()
    if row:
        return row[0]
    cur = con.execute("INSERT INTO note_map (note_id) VALUES (?)", (note_id,))
    return cur.lastrowid


def upsert(idx_db: Path, note_id: str, *, title: str, summary: str,
           tags: list[str], vector: list[float] | None = None) -> None:
    """P2:DELETE+INSERT(vec0 無 OR REPLACE)。vector=None 只更新 FTS。"""
    con = _connect(idx_db)
    try:
        rid = _get_or_create_rowid(con, note_id)
        con.execute("DELETE FROM notes_fts WHERE note_id = ?", (note_id,))
        con.execute("INSERT INTO notes_fts (note_id, title, summary, tags) VALUES (?, ?, ?, ?)",
                    (note_id, title, summary, " ".join(tags)))
        if vector is not None:
            con.execute("DELETE FROM notes_vec WHERE rowid = ?", (rid,))
            con.execute("INSERT INTO notes_vec (rowid, embedding) VALUES (?, ?)",
                        (rid, pack_vector(vector)))
        con.commit()
    finally:
        con.close()


def all_tags(idx_db: Path) -> list[str]:
    """part-013:列出所有筆記的 tags(展平,含重複)——供知識庫總覽 tag 統計。

    從 notes_fts 讀(tags 空白分隔);零檔案 I/O,不掃 vault。壞/缺 → 空。
    """
    con = _connect(idx_db)
    try:
        out: list[str] = []
        for (raw,) in con.execute("SELECT tags FROM notes_fts"):
            if raw:
                out.extend(t for t in raw.split() if t)
        return out
    except Exception:                             # noqa: BLE001 — 索引衍生物容錯
        return []
    finally:
        con.close()


def _has_long_token(query: str) -> bool:
    """trigram MATCH 需要 ≥3 字元的連續 token(中英皆然)。"""
    return any(len(tok) >= 3 for tok in query.split()) or len(query.replace(" ", "")) >= 3


def search_fts(idx_db: Path, query: str, limit: int = 10) -> list[tuple[str, float]]:
    """P4:≥3 字用 MATCH(有 bm25 排名);<3 字降級 LIKE(無排名,score=0)。"""
    if not query.strip():
        return []
    con = _connect(idx_db)
    try:
        if _has_long_token(query):
            try:
                rows = con.execute(
                    "SELECT note_id, bm25(notes_fts) FROM notes_fts "
                    "WHERE notes_fts MATCH ? ORDER BY bm25(notes_fts) LIMIT ?",
                    (f'"{query}"', limit)).fetchall()
                if rows:
                    return [(r[0], r[1]) for r in rows]
            except sqlite3.OperationalError:
                pass  # 查詢含 FTS 特殊語法 → 落到 LIKE
        pat = f"%{query}%"
        rows = con.execute(
            "SELECT note_id FROM notes_fts WHERE title LIKE ? OR summary LIKE ? "
            "OR tags LIKE ? LIMIT ?", (pat, pat, pat, limit)).fetchall()
        return [(r[0], 0.0) for r in rows]
    finally:
        con.close()


def search_vec(idx_db: Path, vector: list[float], k: int = 5) -> list[tuple[str, float]]:
    """KNN。回 [(note_id, distance)],distance 越小越近。"""
    con = _connect(idx_db)
    try:
        rows = con.execute(
            "SELECT m.note_id, v.distance FROM notes_vec v "
            "JOIN note_map m ON m.rowid = v.rowid "
            "WHERE v.embedding MATCH ? AND k = ?",
            (pack_vector(vector), k)).fetchall()
        return [(r[0], r[1]) for r in rows]
    finally:
        con.close()


def set_meta(idx_db: Path, key: str, value: str) -> None:
    con = _connect(idx_db)
    try:
        con.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (key, value))
        con.commit()
    finally:
        con.close()


def get_meta(idx_db: Path, key: str) -> str | None:
    con = _connect(idx_db)
    try:
        row = con.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return row[0] if row else None
    finally:
        con.close()


def rebuild(idx_db: Path, vault: Path, embed_fn=None) -> int:
    """整檔重建:刪 index.db → 掃 vault registry → 全量重灌。回傳筆數。

    embed_fn: (text) -> list[float] | None。None = 只建 FTS(向量下次 upsert 補)。
    衍生物哲學:壞了/換模型就重建,零資料損失。
    """
    from core import ltm
    idx_db.unlink(missing_ok=True)
    Path(str(idx_db) + "-wal").unlink(missing_ok=True)
    Path(str(idx_db) + "-shm").unlink(missing_ok=True)

    count = 0
    for entry in ltm.registry_entries(vault):
        note = ltm.read_note(vault, entry["path"])
        if note is None:
            continue  # 壞筆記跳過,不炸重建
        fm = note["frontmatter"]
        tags = fm.get("tags", []) if isinstance(fm.get("tags"), list) else []
        vector = None
        if embed_fn is not None:
            vector = embed_fn(f"{entry['title']} {entry['summary']} {' '.join(tags)}")
        upsert(idx_db, entry["id"], title=entry["title"],
               summary=entry["summary"], tags=tags, vector=vector)
        count += 1
    set_meta(idx_db, "embed_model", config.EMBED_MODEL)
    set_meta(idx_db, "embed_dim", str(config.EMBED_DIM))
    return count
