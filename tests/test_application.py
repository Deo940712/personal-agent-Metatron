"""part-006-slice-001 裂縫1:統一 invocation 入口。

`core/application.invoke(text, ctx) -> InvocationResult` 收斂 CLI 的 `agent.invoke`
與 Discord 的 `chat.handle_message` 分派邏輯到一處。三介面(CLI / Discord / 未來
MCP)都只呼叫它,回結構化 `InvocationResult`,並且每次呼叫都記 `agent_runs`
——含 Discord(舊路徑 chat.handle_message 不記 run,這是裂縫1 順帶修的)。

無 LLM router:沿用既有確定性前綴分派;無法判定才送 schedule 子 agent。
"""

import json

import pytest

from core import stm
from core.application import InvocationContext, invoke

GOOD = json.dumps({
    "agent": "schedule", "proposal_type": "schedule_change", "target": "new",
    "payload": {"action": "add", "fields": {"title": "開會", "start_at": 1_800_000_000}},
    "confidence": 0.95, "evidence": ["明天開會"]})


@pytest.fixture()
def db(tmp_path):
    path = tmp_path / "state.db"
    stm.init(path)
    return path


def fake_api(text):
    return lambda system, user, model, json_mode: text


def runs(db):
    con = stm.connect(db)
    try:
        cur = con.execute("SELECT * FROM agent_runs")
        return [dict(zip([d[0] for d in cur.description], r)) for r in cur.fetchall()]
    finally:
        con.close()


# ── 每次呼叫都留 agent_runs(含 Discord trigger)──────────────────────

def test_invoke_records_run_cli(db):
    ctx = InvocationContext(trigger="cli")
    res = invoke("today", ctx, db=db)
    assert res.run_id is not None
    r = runs(db)[0]
    assert r["trigger"] == "cli" and r["status"] == "ok" and r["finished_at"] is not None


def test_invoke_records_run_chat_trigger(db):
    """Discord 走 trigger='chat' — 裂縫1:Discord 也要有 run audit。"""
    ctx = InvocationContext(trigger="chat", channel_ref="user:123")
    invoke("today", ctx, db=db)
    r = runs(db)[0]
    assert r["trigger"] == "chat" and r["finished_at"] is not None


# ── 唯讀查詢:answered / no_result,免確認 ────────────────────────────

def test_today_answered(db):
    stm.schedule_add(db, "開會", 1_800_000_000)
    res = invoke("today", InvocationContext(trigger="cli"), db=db)
    assert res.route == "schedule_read" and res.outcome == "answered"
    assert not res.needs_confirmation and res.pending_id is None


def test_empty_message_not_actionable(db):
    res = invoke("   ", InvocationContext(trigger="cli"), db=db)
    assert res.outcome == "not_actionable" and not res.needs_confirmation


# ── 寫入:needs_confirmation → pending_id 回傳(跨介面一致)────────────

def test_schedule_add_needs_confirmation(db):
    ctx = InvocationContext(trigger="chat", channel_ref="user:1")
    res = invoke("明天下午兩點開會", ctx, db=db, _api=fake_api(GOOD))
    assert res.outcome == "needs_confirmation"
    assert res.needs_confirmation and res.pending_id is not None
    # pending 落在 DB1,可被任一介面確認(無狀態跨介面)
    assert stm.pending_get(db, res.pending_id)["status"] == "pending"


def test_todo_add_needs_confirmation(db):
    res = invoke("todo 買貓砂", InvocationContext(trigger="cli"), db=db)
    assert res.outcome == "needs_confirmation" and res.pending_id is not None


# ── done:免確認落地 ─────────────────────────────────────────────────

def test_done_applies_without_confirmation(db):
    tid = stm.task_add(db, "買貓砂")
    res = invoke(f"done {tid}", InvocationContext(trigger="cli"), db=db)
    assert res.outcome == "applied" and not res.needs_confirmation
    assert stm.task_list(db) == []                           # 已完成移出未結清單


# ── recall gating:allow_recall 控制知識查詢是否放行 ──────────────────

def test_recall_blocked_when_not_allowed(db):
    """顯式 allow_recall=False 仍會擋(part-012 後 Discord 預設放行,gate 保留)。"""
    ctx = InvocationContext(trigger="chat", allow_recall=False, channel_ref="u:1")
    res = invoke("查 RAG", ctx, db=db)
    assert res.route == "recall_blocked" and "未開放" in res.text


