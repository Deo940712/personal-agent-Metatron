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
from core.tools import note as note_tools
from core.tools import projects as project_tools
from core.tools import schedule as schedule_tools
from core.tools import tasks as task_tools
from core.tools.contracts import CapabilityContext, CapabilityResult

# 確認逾時(DESIGN §4.4:10 分鐘)
CONFIRM_TTL_SECONDS = 600

# 明確知識查詢快徑前綴(直達 recall)。part-013:移除過廣的「知識」——
# 「知識庫列表」「知識庫有什麼」該由 router 分成 knowledge_list,不能被快徑吃掉。
_KNOWLEDGE_PREFIXES = ("查 ", "search ", "recall ", "找筆記")


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
                   db: Path | None = None, allow_recall: bool = True,
                   _api=None, vault: Path | None = None,
                   idx_db: Path | None = None,
                   transcript_dir: Path | None = None) -> Reply:
    """階段1:訊息 → 回覆(可能帶待確認 pending_id)。

    part-012:快徑(精確指令,零 LLM)未命中 → router 意圖分類 → 七 intent 分派。
    allow_recall 預設 True(舊「知識不經 Discord」內容分級決策已過時——
    Tailscale/內網反代到位;INTERFACES §4.1 已標註)。
    vault/idx_db/transcript_dir:recall 依賴,由介面注入;None 落回 config 預設。
    """
    stripped = text.strip()
    low = stripped.lower()
    context = CapabilityContext(db=db, channel_ref=channel_ref, api=_api,
                                vault=vault, idx_db=idx_db,
                                transcript_dir=transcript_dir)

    # 空訊息:不打 LLM(audit C7)
    if not stripped:
        return Reply("想排行程、查行程、還是查知識庫?直接說就可以。")

    # ── 快徑:精確指令,零 LLM(高頻操作不變貴)──────────────────────
    if any(stripped.startswith(p) for p in _KNOWLEDGE_PREFIXES):
        if not allow_recall:
            return Reply("知識庫查詢在此介面未開放。")
        for p in _KNOWLEDGE_PREFIXES:
            if stripped.startswith(p):
                query = stripped[len(p):].strip() or stripped
                break
        return _reply(memory_tools.query(query, context))

    # 三層下鑽快徑(part-015):看筆記 <id> = L3;看 <tag> = L2。零 LLM。
    # 「看筆記」須先於「看」判斷(前綴重疊)。
    if stripped.startswith("看筆記 ") or stripped.startswith("看筆記"):
        note_id = stripped[len("看筆記"):].strip()
        if not note_id:
            return Reply("用法:看筆記 <id>(id 從「看 <主題>」的清單取得)")
        return _reply(memory_tools.open_note(note_id, context))
    if stripped.startswith("看 "):
        tag = stripped[2:].strip()
        if tag:
            return _reply(memory_tools.browse_topic(tag, context))

    # 知識庫 CRUD 快徑(part-015):明確指令,零 LLM,走 writer 確認。
    if stripped.startswith("新增筆記"):
        return _reply(note_tools.create(stripped[len("新增筆記"):].strip(), context))
    if stripped.startswith("改筆記"):
        return _reply(note_tools.edit(stripped[len("改筆記"):].strip(), context))
    if stripped.startswith("刪筆記"):
        return _reply(note_tools.delete(stripped[len("刪筆記"):].strip(), context))

    if low in ("today", "今天"):
        return _reply(schedule_tools.today(context))
    if low in ("week", "本週"):
        return _reply(schedule_tools.week(context))
    if low in ("proj", "專案"):
        return _reply(project_tools.status(context))
    if low == "done" or low.startswith("done "):
        return _reply(task_tools.complete(stripped[4:].strip(), context))
    if low == "todo" or low.startswith("todo "):
        title = stripped[4:].strip()
        if not title:
            return Reply("用法:todo <待辦內容>")
        return _reply(task_tools.add(title, evidence=stripped, context=context))

    # ── 慢徑:router 意圖分類(單次 cheap LLM)→ 分派 ─────────────────
    return _dispatch_routed(stripped, context, allow_recall=allow_recall)


