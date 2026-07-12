"""part-002-slice-003 驗證:orchestrator 全流程(mock LLM)、無狀態雙呼叫、
B6 白名單、remind job(單次/重複)、agent_runs 稽核。"""

import json

import pytest

from core import agent, stm

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
        return [dict(zip([d[0] for d in con.execute("SELECT * FROM agent_runs").description], r))
                for r in con.execute("SELECT * FROM agent_runs").fetchall()]
    finally:
        con.close()


# ── invoke 全流程 ─────────────────────────────────────────────────────

def test_invoke_add_full_pipeline(db):
    replies = []
    rc = agent.invoke("明天開會", confirm_fn=lambda p: True,
                      reply_fn=replies.append, db=db, _api=fake_api(GOOD))
    assert rc == 0
    assert stm.schedule_list(db)[0]["title"] == "開會"
    assert replies and "✔" in replies[0]
    r = runs(db)[0]
    assert r["status"] == "ok" and r["finished_at"] is not None   # run 不卡 running


def test_invoke_user_declines(db):
    rc = agent.invoke("明天開會", confirm_fn=lambda p: False,
                      reply_fn=lambda s: None, db=db, _api=fake_api(GOOD))
    assert rc == 1 and stm.schedule_list(db) == []


def test_invoke_not_actionable(db):
    rc = agent.invoke("今天天氣如何", confirm_fn=lambda p: True, reply_fn=lambda s: None,
                      db=db, _api=fake_api('{"error": "不是行程"}'))
    assert rc == 1 and runs(db)[0]["status"] == "ok"


def test_invoke_llm_failure_finishes_run_as_error(db):
    def boom(system, user, model, json_mode):
        raise ConnectionError("down")
    rc = agent.invoke("明天開會", confirm_fn=lambda p: True, reply_fn=lambda s: None,
                      db=db, _api=boom)
    assert rc == 2
    r = runs(db)[0]
    assert r["status"] == "error" and r["finished_at"] is not None  # 不卡 running


# ── 無狀態:兩次獨立呼叫僅經 DB1 接續(Phase 2 gate)──────────────────

def test_stateless_two_invocations_share_via_db1_only(db):
    agent.invoke("明天開會", confirm_fn=lambda p: True, reply_fn=lambda s: None,
                 db=db, _api=fake_api(GOOD))
    # 第二次呼叫:LLM 收到的上下文應含第一次寫入的行程(從 DB1 重建,非記憶體)
    seen = {}
    def spy(system, user, model, json_mode):
        seen["user"] = user
        return '{"error": "只是查看"}'
    agent.invoke("我明天有什麼事", confirm_fn=lambda p: True, reply_fn=lambda s: None,
                 db=db, _api=spy)
    assert "開會" in seen["user"]                    # 上下文來自 DB1


# ── B6:done/cancel 白名單 ───────────────────────────────────────────

def test_b6_done_outside_whitelist_rejected(db):
    stm.schedule_add(db, "存在的", 1_800_000_000)     # id=1 在白名單
    inj = json.loads(GOOD)
    inj["target"] = "999"                            # 不在 active 清單
    inj["payload"] = {"action": "done", "fields": {}}
    rc = agent.invoke("注入攻擊", confirm_fn=None, reply_fn=lambda s: None,
                      db=db, _api=fake_api(json.dumps(inj)))
    assert rc == 1
    assert stm.event_query(db, actor="orchestrator")[0]["action"] == "proposal_rejected"


def test_b6_done_inside_whitelist_ok(db):
    rid = stm.schedule_add(db, "要完成的", 1_800_000_000)
    ok = json.loads(GOOD)
    ok["target"] = str(rid)
    ok["payload"] = {"action": "done", "fields": {}}
    rc = agent.invoke("完成", confirm_fn=None, reply_fn=lambda s: None,
                      db=db, _api=fake_api(json.dumps(ok)))
    assert rc == 0
    assert stm.schedule_list(db, include_done=True)[0]["status"] == "done"


# ── remind job ────────────────────────────────────────────────────────

def test_remind_oneoff_notifies_and_marks(db):
    past = stm.now() - 60
    stm.schedule_add(db, "到期會議", past + 30, remind_at=past)
    notes = []
    assert agent.job_remind(db, notify_fn=notes.append) == 0
    assert notes and "到期會議" in notes[0]
    con = stm.connect(db)
    assert con.execute("SELECT reminded_at FROM schedule").fetchone()[0] is not None
    con.close()
    # 再跑一次:不重複提醒(idempotent)
    notes2 = []
    agent.job_remind(db, notify_fn=notes2.append)
    assert notes2 == []


def test_remind_recurring_advances_and_rearms(db):
    past = stm.now() - 60
    stm.schedule_add(db, "站會", past + 30, remind_at=past, rrule="FREQ=DAILY")
    agent.job_remind(db, notify_fn=lambda s: None)
    row = stm.schedule_list(db)[0]
    assert row["start_at"] > stm.now()               # 前推到未來
    assert row["reminded_at"] is None                # 重新武裝,等下一輪
    assert row["status"] == "active"


def test_remind_none_due_is_noop(db):
    stm.schedule_add(db, "未來", stm.now() + 9999, remind_at=stm.now() + 9000)
    notes = []
    assert agent.job_remind(db, notify_fn=notes.append) == 0
    assert notes == []


# ── rrule_next 確定性 ─────────────────────────────────────────────────

def test_rrule_next_daily():
    base = 1_800_000_000
    assert agent.rrule_next("FREQ=DAILY", base) == base + 86_400


def test_rrule_next_weekly_byday():
    from datetime import datetime
    base = 1_800_000_000
    nxt = agent.rrule_next("FREQ=WEEKLY;BYDAY=MO", base)
    assert datetime.fromtimestamp(nxt).weekday() == 0        # 落在週一
    assert 0 < nxt - base <= 7 * 86_400


def test_rrule_next_weekly_same_day_default():
    from datetime import datetime
    base = 1_800_000_000
    nxt = agent.rrule_next("FREQ=WEEKLY", base)
    assert nxt - base == 7 * 86_400
    assert datetime.fromtimestamp(nxt).weekday() == datetime.fromtimestamp(base).weekday()
