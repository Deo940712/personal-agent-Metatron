"""Memory recall and raw-source rehydration capability boundaries."""

from __future__ import annotations

import config
from core import recall, retrieve
from core.tools.contracts import CapabilityContext, CapabilityResult, RehydrationResult


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