def _dispatch_routed(text: str, context: CapabilityContext, *,
                     allow_recall: bool) -> Reply:
    """part-012:router 分類 → 七 intent 分派。fallback → 現行排程解析。"""
    from core import router as router_mod

    route = router_mod.classify(text, context.db, _api=context.api)

    if route.intent == "schedule_query" and route.date_range:
        start, end = route.date_range
        return _reply(schedule_tools.range_view(start, end,
                                                route.argument, context))

    if route.intent == "knowledge":
        if not allow_recall:
            return Reply("知識庫查詢在此介面未開放。")
        return _reply(memory_tools.query(route.argument or text, context))

    if route.intent == "knowledge_list":
        return _reply(memory_tools.list_knowledge(context))

    if route.intent == "note_create":
        text_arg = route.argument.strip() or text
        return _reply(note_tools.create_from_text(text_arg, context))

    if route.intent == "note_delete":
        nid = route.argument.strip()
        if not nid:
            return Reply("要刪哪一篇?給 note id(用「看 <主題>」可查到 id)。")
        return _reply(note_tools.delete(nid, context))

    if route.intent == "note_edit":
        # 自然語修改需帶 id 與新內容;引導到明確指令(避免 LLM 誤拆改錯篇)
        return Reply("修改筆記請用:改筆記 <id> 新標題 | 新內容 | 主題。"
                     "id 可用「看 <主題>」查到。")

    if route.intent == "directive":
        instruction = route.argument.strip()     # 只用 router 抽出的指令內容
        if not instruction:
            return Reply("要留什麼開發指令?說一下內容我幫你記給下次 session。")
        # 留給註冊專案首個;無則 'general'。directive 無副作用(只入佇列),免確認。
        projects = stm.project_show(context.db)
        project = projects[0]["name"] if projects else "general"
        stm.directive_add(context.db, project, instruction)
        return Reply(f"已記下開發指令(專案 {project}):{instruction}\n"
                     f"下次 session 開場會讀到。")

    if route.intent == "advice":
        return Reply(_advices_digest(context.db))

    if route.intent == "status":
        proj = project_tools.status(context)
        return Reply(f"{proj.text}\n---\n{_advices_digest(context.db)}")

    if route.intent == "smalltalk":
        n = len(stm.schedule_list(context.db))
        today_hint = f"今天有 {n} 件事排著。" if n else "今天目前沒排東西。"
        return Reply(f"嗨!{today_hint} 想排行程、查行程或查知識庫,直接說就行。")

    if route.intent == "unclear":
        guesses = {"schedule_write": "排行程/待辦", "schedule_query": "查行程",
                   "knowledge": "查知識庫", "advice": "看建議", "status": "看近況"}
        opts = [guesses[g] for g in route.guess if g in guesses]
        if opts:
            return Reply(f"我不太確定你的意思——你是想{'還是'.join(opts)}?"
                         f"再說具體一點我就能處理。")
        return Reply("我沒聽懂這句。可以排行程(「明天三點開會」)、查行程"
                     "(「明天有什麼」)、或查知識庫(「我存過哪些…」)。")

    # schedule_write 或 fallback(router 失敗)→ 現行排程解析(降級不斷服務)
    return _reply(schedule_tools.propose(text, context))


def _advices_digest(db: Path | None) -> str:
    """pending/pushed 的未過期建議摘要(advice/status intent 用)。"""
    rows = [a for a in stm.advice_list(db, now_ts=stm.now())
            if a["state"] in ("pending", "pushed")]
    if not rows:
        return "目前沒有待處理的建議。"
    lines = [f"[{a['priority']}] {a['observation']} → {a['suggestion']}"
             for a in rows[:5]]
    return "建議:\n" + "\n".join(lines)


def confirm(pending_id: int, approve: bool, *, db: Path | None = None,
            vault: Path | None = None, idx_db: Path | None = None) -> Reply:
    """階段2:使用者按 ✅/❌ 後。無狀態——從 DB1 取 pending,重驗後落地。

    裂縫2(part-006-slice-001):以 `pending_claim` 原子認領取代舊的
    「讀 → 檢查 status → apply」。雙擊或跨介面同時確認時,只有認領成功者落地;
    認領失敗者一律回「已處理」,絕不重複落地。
    vault/idx_db:note_write(part-015)落地依賴;None 落回 config(生產)。
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
    result = writer.confirm_and_apply(pending["proposal"], db, vault=vault, idx_db=idx_db)
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
