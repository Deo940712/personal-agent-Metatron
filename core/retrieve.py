"""檢索(docs/MEMORY-zh.md §6;ARCHITECTURE §6.4;part-004.5 RRF 融合)。

① index-first:INDEX registry 一行描述比對(零成本、可解釋)
   ——強命中(≥2 token)仍短路,保留零成本路徑
② FTS5:trigram 全文(中文 ≥3 字 / LIKE 降級,零 embedding 成本)
③ 向量 KNN:sqlite-vec(語意「換句話說」,一次 embed 呼叫)
   ②③ 與弱 index 候選經 RRF(Reciprocal Rank Fusion, k=60)融合排序
   (backlog-024,Cognis/Mneme 標配——取代「前段命中即返回」)
④ rehydrate:沿 source_ids 讀 transcript 原文(要確切數字/名字時)

命中閉環:任一段命中 → health.on_hit(來源 events)——常被問到的記憶衰減變慢。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from core import health, ltm, transcript, vindex


RRF_K = 60    # RRF 標準常數(Cormack et al.;Cognis/Mneme 同值)


@dataclass
class Hit:
    note_id: str
    path: str
    score: float      # 融合後 = RRF 分數(越大越好);短路路徑 = 命中 token 數
    stage: str        # 'index' | 'fts' | 'vec' | 'rrf'


def _tokens(query: str) -> list[str]:
    """查詢 → 比對用 token(中文連續段 + 英數詞,≥2 字)。"""
    return [t for t in re.findall(r"[\u4e00-\u9fff]{2,}|[a-zA-Z0-9]{2,}", query)]


def _rrf_fuse(candidate_lists: list[list[Hit]], k: int = RRF_K) -> list[Hit]:
    """Reciprocal Rank Fusion:每清單依名次給 1/(k+rank),同 note_id 跨清單加總。

    純函數(backlog-024)。輸入清單各自已按該段的優先序排好(index 0 = rank 1)。
    輸出按融合分數降冪;stage 標 'rrf',score = 融合分數。
    """
    scores: dict[str, float] = {}
    best_hit: dict[str, Hit] = {}
    for hits in candidate_lists:
        for rank, hit in enumerate(hits, start=1):
            scores[hit.note_id] = scores.get(hit.note_id, 0.0) + 1.0 / (k + rank)
            if hit.note_id not in best_hit:
                best_hit[hit.note_id] = hit
    fused = [Hit(nid, best_hit[nid].path, score, "rrf")
             for nid, score in scores.items()]
    fused.sort(key=lambda h: (-h.score, h.note_id))   # 分數同 → id 穩定排序
    return fused


def _strong_index_hits(vault: Path, query: str, limit: int, *,
                        include_evidence: bool = False) -> list[Hit]:
    """強命中:≥2 個 token 命中同一筆記 → 短路(零 FTS/embedding 成本)。
    單 token 查詢時,全部 token(=1)命中也算強。
    KB 2.0:預設只搜尋 topic notes;include_evidence=True 時也包含原始貼文。"""
    toks = _tokens(query)
    if not toks:
        return []
    need = min(2, len(toks))
    out = []
    for e in ltm.registry_entries(vault):
        # KB 2.0: skip evidence notes unless explicitly included
        if not include_evidence:
            note = ltm.read_note(vault, e["path"])
            if note and note["frontmatter"].get("note_type") == "evidence":
                continue
        haystack = f"{e['title']} {e['summary']}"
        n_hit = sum(1 for t in toks if t in haystack)
        if n_hit >= need:
            out.append(Hit(e["id"], e["path"], float(n_hit), "index"))
    out.sort(key=lambda h: (-h.score, h.note_id))
    return out[:limit]


def search(vault: Path, idx_db: Path, query: str, *,
           embed_fn=None, limit: int = 5,
           db: Path | None = None,
           include_evidence: bool = False) -> list[Hit]:
    """RRF 融合檢索(part-004.5):強 index 命中短路;否則三段候選融合。

    embed_fn: (text) -> list[float]。None = 跳過向量段(無 embedding 能力時)。
    db: 提供時,命中筆記的 source_ids 中 evt: 事件會觸發回血。
    include_evidence: KB 2.0——True 時也搜尋原始貼文(evidence);預設 False 只搜尋
        精煉後的主題筆記(topic),讓檢索結果更乾淨。
    """
    # 零成本短路:多 token 強命中不需要融合
    strong = _strong_index_hits(vault, query, limit, include_evidence=include_evidence)
    if strong:
        if db is not None:
            _heal_sources(vault, strong, db)
        return strong

    # 三段並行取候選(池放大 2 倍)→ RRF 融合
    pool = limit * 2
    idx_hits = _stage_index(vault, query, pool, include_evidence=include_evidence)
    fts_hits = _stage_fts(vault, idx_db, query, pool, include_evidence=include_evidence)
    vec_hits = _stage_vec(vault, idx_db, query, embed_fn, pool) if embed_fn else []
    hits = _rrf_fuse([idx_hits, fts_hits, vec_hits])[:limit]

    if hits and db is not None:
        _heal_sources(vault, hits, db)
    return hits


def _stage_index(vault: Path, query: str, limit: int, *,
                  include_evidence: bool = False) -> list[Hit]:
    """① registry 一行描述比對:任一 token 出現在 title/summary。
    KB 2.0:預設只搜尋 topic notes;include_evidence=True 時也包含原始貼文。"""
    toks = _tokens(query)
    if not toks:
        return []
    out = []
    for e in ltm.registry_entries(vault):
        # KB 2.0: skip evidence notes unless explicitly included
        if not include_evidence:
            note = ltm.read_note(vault, e["path"])
            if note and note["frontmatter"].get("note_type") == "evidence":
                continue
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


def _stage_fts(vault: Path, idx_db: Path, query: str, limit: int, *,
                include_evidence: bool = False) -> list[Hit]:
    if not idx_db.exists():
        return []
    hits = [Hit(nid, _note_path(vault, nid), score, "fts")
            for nid, score in vindex.search_fts(idx_db, query, limit)]
    # KB 2.0: filter evidence notes unless explicitly included
    if not include_evidence:
        filtered = []
        for h in hits:
            note = ltm.read_note(vault, h.path) if h.path else None
            if note and note["frontmatter"].get("note_type") == "evidence":
                continue
            filtered.append(h)
        return filtered
    return hits


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
