"""Task proposal and completion capabilities."""

from __future__ import annotations

from typing import Literal

from core import proposals, stm, writer
from core.tools import schedule
from core.tools.contracts import CapabilityContext, CapabilityResult


def add(title: str, *, evidence: str, context: CapabilityContext) -> CapabilityResult:
    """Stage a deterministic task-add proposal through the writer precheck path."""
    proposal = {
        "agent": "schedule",
        "proposal_type": "task_change",
        "target": "new",
        "payload": {"action": "add", "fields": {"title": title}},
        "confidence": 1.0,
        "evidence": [evidence],
    }
    return schedule.stage(proposal, context)


def complete(reference: str, context: CapabilityContext) -> CapabilityResult:
    """Complete an item; require its kind when task and schedule ids collide."""
    parts = reference.lower().split()
    kind: Literal["task", "schedule"] | None = None
    item_id = reference
    if len(parts) == 1:
        item_id = parts[0]
    elif len(parts) == 2:
        item_kind, item_id = parts
        if item_kind in {"task", "tasks", "待辦"}:
            kind = "task"
        elif item_kind in {"schedule", "行程"}:
            kind = "schedule"
        else:
            return CapabilityResult(
                "用法:done <編號>；撞號時用 done task <編號> 或 done schedule <編號>"
            )
    else:
        return CapabilityResult(
            "用法:done <編號>；撞號時用 done task <編號> 或 done schedule <編號>"
        )
    if not item_id.isdigit():
        return CapabilityResult(
            "用法:done <編號>；撞號時用 done task <編號> 或 done schedule <編號>"
        )

    row_id = int(item_id)
    proposal_type = {
        "task": "task_change",
        "schedule": "schedule_change",
    }
    if kind is not None:
        precheck = writer.precheck(
            _done_proposal(proposal_type[kind], row_id, reference),
            context.db,
        )
    else:
        task_precheck = writer.precheck(
            _done_proposal("task_change", row_id, reference),
            context.db,
        )
        schedule_exists = any(
            row["id"] == row_id
            for row in stm.schedule_list(context.db, include_done=True)
        )
        if task_precheck.ok and schedule_exists:
            return CapabilityResult(
                f"#{row_id} 同時存在待辦與行程；請用 done task {row_id} "
                f"或 done schedule {row_id}。"
            )
        precheck = task_precheck
        if not precheck.ok:
            precheck = writer.precheck(
                _done_proposal("schedule_change", row_id, reference),
                context.db,
            )

    if not precheck.ok:
        return CapabilityResult(f"找不到 #{row_id} 或無法完成:{precheck.reason}", outcome="rejected")
    result = writer.apply_validated(precheck.proposal, context.db)
    mark = "✔" if result.ok else "✘"
    return CapabilityResult(f"{mark} {result.detail}",
                            outcome="done" if result.ok else "rejected")


def _done_proposal(
    proposal_type: str,
    row_id: int,
    evidence: str,
) -> proposals.Proposal:
    return proposals.Proposal(
        agent="schedule",
        proposal_type=proposal_type,
        target=str(row_id),
        payload={"action": "done", "fields": {}},
        confidence=1.0,
        evidence=[f"done {evidence}"],
    )
