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

from core import stm, writer
from core.tools import memory as memory_tools
from core.tools import projects as project_tools
from core.tools import schedule as schedule_tools
from core.tools import tasks as task_tools
from core.tools.contracts import CapabilityContext, CapabilityResult

# 確認逾時(DESIGN §4.4:10 分鐘)
CONFIRM_TTL_SECONDS = 600

# 深度知識查詢關鍵詞 → 拒絕(§4.1 內容分級:知識不經 Discord)
_KNOWLEDGE_PREFIXES = ("查", "search", "recall", "找筆記", "知識")


@dataclass(frozen=True, slots=True)
class Reply:
    text: str
    pending_id: int | None = None    # 非 None → adapter 掛 ✅/❌ 按鈕
    needs_buttons: bool = False
    outcome: str | None = None       # 能力回報的細分結果(recall found/not_found 等)


def _reply(result: CapabilityResult) -> Reply:
    """Convert a channel-neutral capability result into the stable chat API."""
    return Reply(
        result.text,
        pending_id=result.pending_id,
        needs_buttons=result.needs_confirmation,
        outcome=result.outcome,
    )


def handle_message(text: str, *, channel_ref: str | None = None,
                   db: Path | None = None, allow_recall: bool = False,
                   _api=None, vault: Path | None = None,
                   idx_db: Path | None = None,
                   transcript_dir: Path | None = None) -> Reply:
    """階段1:訊息 → 回覆(可能帶待確認 pending_id)。

    allow_recall:本機 CLI/MCP 為 True(知識查詢放行);Discord 為 False
    (內容分級 §4.1——知識不經 Discord;Tailscale MCP 到位後解除)。
    vault/idx_db/transcript_dir:recall 依賴,由介面注入(測試/CLI);None 時
    memory_tools 落回 config 預設。
    """
    stripped = text.strip()
    low = stripped.lower()
    context = CapabilityContext(db=db, channel_ref=channel_ref, api=_api,
                                vault=vault, idx_db=idx_db,
                                transcript_dir=transcript_dir)

    # 空訊息:不打 LLM(audit C7)
    if not stripped:
        return Reply("請輸入指令(today / week / proj / todo <內容> / done <編號> / 或直接說要排的行程)。")

    # 深度知識查詢:本機放行 → recall;Discord 拒絕(內容分級,§4.1)
    if any(stripped.startswith(p) for p in _KNOWLEDGE_PREFIXES):
        if not allow_recall:
            return Reply("知識庫查詢請用本機 CLI(recall);Discord 只處理行程/待辦/提醒。")
        for p in _KNOWLEDGE_PREFIXES:
            if stripped.startswith(p):
                query = stripped[len(p):].strip() or stripped
                break
        return _reply(memory_tools.query(query, context))

    # 確定性前綴分派(零 LLM)——唯讀查詢免確認
    if low in ("today", "今天"):
        return _reply(schedule_tools.today(context))
    if low in ("week", "本週"):
        return _reply(schedule_tools.week(context))
    if low in ("proj", "專案"):
        return _reply(project_tools.status(context))

    # done N:標記完成(免確認,§3.1 規則 7)。'done' 無參數也接住
    if low == "done" or low.startswith("done "):
        return _reply(task_tools.complete(stripped[4:].strip(), context))

    # todo ...:待辦(需確認)。低頭已 strip,故 'todo' + 純空白也要接住
    if low == "todo" or low.startswith("todo "):
        title = stripped[4:].strip()
        if not title:
            return Reply("用法:todo <待辦內容>")
        return _reply(task_tools.add(title, evidence=stripped, context=context))

    # 其餘:自然語言 → schedule 子 agent
    return _reply(schedule_tools.propose(stripped, context))


def confirm(pending_id: int, approve: bool, *, db: Path | None = None) -> Reply:
    """階段2:使用者按 ✅/❌ 後。無狀態——從 DB1 取 pending,重驗後落地。

    裂縫2(part-006-slice-001):以 `pending_claim` 原子認領取代舊的
    「讀 → 檢查 status → apply」。雙擊或跨介面同時確認時,只有認領成功者落地;
    認領失敗者一律回「已處理」,絕不重複落地。
    """
    pending = stm.pending_get(db, pending_id)
    if pending is None:
        return Reply("此確認已失效(找不到),請重發指令。")

    # 原子認領:pending → applying。失敗 = 已被其他確認處理(或非 pending 態)
    if not stm.pending_claim(db, pending_id):
        current = stm.pending_get(db, pending_id)
        status = current["status"] if current else "expired"
        zh = _status_zh("done" if status == "applying" else status)
        return Reply(f"此確認已{zh},請重發指令。")

    if not approve:
        stm.pending_finish(db, pending_id, "cancelled")
        return Reply("已取消。")

    # 重驗後落地(writer.confirm_and_apply 內部重跑 precheck——audit A2'/A3')
    result = writer.confirm_and_apply(pending["proposal"], db)
    stm.pending_finish(db, pending_id, "done" if result.ok else "cancelled")
    return Reply(f"{'✔ 已建立' if result.ok else '✘ ' + result.detail}")


def _status_zh(status: str) -> str:
    return {"done": "完成", "cancelled": "取消", "expired": "逾時失效"}.get(status, status)


def expire_pending(db: Path | None = None, now_ts: int | None = None) -> int:
    """逾時清理(併入 remind job)。回傳清理數。"""
    ids = stm.pending_expire_due(db, CONFIRM_TTL_SECONDS, now_ts=now_ts)
    for pid in ids:
        stm.event_append(db, "chat", "state_change", f"pending #{pid} expired")
    return len(ids)
