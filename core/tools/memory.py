"""Memory recall and raw-source rehydration capability boundaries."""

from __future__ import annotations

import config
from core import recall, retrieve
from core.tools.contracts import CapabilityContext, CapabilityResult, RehydrationResult


def list_knowledge(context: CapabilityContext) -> CapabilityResult:
    """part-013:知識庫總覽(確定性,零 LLM)——筆記數 + tag 分布 + 最近幾篇。

    這是「瀏覽」而非「問答」:回答「我知識庫有什麼」。掃 registry + frontmatter
    tags 做統計。個人量級 O(n) 可接受。
    """
    from collections import Counter

    from core import ltm

    vault = context.vault or config.VAULT_PATH
    entries = ltm.registry_entries(vault)
    if not entries:
        return CapabilityResult("知識庫目前是空的。同步 threads 或跑知識偵察後就有料。",
                                outcome="no_result")

    # tag 統計走向量索引(vindex 有存 tags,零檔案 I/O)——避免 O(n) 讀 808 篇 frontmatter
    idx_db = context.idx_db or config.INDEX_DB
    tag_counts: Counter = Counter()
    try:
        from core import vindex
        for tag in vindex.all_tags(idx_db):
            if tag not in ("inbox", "threads"):
                tag_counts[tag] += 1
    except Exception:                             # noqa: BLE001 — 索引衍生物,壞了不擋列表
        pass

    top_tags = tag_counts.most_common(10)
    recent = entries[-5:][::-1]     # registry 尾端 = 最新(append-only)

    lines = [f"知識庫共 {len(entries)} 篇筆記。"]
    if top_tags:
        lines.append("\n主題分布(前 10):")
        lines.extend(f"  {tag} × {n}" for tag, n in top_tags)
    lines.append("\n最近幾篇:")
    lines.extend(f"  · {e['title']}" for e in recent)
    if top_tags:
        lines.append(f"\n輸入「看 <主題>」下鑽,例如「看 {top_tags[0][0]}」。")
    return CapabilityResult("\n".join(lines), outcome="answered")


def browse_topic(tag: str, context: CapabilityContext) -> CapabilityResult:
    """part-015 三層下鑽 L2:列某主題(tag)下的筆記標題 + id(確定性,零 LLM)。

    走向量索引 notes_by_tag 找 id,再對 registry 補標題;最多列前 20 篇 + 提示
    下一步「看筆記 <id>」。無狀態下鑽(每層獨立指令)。
    """
    from core import ltm, vindex

    vault = context.vault or config.VAULT_PATH
    idx_db = context.idx_db or config.INDEX_DB

    ids = vindex.notes_by_tag(idx_db, tag, limit=20)
    if not ids:
        return CapabilityResult(
            f"主題「{tag}」下沒有筆記。用「瀏覽知識庫」看有哪些主題。",
            outcome="no_result")

    by_id = {e["id"]: e for e in ltm.registry_entries(vault)}
    lines = [f"主題「{tag}」下的筆記(前 {len(ids)} 篇):"]
    for nid in ids:
        title = by_id[nid]["title"] if nid in by_id else nid
        lines.append(f"  · {title}  —  {nid}")
    lines.append("\n輸入「看筆記 <id>」看內容,例如「看筆記 " + ids[0] + "」。")
    return CapabilityResult("\n".join(lines), outcome="answered")


def open_note(note_id: str, context: CapabilityContext) -> CapabilityResult:
    """part-015 三層下鑽 L3:開一篇筆記看內容(確定性,零 LLM)。

    走 registry 找路徑(fallback semantic/),讀 frontmatter 摘要 + 內文。
    """
    from core import ltm

    vault = context.vault or config.VAULT_PATH
    entry = next((e for e in ltm.registry_entries(vault) if e["id"] == note_id), None)
    rel_path = entry["path"] if entry else f"semantic/{note_id}.md"
    note = ltm.read_note(vault, rel_path)
    if note is None:
        return CapabilityResult(
            f"找不到筆記「{note_id}」。用「看 <主題>」列出該主題筆記再挑。",
            outcome="no_result")

    fm = note["frontmatter"]
    title = fm.get("title", note_id)
    tags = fm.get("tags", [])
    tag_str = " ".join(tags) if isinstance(tags, list) else str(tags)
    header = f"# {title}  ({note_id})"
    if tag_str:
        header += f"\n主題:{tag_str}"
    return CapabilityResult(f"{header}\n\n{note['body']}", outcome="answered")


def query(text: str, context: CapabilityContext) -> CapabilityResult:
    """Run citation-aware recall with dependencies supplied by the interface.
    
    KB 2.0: 預設只搜尋 topic notes;若需搜尋原始貼文(evidence),
    使用「搜原文 <query>」或「include evidence」。
    """
    # KB 2.0: 檢查是否明確要求搜尋原始貼文
    include_evidence = "搜原文" in text or "include evidence" in text.lower()
    if include_evidence:
        # 移除指令前綴,只保留實際查詢
        text = text.replace("搜原文", "").replace("include evidence", "").strip()
    
    result = recall.ask(
        text,
        vault=context.vault,
        idx_db=context.idx_db,
        db=context.db,
        transcript_dir=context.transcript_dir,
        _api=context.api,
        include_evidence=include_evidence,
    )
    # 裂縫1/3:把 recall 的 found/not_found 契約帶回,供上層推 outcome。
    # ok=False(執行異常)也視為 not_found(誠實:沒有可信答案)。
    outcome = result.outcome if result.ok else "not_found"
    return CapabilityResult(result.text, outcome=outcome)


def rehydrate(note_path: str, context: CapabilityContext) -> RehydrationResult:
    """Follow a note's source ids into append-only cold transcript storage."""
    vault = context.vault or config.VAULT_PATH
    entries = retrieve.rehydrate(
        vault,
        note_path,
        transcript_dir=context.transcript_dir,
    )
    return RehydrationResult(tuple(entries))
