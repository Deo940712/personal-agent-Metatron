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
    return CapabilityResult("\n".join(lines), outcome="answered")


def query(text: str, context: CapabilityContext) -> CapabilityResult:
    """Run citation-aware recall with dependencies supplied by the interface."""
    result = recall.ask(
        text,
        vault=context.vault,
        idx_db=context.idx_db,
        db=context.db,
        transcript_dir=context.transcript_dir,
        _api=context.api,
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
