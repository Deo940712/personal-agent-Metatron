"""part-002.5-slice-002:chat.py 兩階段(mock LLM,零 discord)、無狀態重啟、
免確認、拒絕、expire。"""

import json

import pytest

from core import chat, stm

GOOD_SCHEDULE = json.dumps({
    "agent": "schedule", "proposal_type": "schedule_change", "target": "new",
    "payload": {"action": "add", "fields": {"title": "開會", "start_at": 1_800_000_000}},
    "confidence": 0.95, "evidence": ["明天開會"]})


@pytest.fixture()
def db(tmp_path):
    path = tmp_path / "state.db"
    stm.init(path)
    return path


def api(text):
    return lambda s, u, m, j: text


# ── 階段1 → pending → 階段2 ─────────────────────────────────────────

def test_schedule_two_stage_approve(db):
    r1 = chat.handle_message("明天開會", channel_ref="user:1", db=db,
                             _api=api(GOOD_SCHEDULE))
    assert r1.needs_buttons and r1.pending_id is not None
    assert stm.schedule_list(db) == []                      # 尚未落地

    r2 = chat.confirm(r1.pending_id, approve=True, db=db)
    assert "已建立" in r2.text
    assert stm.schedule_list(db)[0]["title"] == "開會"       # 確認後落地


def test_schedule_two_stage_reject(db):
    r1 = chat.handle_message("明天開會", db=db, _api=api(GOOD_SCHEDULE))
    r2 = chat.confirm(r1.pending_id, approve=False, db=db)
    assert "取消" in r2.text and stm.schedule_list(db) == []


def test_confirm_survives_bot_restart(db):
    """無狀態:handle_message 與 confirm 之間 chat 模組無共享狀態,只經 DB1。"""
    r1 = chat.handle_message("明天開會", db=db, _api=api(GOOD_SCHEDULE))
    pid = r1.pending_id
    # 模擬 bot 重啟:重新 import(狀態不在記憶體)
    import importlib
    from core import chat as chat_reloaded
    importlib.reload(chat_reloaded)
    r2 = chat_reloaded.confirm(pid, approve=True, db=db)
    assert "已建立" in r2.text
    assert stm.schedule_list(db)[0]["title"] == "開會"


def test_confirm_missing_pending(db):
    assert "失效" in chat.confirm(999, approve=True, db=db).text


def test_confirm_already_done_pending(db):
    r1 = chat.handle_message("明天開會", db=db, _api=api(GOOD_SCHEDULE))
    chat.confirm(r1.pending_id, approve=True, db=db)         # 第一次確認
    r3 = chat.confirm(r1.pending_id, approve=True, db=db)    # 重複確認
    assert "完成" in r3.text                                 # 不重複落地
    assert len(stm.schedule_list(db)) == 1


# ── 免確認路徑(查詢/done)────────────────────────────────────────────

def test_today_readonly_no_pending(db):
    stm.schedule_add(db, "既有會議", 1_800_000_000)
    r = chat.handle_message("today", db=db)
    assert "既有會議" in r.text and r.pending_id is None


def test_week_and_proj(db):
    stm.schedule_add(db, "週會", 1_800_000_000)
    stm.project_set(db, "my-agent", phase="p3")
    assert "週會" in chat.handle_message("week", db=db).text
    assert "my-agent" in chat.handle_message("proj", db=db).text


def test_done_no_confirm(db):
    tid = stm.task_add(db, "買貓砂")
    r = chat.handle_message(f"done {tid}", db=db)
    assert "✔" in r.text and r.pending_id is None
    assert stm.task_list(db) == []                          # 已完成


def test_done_bad_arg(db):
    assert "用法" in chat.handle_message("done abc", db=db).text


def test_done_nonexistent(db):
    assert "找不到" in chat.handle_message("done 999", db=db).text


def test_todo_needs_confirm(db):
    r1 = chat.handle_message("todo 買貓砂", db=db)
    assert r1.needs_buttons and stm.task_list(db) == []
    chat.confirm(r1.pending_id, approve=True, db=db)
    assert stm.task_list(db)[0]["title"] == "買貓砂"


def test_todo_empty(db):
    assert "用法" in chat.handle_message("todo   ", db=db).text


# ── 內容分級:知識查詢拒絕(§4.1)──────────────────────────────────

@pytest.mark.parametrize("q", ["查 RAG 筆記", "recall 向量索引", "找筆記 sqlite"])
def test_knowledge_query_rejected(db, q):
    r = chat.handle_message(q, db=db)
    assert "本機 CLI" in r.text and r.pending_id is None


# ── LLM 判定非行程 ───────────────────────────────────────────────────

def test_not_actionable(db):
    r = chat.handle_message("今天天氣如何", db=db,
                            _api=api('{"error": "不是行程"}'))
    assert "不是行程" in r.text and r.pending_id is None


def test_llm_failure(db):
    def boom(s, u, m, j):
        raise ConnectionError("down")
    r = chat.handle_message("明天開會", db=db, _api=boom)
    assert "解析失敗" in r.text


# ── audit gate (slice-002) regression ────────────────────────────────

def test_c7_empty_message_no_llm(db):
    """audit C7:純空白訊息 → 曾落到 LLM 白打 API。"""
    called = []
    def spy(s, u, m, j):
        called.append(1)
        return GOOD_SCHEDULE
    r = chat.handle_message("   ", db=db, _api=spy)
    assert called == [] and "請輸入指令" in r.text


def test_c1_uppercase_prefix_dispatch(db):
    """audit C1:大小寫混合前綴分派一致。"""
    tid = stm.task_add(db, "t")
    assert "✔" in chat.handle_message(f"DONE {tid}", db=db).text
    stm.schedule_add(db, "會議", 1_800_000_000)
    assert "會議" in chat.handle_message("Today", db=db).text


def test_c6_channel_ref_persisted(db):
    """audit C6:channel_ref 存進 pending 供 adapter 回覆定址。"""
    r = chat.handle_message("明天開會", channel_ref="user:999", db=db,
                            _api=api(GOOD_SCHEDULE))
    assert stm.pending_get(db, r.pending_id)["channel_ref"] == "user:999"


# ── expire ───────────────────────────────────────────────────────────

def test_expire_pending(db):
    r1 = chat.handle_message("明天開會", db=db, _api=api(GOOD_SCHEDULE))
    now = stm.now()
    con = stm.connect(db)
    con.execute("UPDATE pending_proposals SET created_at = ? WHERE id = ?",
                (now - chat.CONFIRM_TTL_SECONDS - 1, r1.pending_id))
    con.commit()
    con.close()
    assert chat.expire_pending(db, now_ts=now) == 1
    # 逾時後確認 → 失效訊息
    assert "逾時" in chat.confirm(r1.pending_id, approve=True, db=db).text