def test_recall_allowed_local(db, tmp_path):
    """CLI(allow_recall=True):知識查詢放行 → recall。"""
    from core import ltm
    vault = tmp_path / "vault"
    ltm.init_vault(vault)

    def api(s, u, m, j):
        return json.dumps({"tool": "answer", "text": "知識庫中找不到。",
                           "citations": []})
    ctx = InvocationContext(trigger="cli", allow_recall=True)
    res = invoke("查 量子計算", ctx, db=db, vault=vault,
                 idx_db=tmp_path / "index.db", _api=api)
    assert res.route == "recall"
    assert res.outcome in ("answered", "no_result")


# ── 三介面同入口一致:同指令,CLI 與 chat 得到同 outcome ───────────────

def test_three_interfaces_same_dispatch(db):
    stm.schedule_add(db, "開會", 1_800_000_000)
    cli = invoke("today", InvocationContext(trigger="cli"), db=db)
    chat = invoke("today", InvocationContext(trigger="chat", channel_ref="u:1"), db=db)
    assert cli.route == chat.route == "schedule_read"
    assert cli.outcome == chat.outcome == "answered"


# ── 同步 confirm:CLI 走統一入口但立即落地(不留 pending 按鈕)──────────

def test_sync_confirm_approve_lands_immediately(db):
    """CLI:confirm_fn 給 True → 需確認的寫入立即落地,不回 pending_id。"""
    ctx = InvocationContext(trigger="cli", confirm_fn=lambda preview: True)
    res = invoke("明天下午兩點開會", ctx, db=db, _api=fake_api(GOOD))
    assert res.outcome == "applied" and not res.needs_confirmation
    assert res.pending_id is None                            # 同步落地不留待確認
    assert stm.schedule_list(db)[0]["title"] == "開會"


def test_sync_confirm_decline_rejects(db):
    ctx = InvocationContext(trigger="cli", confirm_fn=lambda preview: False)
    res = invoke("明天下午兩點開會", ctx, db=db, _api=fake_api(GOOD))
    assert res.outcome == "rejected" and stm.schedule_list(db) == []


def test_sync_confirm_preview_shown(db):
    seen = []
    ctx = InvocationContext(trigger="cli",
                            confirm_fn=lambda preview: (seen.append(preview), True)[1])
    invoke("明天下午兩點開會", ctx, db=db, _api=fake_api(GOOD))
    assert seen and "開會" in seen[0]                         # preview 有傳給 confirm_fn


def test_sync_todo_add_lands(db):
    """todo(需確認)在同步模式下也立即落地。"""
    ctx = InvocationContext(trigger="cli", confirm_fn=lambda p: True)
    res = invoke("todo 買貓砂", ctx, db=db)
    assert res.outcome == "applied"
    assert stm.task_list(db)[0]["title"] == "買貓砂"


def test_no_confirm_fn_stays_async_pending(db):
    """無 confirm_fn(Discord/MCP):維持 pending 非同步,回 pending_id。"""
    ctx = InvocationContext(trigger="chat", channel_ref="u:1")
    res = invoke("明天下午兩點開會", ctx, db=db, _api=fake_api(GOOD))
    assert res.outcome == "needs_confirmation" and res.pending_id is not None
    assert stm.schedule_list(db) == []                       # 尚未落地


def test_sync_readonly_unaffected_by_confirm_fn(db):
    """唯讀查詢有無 confirm_fn 都一樣(不觸發確認)。"""
    stm.schedule_add(db, "開會", 1_800_000_000)
    ctx = InvocationContext(trigger="cli", confirm_fn=lambda p: True)
    res = invoke("today", ctx, db=db)
    assert res.outcome == "answered" and res.pending_id is None


# ── LLM 壞:run 標 error,不卡 running(頂層防線)─────────────────────

def test_llm_failure_run_error(db):
    def boom(system, user, model, json_mode):
        raise ConnectionError("down")
    res = invoke("明天開會", InvocationContext(trigger="cli"), db=db, _api=boom)
    assert res.outcome in ("rejected", "not_actionable")
    r = runs(db)[0]
    assert r["finished_at"] is not None                      # run 不卡 running
