"""Schedule-oriented read and proposal capabilities."""

from __future__ import annotations

from core import stm, subagents, writer
from core.llm import LLMError
from core.subagents import SubagentError
from core.tools.contracts import CapabilityContext, CapabilityResult


def _format_schedule(rows: list[dict]) -> str:
    if not rows:
        return "(無行程)"
    return "\n".join(
        f"#{row['id']} {stm.fmt_when(row['start_at'])} {row['title']}"
        + (f" ⏰{stm.fmt_when(row['remind_at'])}" if row.get("remind_at") else "")
        for row in rows
    )


def _format_tasks(rows: list[dict]) -> str:
    if not rows:
        return "(無待辦)"
    return "\n".join(
        f"#{row['id']} {row['title']}"
        + (f" (due {stm.fmt_when(row['due_at'])})" if row.get("due_at") else "")
        for row in rows
    )


def today(context: CapabilityContext) -> CapabilityResult:
    """List active schedule items and tasks in the established chat format."""
    text = (
        "今日行程/待辦:\n"
        + _format_schedule(stm.schedule_list(context.db))
        + "\n---\n"
        + _format_tasks(stm.task_list(context.db))
    )
    return CapabilityResult(text)


def week(context: CapabilityContext) -> CapabilityResult:
    """List active schedule items in the established chat format."""
    return CapabilityResult("行程:\n" + _format_schedule(stm.schedule_list(context.db)))


def range_view(start_iso: str, end_iso: str, label: str,
               context: CapabilityContext) -> CapabilityResult:
    """part-012:確定性時間窗查詢(router 給已驗證的 ISO range;本地時區含頭尾)。

    「明天有什麼」「下週三有事嗎」的回答層——LLM 理解語言,程式算時間與查 DB。
    """
    from datetime import datetime, timedelta

    start_ts = int(datetime.fromisoformat(start_iso).timestamp())
    end_ts = int((datetime.fromisoformat(end_iso) + timedelta(days=1)).timestamp())
    con = stm.connect(context.db)
    try:
        cur = con.execute(
            "SELECT id, title, start_at, remind_at FROM schedule "
            "WHERE status = 'active' AND start_at >= ? AND start_at < ? "
            "ORDER BY start_at", (start_ts, end_ts))
        cols = [c[0] for c in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    finally:
        con.close()
    scope = label or f"{start_iso}~{end_iso}"
    if not rows:
        return CapabilityResult(f"{scope}沒有排任何行程。")
    return CapabilityResult(f"{scope}有 {len(rows)} 件事:\n" + _format_schedule(rows))


def propose(text: str, context: CapabilityContext) -> CapabilityResult:
    """Parse natural language and stage a validated proposal when confirmation is required."""
    try:
        active = stm.schedule_list(context.db) + stm.task_list(context.db)
        proposal = subagents.run_schedule(
            text,
            active_items=active,
            db=context.db,
            _api=context.api,
        )
    except (LLMError, SubagentError) as error:
        return CapabilityResult(f"解析失敗:{error}")
    if "error" in proposal:
        return CapabilityResult(f"這不是行程/待辦:{proposal['error']}")
    return stage(proposal, context)


def stage(proposal: dict, context: CapabilityContext) -> CapabilityResult:
    """Pass a raw proposal through writer validation and the shared pending store."""
    precheck = writer.precheck(proposal, context.db)
    if not precheck.ok:
        return CapabilityResult(f"無法處理:{precheck.reason}")
    if not precheck.needs_confirm:
        result = writer.apply_validated(precheck.proposal, context.db)
        mark = "✔" if result.ok else "✘"
        return CapabilityResult(f"{mark} {result.detail}")
    pending_id = stm.pending_add(
        context.db,
        proposal,
        precheck.preview,
        channel_ref=context.channel_ref,
    )
    return CapabilityResult(
        f"請確認:\n{precheck.preview}",
        pending_id=pending_id,
        needs_confirmation=True,
    )
