"""四段級聯檢索(docs/MEMORY-zh.md §6;ARCHITECTURE §6.4)。

① index-first:INDEX registry 一行描述比對(零成本、可解釋)
② FTS5:trigram 全文(中文 ≥3 字 / LIKE 降級,零 embedding 成本)
③ 向量 KNN:sqlite-vec(語意「換句話說」,一次 embed 呼叫)
④ rehydrate:沿 source_ids 讀 transcript 原文(要確切數字/名字時)

命中閉環:任一段命中 → health.on_hit(來源 events)——常被問到的記憶衰減變慢。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from core import health, ltm, transcript, vindex


@dataclass
class Hit:
    note_id: str
    path: str
    score: float      # 各段語意不同:index/fts-like=0、fts-match=bm25(越小越好)、vec=distance
    stage: str        # 'index' | 'fts' | 'vec'


def _tokens(query: str) -> list[str]:
    """查詢 → 比對用 token(中文連續段 + 英數詞,≥2 字)。"""
    return [t for t in re.findall(r"[\u4e00-\u9fff]{2,}|[a-zA-Z0-9]{2,}", query)]


def search(vault: Path, idx_db: Path, query: str, *,
           embed_fn=None, limit: int = 5,
           db: Path | None = None) -> list[Hit]:
    """級聯:前段命中即返回(不疊加後段);全 miss 回空。

    embed_fn: (text) -> list[float]。None = 跳過向量段(無 embedding 能力時)。
    db: 提供時,命中筆記的 source_ids 中 evt: 事件會觸發回血。
    """
    hits = _stage_index(vault, query, limit)
    if not hits:
        hits = _stage_fts(vault, idx_db, query, limit)
    if not hits and embed_fn is not None:
        hits = _stage_vec(vault, idx_db, query, embed_fn, limit)

    if hits and db is not None:
        _heal_sources(vault, hits, db)
    return hits


def _stage_index(vault: Path, query: str, limit: int) -> list[Hit]:
    """① registry 一行描述比對:任一 token 出現在 title/summary。"""
    toks = _tokens(query)
    if not toks:
        return []
    out = []
    for e in ltm.registry_entries(vault):
        haystack = f"{e['title']} {e['summary']}"
        if any(t in haystack for t in toks):
            out.append(Hit(e["id"], e["path"], 0.0, "index"))
            if len(out) >= limit:
                break
    return out


def _note_path(vault: Path, note_id: str) -> str:
    for e in ltm.registry_entries(vault):
        if e["id"] == note_id:
            return e["path"]
    return ""


def _stage_fts(vault: Path, idx_db: Path, query: str, limit: int) -> list[Hit]:
    if not idx_db.exists():
        return []
    return [Hit(nid, _note_path(vault, nid), score, "fts")
            for nid, score in vindex.search_fts(idx_db, query, limit)]


def _stage_vec(vault: Path, idx_db: Path, query: str, embed_fn, limit: int) -> list[Hit]:
    if not idx_db.exists():
        return []
    return [Hit(nid, _note_path(vault, nid), dist, "vec")
            for nid, dist in vindex.search_vec(idx_db, embed_fn(query), limit)]


def _heal_sources(vault: Path, hits: list[Hit], db: Path) -> None:
    """命中閉環:筆記 source_ids 的 evt:<id> → health.on_hit。"""
    event_ids: list[int] = []
    for h in hits:
        note = ltm.read_note(vault, h.path) if h.path else None
        if not note:
            continue
        src = note["frontmatter"].get("source_ids", [])
        if isinstance(src, str):                 # frontmatter 解析可能回字串
            try:
                src = json.loads(src)
            except json.JSONDecodeError:
                continue
        for sid in src:
            if isinstance(sid, str) and sid.startswith("evt:") and sid[4:].isdigit():
                event_ids.append(int(sid[4:]))
    if event_ids:
        health.on_hit(db, event_ids)


def rehydrate(vault: Path, note_path: str, *,
              transcript_dir: Path | None = None) -> list[dict]:
    """④ 沿筆記 source_ids 讀回 transcript 原文(摘要不夠精確時)。"""
    note = ltm.read_note(vault, note_path)
    if not note:
        return []
    src = note["frontmatter"].get("source_ids", [])
    if not isinstance(src, list) or not src:
        return []
    entries, _missing = transcript.read_by_ids(transcript_dir, src)
    return entries
