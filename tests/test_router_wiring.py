"""part-012-slice-001:router 接線 chat 分派。

Done gate 對應（DESIGN Verification Targets）：
- 「明天」→ 列明天行程（不再是「這不是行程/待辦」）
- knowledge → recall（Discord context 也放行）
- advice / status / smalltalk / unclear 各路徑
- 快徑零 LLM 斷言（today/done N 不觸 router）
- 寫入意圖仍 preview→confirm
- router 失敗 → fallback 排程解析，服務不中斷
"""

import json
from datetime import datetime, timedelta

import pytest

from core import chat, llm, stm

T0 = 1_800_000_000


@pytest.fixture()
def db(tmp_path):
    path = tmp_path / "state.db"
    stm.init(path)
    return path


def _route_api(payload: dict):
    """fake LLM:回 router 分類結果。"""
    return lambda s, u, m, j: json.dumps(payload)


# ── schedule_query:「明天」回明天行程 ────────────────────────────────

def test_tomorrow_query_lists_tomorrow(db):
    tomorrow = datetime.fromtimestamp(stm.now()) + timedelta(days=1)
    t_iso = tomorrow.date().isoformat()
    ts = int(tomorrow.replace(hour=14, minute=0, second=0).timestamp())
    stm.schedule_add(db, "跟阿明開會", ts)
    stm.schedule_add(db, "下下週的事",
                     int((tomorrow + timedelta(days=20)).timestamp()))
    r = chat.handle_message("明天有什麼", db=db, _api=_route_api(
        {"intent": "schedule_query", "argument": "明天",
         "date_range": [t_iso, t_iso]}))
    assert "跟阿明開會" in r.text
    assert "下下週的事" not in r.text            # 時間窗外不出現
    assert "這不是行程" not in r.text            # 舊蠢話不再出現


def test_query_empty_window_friendly(db):
    tomorrow = (datetime.fromtimestamp(stm.now()) + timedelta(days=1)).date().isoformat()
    r = chat.handle_message("明天有什麼", db=db, _api=_route_api(
        {"intent": "schedule_query", "argument": "明天",
         "date_range": [tomorrow, tomorrow]}))
    assert "沒有排" in r.text


# ── knowledge:recall 放行(含 Discord 情境) ──────────────────────────

def test_knowledge_routes_to_recall(db, tmp_path):
    from core import ltm, vindex
    vault = tmp_path / "vault"
    ltm.init_vault(vault)
    idx = tmp_path / "idx.db"
    nid = ltm.write_note(vault, "semantic", title="RAG 做法筆記", body="內文",
                         frontmatter={"source": "manual", "tags": ["misc"],
                                      "summary": "RAG 做法"}, ts=T0)
    vindex.upsert(idx, nid, title="RAG 做法筆記", summary="RAG 做法", tags=["misc"])

    calls = {"n": 0}

    def api(s, u, m, j):
        calls["n"] += 1
        if calls["n"] == 1:                      # 第一次 = router
            return json.dumps({"intent": "knowledge", "argument": "RAG 做法"})
        # 第二次 = recall agent 迴圈:直接回答並引用
        return json.dumps({"tool": "answer", "text": "找到 RAG 做法筆記",
                           "citations": [nid]})
    r = chat.handle_message("我存過哪些 RAG 做法?", db=db, allow_recall=True,
                            _api=api, vault=vault, idx_db=idx)
    assert "RAG" in r.text


def test_knowledge_blocked_when_recall_disabled(db):
    r = chat.handle_message("我存過哪些 RAG?", db=db, allow_recall=False,
                            _api=_route_api({"intent": "knowledge",
                                             "argument": "RAG"}))
    assert "未開放" in r.text


# ── advice / status / smalltalk / unclear ────────────────────────────

def test_advice_intent_lists_pending(db):
    stm.advice_add(db, priority="high", observation="繳房租逾期",
                   suggestion="今天處理", expires_at=stm.now() + 86400)
    r = chat.handle_message("最近有什麼建議", db=db, _api=_route_api(
        {"intent": "advice", "argument": ""}))
    assert "繳房租" in r.text


def test_advice_intent_empty(db):
    r = chat.handle_message("有建議嗎", db=db, _api=_route_api(
        {"intent": "advice", "argument": ""}))
    assert "沒有待處理" in r.text


def test_status_intent(db):
    stm.project_set(db, "my-agent", phase="part-012", next_action="接線")
    r = chat.handle_message("最近怎樣", db=db, _api=_route_api(
        {"intent": "status", "argument": ""}))
    assert "my-agent" in r.text


def test_smalltalk_natural(db):
    stm.schedule_add(db, "開會", stm.now() + 3600)
    r = chat.handle_message("哈囉", db=db, _api=_route_api(
        {"intent": "smalltalk", "argument": "哈囉"}))
    assert "嗨" in r.text and "1 件事" in r.text
    assert r.pending_id is None                  # 閒聊絕不觸發寫入


def test_unclear_asks_with_guess(db):
    r = chat.handle_message("那個弄一下", db=db, _api=_route_api(
        {"intent": "unclear", "argument": "那個弄一下",
         "guess": ["schedule_write", "knowledge"]}))
    assert "排行程" in r.text and "查知識庫" in r.text


def test_unclear_no_guess_gives_examples(db):
    r = chat.handle_message("???", db=db, _api=_route_api(
        {"intent": "unclear", "argument": "???"}))
    assert "明天有什麼" in r.text                # 給例句,不是說明書口吻


# ── 快徑零 LLM ───────────────────────────────────────────────────────

def test_fast_path_today_zero_llm(db):
    called = []

    def spy(s, u, m, j):
        called.append(1)
        return "{}"
    chat.handle_message("今天", db=db, _api=spy)
    assert called == []


def test_fast_path_done_zero_llm(db):
    tid = stm.task_add(db, "t")
    called = []

    def spy(s, u, m, j):
        called.append(1)
        return "{}"
    r = chat.handle_message(f"done {tid}", db=db, _api=spy)
    assert called == [] and "✔" in r.text


# ── 寫入仍走確認 + fallback 不中斷 ───────────────────────────────────

GOOD_SCHEDULE = json.dumps({
    "agent": "schedule", "proposal_type": "schedule_change", "target": "new",
    "payload": {"action": "add", "fields": {"title": "開會", "start_at": T0}},
    "confidence": 0.9, "evidence": ["明天開會"]})


def test_schedule_write_still_needs_confirm(db):
    calls = {"n": 0}

    def api(s, u, m, j):
        calls["n"] += 1
        if calls["n"] == 1:                      # router
            return json.dumps({"intent": "schedule_write",
                               "argument": "明天開會"})
        return GOOD_SCHEDULE                     # schedule 子 agent
    r = chat.handle_message("明天開會", db=db, _api=api)
    assert r.needs_buttons and r.pending_id is not None   # 預覽+確認不變


def test_router_llm_failure_falls_back_to_schedule(db):
    """router 掛掉 → fallback 現行排程解析(服務不中斷,行為=舊水準)。"""
    calls = {"n": 0}

    def api(s, u, m, j):
        calls["n"] += 1
        if calls["n"] == 1:
            raise llm.LLMError("router down")
        return GOOD_SCHEDULE
    r = chat.handle_message("明天開會", db=db, _api=api)
    assert r.needs_buttons                       # 仍走到排程解析出預覽
