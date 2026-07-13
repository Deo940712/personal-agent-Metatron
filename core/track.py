"""coding_tracker 管線(part-005;ARCHITECTURE §3.3)。

流程:projects 表撈有 repo_path 的 → 三源唯讀掃描(確定性)→ LLM 批次綜合
(≤10 專案/批)→ project_update 提案 → writer 驗證落地(免確認)→ 統計。

部分失敗容忍:單一專案掃描壞 → 該專案帶 error 欄位照送 LLM(它會誠實回報);
LLM 整批失敗 → 該批跳過,下輪重跑(掃描是唯讀冪等,無資料損失問題)。
"""

from __future__ import annotations

import json
from pathlib import Path

from core import llm, octools, scanners, stm, subagents, writer

MAX_PROJECTS_PER_BATCH = 10


def _scan_project(name: str, repo_path: str) -> dict:
    """三源唯讀掃描(全容錯——壞源給 null,LLM 契約已定義如何處理)。"""
    return {
        "name": name,
        "beacon": scanners.beacon_scan(repo_path),
        "git": scanners.git_scan(repo_path),
        "opencode": octools.project_activity(repo_path),
    }


def _synthesize_batch(scans: list[dict], db: Path | None, _api=None) -> list[dict]:
    """一批掃描 → LLM → project_update 提案 list(幻覺專案名丟棄記 log)。"""
    parts = []
    for s in scans:
        parts.append(
            f"專案(name: {s['name']}):\n"
            f"beacon: {json.dumps(s['beacon'], ensure_ascii=False)}\n"
            f"git: {json.dumps(s['git'], ensure_ascii=False)}\n"
            f"opencode: {json.dumps(s['opencode'], ensure_ascii=False)}")
    user = "\n\n".join(parts)

    system = subagents.load_contract("coding_tracker")
    result = llm.complete_json(system, user, db=db, purpose="track", _api=_api)

    valid_names = {s["name"] for s in scans}
    proposals = []
    items = result.get("projects", [])
    if not isinstance(items, list):
        stm.event_append(db, "coding_tracker", "proposal_rejected",
                         f"track response invalid: projects is {type(items).__name__}")
        return []
    for item in items:
        if not isinstance(item, dict) or item.get("name") not in valid_names:
            stm.event_append(db, "coding_tracker", "proposal_rejected",
                             f"track item invalid or unknown project: {str(item)[:80]}")
            continue
        proposals.append({
            "agent": "coding_tracker",
            "proposal_type": "project_update",
            "target": item["name"],
            "payload": {"phase": item.get("phase"),
                        "blockers": item.get("blockers"),
                        "next_action": item.get("next_action")},
            "confidence": item.get("confidence", 0.5)
            if isinstance(item.get("confidence"), (int, float)) else 0.5,
            "evidence": [f"three-source scan of {item['name']}"],
        })
    return proposals


def run(db: Path | None = None, _api=None) -> dict:
    """完整 track job。回統計 dict(進 agent_runs summary)。"""
    rows = stm.project_show(db)
    targets = [(r["name"], r["repo_path"]) for r in rows if r.get("repo_path")]

    stats = {"projects": len(targets), "scanned": 0, "updated": 0,
             "rejected": 0, "batches_failed": 0}
    scans = []
    for name, repo_path in targets:
        scans.append(_scan_project(name, repo_path))
        stats["scanned"] += 1

    for i in range(0, len(scans), MAX_PROJECTS_PER_BATCH):
        batch = scans[i:i + MAX_PROJECTS_PER_BATCH]
        try:
            proposals = _synthesize_batch(batch, db, _api=_api)
        except llm.LLMError:
            stats["batches_failed"] += 1
            continue  # 掃描唯讀冪等,下輪重跑即可
        for prop in proposals:
            pre = writer.precheck(prop, db)
            if not pre.ok:
                stats["rejected"] += 1
                continue
            result = writer.apply_project_update(pre.proposal, db)
            if result.ok:
                stats["updated"] += 1
            else:
                stats["rejected"] += 1
    return stats
