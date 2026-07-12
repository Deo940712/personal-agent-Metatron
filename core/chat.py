"""平台無關的聊天邏輯(part-002.5;INTERFACES §4)。

零 discord 依賴——channels/discord_bot.py 是薄 adapter,把平台事件橋接到這裡。
所有狀態在 DB1;chat 實例無狀態,重啟不丟(待確認提案存 pending_proposals)。

兩階段確認(DESIGN §Chosen Design):
- 階段1 handle_message:text → 分派 → 需確認則存 pending 回預覽;免確認直接落地
- 階段2 confirm:使用者按鈕後 → writer.confirm_and_apply(重驗後落地)

回傳統一 Reply(text + 可選 pending_id 供 adapter 掛按鈕)。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from core import stm, subagents, writer
from core.llm import LLMError
from core.subagents import SubagentError

# 確認逾時(DESIGN §4.4:10 分鐘)
CONFIRM_TTL_SECONDS = 600

# 深度知識查詢關鍵詞 → 拒絕(§4.1 內容分級:知識不經 Discord)
_KNOWLEDGE_PREFIXES = ("查", "search", "recall", "找筆記", "知識")


@dataclass
class Reply:
    text: str
    pending_id: int | None = None    # 非 None → adapter 掛 ✅/❌ 按鈕
    needs_buttons: bool = False


def _fmt_schedule(rows: list[dict]) -> str:
    if not rows:
        return "(無行程)"
    return "\n".join(
        f"#{r['id']} {stm.fmt_when(r['start_at'])} {r['title']}"
        + (f" ⏰{stm.fmt_when(r['remind_at'])}" if r.get("remind_at") else "")
        for r in rows)


def _fmt_tasks(rows: list[dict]) -> str:
    if not rows:
        return "(無待辦)"
    return "\n".join(
        f"#{r['id']} {r['title']}" + (f" (due {stm.fmt_when(r['due_at'])})" if r.get("due_at") else "")
        for r in rows)


def _fmt_projects(rows: list[dict]) -> str:
    if not rows:
        return "(無專案)"
    return "\n".join(
        f"{r['name']}: {r.get('phase') or '-'}"
        + (f" | blockers: {', '.join(r['blockers'])}" if r.get("blockers") else "")
        + (f" | next: {r['next_action']}" if r.get("next_action") else "")
        for r in rows)


def handle_message(text: str, *, channel_ref: str | None = None,
                   db: Path | None = None, _api=None) -> Reply:
    """階段1:訊息 → 回覆(可能帶待確認 pending_id)。"""
    stripped = text.strip()
    low = stripped.lower()

    # 空訊息:不打 LLM(audit C7)
    if not stripped:
        return Reply("請輸入指令(today / week / proj / todo <內容> / done <編號> / 或直接說要排的行程)。")

    # 深度知識查詢:明確拒絕(內容分級,§4.1)
    if any(stripped.startswith(p) for p in _KNOWLEDGE_PREFIXES):
        return Reply("知識庫查詢請用本機 CLI(recall);Discord 只處理行程/待辦/提醒。")

    # 確定性前綴分派(零 LLM)——唯讀查詢免確認
    if low in ("today", "今天"):
        return Reply("今日行程/待辦:\n" + _fmt_schedule(stm.schedule_list(db))
                     + "\n---\n" + _fmt_tasks(stm.task_list(db)))
    if low in ("week", "本週"):
        return Reply("行程:\n" + _fmt_schedule(stm.schedule_list(db)))
    if low in ("proj", "專案"):
        return Reply("專案進度:\n" + _fmt_projects(stm.project_show(db)))

    # done N:標記完成(免確認,§3.1 規則 7)。'done' 無參數也接住
    if low == "done" or low.startswith("done "):
        return _handle_done(stripped[4:].strip(), db)

    # todo ...:待辦(需確認)。低頭已 strip,故 'todo' + 純空白也要接住
    if low == "todo" or low.startswith("todo "):
        title = stripped[4:].strip()
        if not title:
            return Reply("用法:todo <待辦內容>")
        proposal = {
            "agent": "schedule", "proposal_type": "task_change", "target": "new",
            "payload": {"action": "add", "fields": {"title": title}},
            "confidence": 1.0, "evidence": [stripped],
        }
        return _stage1(proposal, channel_ref, db)

    # 其餘:自然語言 → schedule 子 agent
    try:
        active = stm.schedule_list(db) + stm.task_list(db)
        proposal = subagents.run_schedule(stripped, active_items=active, db=db, _api=_api)
    except (LLMError, SubagentError) as e:
        return Reply(f"解析失敗:{e}")

    if "error" in proposal:
        return Reply(f"這不是行程/待辦:{proposal['error']}")
    return _stage1(proposal, channel_ref, db)


def _handle_done(arg: str, db: Path | None) -> Reply:
    if not arg.isdigit():
        return Reply("用法:done <編號>(先用 today 看編號)")
    rid = int(arg)
    proposal = {
        "agent": "schedule", "proposal_type": "task_change", "target": str(rid),
        "payload": {"action": "done", "fields": {}}, "confidence": 1.0,
        "evidence": [f"done {rid}"],
    }
    # done 免確認:precheck 通過即直接落地
    pre = writer.precheck(proposal, db)
    if not pre.ok:
        # 可能是 schedule 而非 task;改試 schedule_change
        proposal["proposal_type"] = "schedule_change"
        pre = writer.precheck(proposal, db)
    if not pre.ok:
        return Reply(f"找不到 #{rid} 或無法完成:{pre.reason}")
    r = writer.apply_validated(pre.proposal, db)
    return Reply(f"{'✔' if r.ok else '✘'} {r.detail}")


def _stage1(proposal: dict, channel_ref: str | None, db: Path | None) -> Reply:
    """驗證 → 需確認存 pending 回按鈕;免確認直接落地。"""
    pre = writer.precheck(proposal, db)
    if not pre.ok:
        return Reply(f"無法處理:{pre.reason}")
    if not pre.needs_confirm:
        r = writer.apply_validated(pre.proposal, db)
        return Reply(f"{'✔' if r.ok else '✘'} {r.detail}")
    pid = stm.pending_add(db, proposal, pre.preview, channel_ref=channel_ref)
    return Reply(f"請確認:\n{pre.preview}", pending_id=pid, needs_buttons=True)


def confirm(pending_id: int, approve: bool, *, db: Path | None = None) -> Reply:
    """階段2:使用者按 ✅/❌ 後。無狀態——從 DB1 取 pending,重驗後落地。"""
    pending = stm.pending_get(db, pending_id)
    if pending is None:
        return Reply("此確認已失效(找不到),請重發指令。")
    if pending["status"] != "pending":
        return Reply(f"此確認已{_status_zh(pending['status'])},請重發指令。")

    if not approve:
        stm.pending_set_status(db, pending_id, "cancelled")
        return Reply("已取消。")

    # 重驗後落地(writer.confirm_and_apply 內部重跑 precheck——audit A2'/A3')
    result = writer.confirm_and_apply(pending["proposal"], db)
    stm.pending_set_status(db, pending_id, "done" if result.ok else "cancelled")
    return Reply(f"{'✔ 已建立' if result.ok else '✘ ' + result.detail}")


def _status_zh(status: str) -> str:
    return {"done": "完成", "cancelled": "取消", "expired": "逾時失效"}.get(status, status)


def expire_pending(db: Path | None = None, now_ts: int | None = None) -> int:
    """逾時清理(併入 remind job)。回傳清理數。"""
    ids = stm.pending_expire_due(db, CONFIRM_TTL_SECONDS, now_ts=now_ts)
    for pid in ids:
        stm.event_append(db, "chat", "state_change", f"pending #{pid} expired")
    return len(ids)
