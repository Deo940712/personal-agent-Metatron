"""統一 invocation 入口(part-006-slice-001 裂縫1;DESIGN §112-148)。

在 MCP 成為第三個介面入口前,先把 CLI(`agent.invoke`)與 Discord
(`chat.handle_message`)兩條分派路徑收斂到一處。三介面都只呼叫 `invoke`,
回結構化 `InvocationResult`,並且每次呼叫都記 `agent_runs`——含 Discord
(舊 chat 路徑不記 run,這是裂縫1 順帶修的稽核缺口)。

無 LLM router:route 由既有確定性前綴決定(沿用 chat 的分派);無法判定的
自然語言才送 schedule 子 agent。實際分派仍委派給 `core.chat.handle_message`
(單一分派權威),本模組只加結構化外殼、route/outcome 推導與 run audit。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from core import chat, stm

# route 分類用的確定性前綴(與 chat.handle_message 的分派保持一致)
_READ_WORDS = {"today", "今天", "week", "本週", "proj", "專案"}


@dataclass(frozen=True, slots=True)
class InvocationContext:
    """一次呼叫的介面情境(DESIGN §144)。

    trigger:agent_runs.trigger('cli'/'chat'/'scheduler')。
    allow_recall:本機 CLI/MCP 為 True(知識查詢放行);Discord 為 False(§4.1)。
    channel_ref:回覆定址(Discord user/channel id),寫入 pending 供跨介面確認。
    confirm_fn:同步確認回呼(CLI 用)。給定時,需確認的寫入立即
      preview→confirm→落地(不留 pending 按鈕);None 時走 pending 非同步流
      (Discord/MCP)。兩種模式共用同一分派與同一 pending_claim 原子保護。
    """

    trigger: str = "cli"
    allow_recall: bool = False
    channel_ref: str | None = None
    confirm_fn: Callable[[str], bool] | None = None


@dataclass(frozen=True, slots=True)
class InvocationResult:
    """結構化呼叫結果(DESIGN §130)。channel-neutral,adapter 只做呈現轉換。

    outcome ∈ {applied, rejected, not_actionable, answered, no_result,
    needs_confirmation}。
    """

    text: str
    route: str
    outcome: str
    run_id: int | None = None
    pending_id: int | None = None
    needs_confirmation: bool = False


def _sync_confirm(reply: chat.Reply, confirm_fn: Callable[[str], bool],
                  db: Path | None) -> chat.Reply:
    """同步收尾一個待確認 pending:preview→confirm_fn→claim+落地/取消。

    重用 chat.confirm(內部 pending_claim 原子認領);回不帶按鈕的 Reply。
    preview 即 reply.text('請確認:\\n<preview>'),整段傳給 confirm_fn。
    """
    approved = confirm_fn(reply.text)
    result = chat.confirm(reply.pending_id, approved, db=db)
    return chat.Reply(result.text, pending_id=None, needs_buttons=False)


def _classify_route(text: str, *, allow_recall: bool) -> str:
    """由確定性前綴推 route(不落地、零 LLM)。與 chat 分派同一套規則。"""
    stripped = text.strip()
    if not stripped:
        return "empty"
    low = stripped.lower()
    if any(stripped.startswith(p) for p in chat._KNOWLEDGE_PREFIXES):
        return "recall" if allow_recall else "recall_blocked"
    if low in ("today", "今天", "week", "本週"):
        return "schedule_read"
    if low in ("proj", "專案"):
        return "projects"
    if low == "done" or low.startswith("done "):
        return "task_done"
    if low == "todo" or low.startswith("todo "):
        return "task_add"
    return "schedule"


def _outcome_for(route: str, reply: chat.Reply) -> str:
    """由 route + Reply 形狀推 outcome(不重跑業務邏輯)。"""
    if route == "empty":
        return "not_actionable"
    if reply.needs_buttons:
        return "needs_confirmation"
    if route == "recall_blocked":
        return "no_result"
    if route == "recall":
        # recall 的 found/not_found 由 memory_tools 帶回(裂縫3 契約)
        if reply.outcome == "found":
            return "answered"
        return "no_result"
    if route in ("schedule_read", "projects"):
        return "answered"
    # task_done / task_add / 自然語言 schedule:落地或拒絕由 ✔/✘ 標記判斷
    if reply.text.startswith("✔") or "已完成" in reply.text or "已建立" in reply.text:
        return "applied"
    if reply.text.startswith("✘") or reply.text.startswith("無法") \
            or reply.text.startswith("這不是") or reply.text.startswith("找不到") \
            or reply.text.startswith("解析失敗") or reply.text.startswith("已取消"):
        return "rejected"
    return "answered"


def invoke(text: str, ctx: InvocationContext, *,
           db: Path | None = None, vault: Path | None = None,
           idx_db: Path | None = None, transcript_dir: Path | None = None,
           _api=None) -> InvocationResult:
    """統一入口:一次呼叫 = 記 run → 確定性分派 → 結構化結果 → 死。

    永不拋例外——頂層防線把任何異常化為 rejected 並收尾 run(不卡 running)。
    """
    run_id = _run_start(db, ctx.trigger)
    route = _classify_route(text, allow_recall=ctx.allow_recall)
    try:
        reply = chat.handle_message(
            text, channel_ref=ctx.channel_ref, db=db,
            allow_recall=ctx.allow_recall, _api=_api,
            vault=vault, idx_db=idx_db, transcript_dir=transcript_dir)

        # 同步確認(CLI):有 confirm_fn 且需確認 → 立即 preview→confirm→落地。
        # 重用 pending_claim 原子機制;不留 pending 按鈕,不新增第二個落地路徑。
        if reply.needs_buttons and reply.pending_id is not None \
                and ctx.confirm_fn is not None:
            reply = _sync_confirm(reply, ctx.confirm_fn, db)

        outcome = _outcome_for(route, reply)
        _run_finish(db, run_id, "ok", summary=f"{route}:{outcome}")
        return InvocationResult(
            text=reply.text, route=route, outcome=outcome, run_id=run_id,
            pending_id=reply.pending_id,
            needs_confirmation=reply.needs_buttons)
    except Exception as e:                      # noqa: BLE001 — 頂層防線:run 不卡 running
        _run_finish(db, run_id, "error", error=f"{type(e).__name__}: {e}")
        return InvocationResult(
            text=f"內部錯誤:{type(e).__name__}: {e}", route=route,
            outcome="rejected", run_id=run_id)


# ── agent_runs 記錄(收斂自 agent._run_start/_run_finish)──────────────

def _run_start(db: Path | None, trigger: str) -> int:
    con = stm.connect(db)
    try:
        cur = con.execute(
            "INSERT INTO agent_runs (started_at, trigger) VALUES (?, ?)",
            (stm.now(), trigger))
        con.commit()
        return cur.lastrowid
    finally:
        con.close()


def _run_finish(db: Path | None, run_id: int, status: str,
                summary: str | None = None, error: str | None = None) -> None:
    con = stm.connect(db)
    try:
        con.execute(
            "UPDATE agent_runs SET finished_at = ?, status = ?, summary = ?, error = ? "
            "WHERE id = ?",
            (stm.now(), status, summary, error, run_id))
        con.commit()
    finally:
        con.close()
