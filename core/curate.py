"""curator 管線(part-004;ARCHITECTURE §6.5 後半)。

流程:curator_pre.prepare(確定性)→ 標 duplicate → LLM 批次(≤10 篇)→
classify_note 提案 → writer.apply_classify(驗證+落地)→ 統計。

配額(Horizon category_groups):單次每 tag 進 registry 上限 CURATE_TAG_QUOTA,
超額的照常落地分類但不 promote(下輪或手動再提)——防單一主題洪水。
LLM 失敗該批跳過(筆記留 inbox 下輪重試)——與 consolidate 同哲學,永不丟資料。
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import config
from core import curator_pre, llm, ltm, stm, subagents, writer
from core import proposals as P


def _mark_duplicates(vault: Path, duplicates: list[dict], db: Path | None) -> int:
    """重複貼文:tags 改 [duplicate](不刪,append-only;不進 registry)。"""
    for note in duplicates:
        fm = note["frontmatter"]
        if str(fm.get("manual_tags", "")).lower() == "true":
            continue  # 人工改過的不動
        fm["tags"] = [curator_pre.DUPLICATE_TAG]
        ltm.update_note_frontmatter(vault, note["path"], fm)
        stm.event_append(db, "curator", "state_change",
                         f"marked duplicate: {note['path']}", target=note["path"])
    return len(duplicates)


def _classify_batch(batch: list[dict], vault: Path, db: Path | None,
                    _api=None) -> list[dict]:
    """一批筆記 → LLM → 提案 list(未驗證;path 對不上的丟棄並記 log)。"""
    allowed = sorted(ltm.controlled_tags(vault) - {curator_pre.INBOX_TAG})
    parts = [f"允許的 tags: {', '.join(allowed)}"]
    for n in batch:
        parts.append(f"筆記(path: {n['path']}):\n{n['body'][:2000]}")
    user = "\n\n".join(parts)

    system = subagents.load_contract("curator")
    result = llm.complete_json(system, user, db=db, purpose="curate", _api=_api)

    valid_paths = {n["path"] for n in batch}
    proposals = []
    notes = result.get("notes", [])
    if not isinstance(notes, list):
        stm.event_append(db, "curator", "proposal_rejected",
                         f"curate response invalid: notes is {type(notes).__name__}")
        return []
    for item in notes:
        if not isinstance(item, dict) or item.get("path") not in valid_paths:
            stm.event_append(db, "curator", "proposal_rejected",
                             f"curate item invalid or unknown path: {str(item)[:80]}")
            continue
        proposals.append({
            "agent": "curator",
            "proposal_type": "classify_note",
            "target": item["path"],
            "payload": {"score": item.get("score"), "tags": item.get("tags"),
                        "summary": item.get("summary")},
            "confidence": 1.0,   # curator 的信心以 score 表達;信封 confidence 恆 1
            "evidence": item.get("evidence") or [],
        })
    return proposals


def run(vault: Path | None = None, idx_db: Path | None = None,
        db: Path | None = None, now_ts: int | None = None, _api=None) -> dict:
    """完整 curate job。回統計 dict(進 agent_runs summary)。"""
    vault = vault or config.VAULT_PATH
    idx_db = idx_db or config.INDEX_DB
    ts = now_ts or stm.now()
    ltm.init_vault(vault)

    pre = curator_pre.prepare(vault, ts)
    stats = {"scanned": pre["scanned"], "duplicates": 0, "classified": 0,
             "promoted": 0, "rejected": 0, "batches_failed": 0}
    stats["duplicates"] = _mark_duplicates(vault, pre["duplicates"], db)

    # 把 enrich 後的 frontmatter 先寫回(content_hash/captured_at/source_id 落檔)
    for note in pre["uniques"]:
        if str(note["frontmatter"].get("manual_tags", "")).lower() != "true":
            ltm.update_note_frontmatter(vault, note["path"], note["frontmatter"])

    quota: dict[str, int] = defaultdict(int)
    uniques = pre["uniques"]
    for i in range(0, len(uniques), config.CURATE_BATCH_SIZE):
        batch = uniques[i:i + config.CURATE_BATCH_SIZE]
        try:
            proposals = _classify_batch(batch, vault, db, _api=_api)
        except llm.LLMError:
            stats["batches_failed"] += 1
            continue  # 該批留 inbox,下輪重試

        for prop in proposals:
            # 配額:主 tag 超額 → 降級為 low-score 路徑(照常記分類但不 promote)
            main_tag = prop["payload"]["tags"][0] if prop["payload"].get("tags") else ""
            over_quota = quota[main_tag] >= config.CURATE_TAG_QUOTA
            if over_quota and prop["payload"].get("score", 0) >= config.CURATE_SCORE_THRESHOLD:
                prop["payload"]["score"] = config.CURATE_SCORE_THRESHOLD - 0.1
                prop["payload"]["summary"] = f"[quota-deferred] {prop['payload']['summary']}"[:160]

            pre_r = writer.precheck(prop, db)
            if not pre_r.ok:
                stats["rejected"] += 1
                continue
            result = writer.apply_classify(pre_r.proposal, vault, idx_db, db)
            if result.ok:
                stats["classified"] += 1
                if "promoted" in result.detail:
                    stats["promoted"] += 1
                    quota[main_tag] += 1
            else:
                stats["rejected"] += 1
    return stats
