"""part-011 todo 3-4:routine loop 端到端整合。

鎖定「死程式碼復活」的完整鏈:
  完成 task (writer done) → completed 事件 + transcript
  → consolidate routine producer → routine facet
  → advisor.observe routine_deviation → reflect 產 routine advice

todo 3:advisor routine-deviation 讀真 completed 事件(非 mock)。
todo 4:整條鏈端到端(completed→facet→deviation→advice)。
"""

from datetime import datetime

import json

import pytest

import config
from core import advisor, consolidate, stm, transcript, writer

DAY = 86_400


@pytest.fixture()
def env(tmp_path, monkeypatch):
    db = tmp_path / "state.db"
    stm.init(db)
    tdir = tmp_path / "transcript"
    tdir.mkdir()
    monkeypatch.setattr(config, "TRANSCRIPT_DIR", tdir)
    return {"db": db, "tdir": tdir, "vault": tmp_path / "vault"}


def _done_task(db, title):
    """建 task → 走 writer done 路徑(產生真 completed 事件 + transcript)。"""
    tid = stm.task_add(db, title)
    prop = {"agent": "schedule", "proposal_type": "task_change",
            "target": str(tid), "payload": {"action": "done", "fields": {}},
            "confidence": 1.0, "evidence": ["做完了"]}
    writer.apply(prop, lambda _: True, db)
    return tid


def _retime_completed(db, tdir, when_dt):
    """把最新的 completed 事件 + 其 transcript 挪到指定本地時間(模擬歷史完成)。"""
    ts = int(when_dt.timestamp())
    con = stm.connect(db)
    row = con.execute(
        "SELECT id, source_ids FROM events WHERE action='completed' "
        "ORDER BY id DESC LIMIT 1").fetchone()
    eid, sids_json = row
    con.execute("UPDATE events SET ts = ? WHERE id = ?", (ts, eid))
    con.commit()
    con.close()
    # transcript entry 也重寫時間(read_by_time 用;read_by_ids 不受影響)
    sids = json.loads(sids_json)
    transcript.append(tdir, sids[0] + ":retimed", "event_raw",
                      {"summary": "retimed"}, ts)   # 不改原 entry;source_id 已固定
    return eid


# ── todo 3:advisor 讀真 completed 事件 ─────────────────────────────────

def test_advisor_routine_deviation_from_real_completed_events(env):
    """穩定 morning routine facet + 真 completed 事件落在 night → observe 偵測偏離。"""
    # 建穩定 morning routine facet
    stm.facet_insert(env["db"], "routine", "active_bucket", "morning",
                     confidence=0.9, seen_at=int(datetime(2027, 1, 1).timestamp()))
    baseline = int(datetime(2027, 2, 1).timestamp())
    advisor.advance_baseline(env["db"], baseline)
    # 走 writer done 路徑產真 completed 事件,挪到 baseline 後的 night(02:00)
    for i in range(2):
        _done_task(env["db"], f"深夜活{i}")
        _retime_completed(env["db"], env["tdir"],
                          datetime(2027, 2, 5 + i, 2, 0))
    diff = advisor.observe(env["db"], now_ts=int(datetime(2027, 2, 10).timestamp()))
    assert diff.routine_deviation is not None
    assert diff.routine_deviation["expected_bucket"] == "morning"


# ── todo 4:整條鏈端到端 ────────────────────────────────────────────────

def test_full_routine_loop(env):
    """completed(writer)→ routine facet(consolidate)→ deviation(advisor)→ advice。"""
    base = datetime(2027, 3, 10, 20, 0)        # 本地 20:00 = evening
    # 1) 走 writer done 產真 completed 事件,挪到 evening(4 天)
    for d in range(4):
        _done_task(env["db"], f"晚間活{d}")
        _retime_completed(env["db"], env["tdir"], base.replace(day=10 + d))
    now = int(base.replace(day=15).timestamp())
    # 2) consolidate routine producer → routine facet
    r = consolidate.run_routine_producer(env["db"], env["tdir"], now_ts=now)
    assert r["routine_facet"] is True
    facet = stm.facet_get_active(env["db"], "routine", "active_bucket")
    assert facet["value"] == "evening"

    # 3) 之後在 morning 完成(偏離 evening routine)→ advisor 偵測
    advisor.advance_baseline(env["db"], now)
    for i in range(2):
        _done_task(env["db"], f"早晨活{i}")
        _retime_completed(env["db"], env["tdir"],
                          datetime(2027, 3, 16 + i, 9, 0))   # morning
    diff = advisor.observe(env["db"], now_ts=int(datetime(2027, 3, 20).timestamp()))
    assert diff.routine_deviation is not None
    assert diff.routine_deviation["expected_bucket"] == "evening"

    # 4) reflect(mock LLM)→ routine advice
    api = lambda s, u, m, j: json.dumps({"advices": [{
        "priority": "medium", "observation": "作息偏離平常 evening",
        "suggestion": "回穩作息", "evidence_ids": [],
        "dedup_key": "routine_drift", "ttl_days": 3}]})
    diff2 = advisor.observe(env["db"], now_ts=int(datetime(2027, 3, 20).timestamp()))
    advices = advisor.reflect(diff2, env["db"], _api=api)
    assert any("作息" in a["observation"] for a in advices)


def test_routine_consistent_no_deviation(env):
    """完成都在平常時段(morning)→ 無偏離、無 routine advice。"""
    stm.facet_insert(env["db"], "routine", "active_bucket", "morning",
                     confidence=0.9, seen_at=int(datetime(2027, 4, 1).timestamp()))
    advisor.advance_baseline(env["db"], int(datetime(2027, 4, 1).timestamp()))
    for i in range(3):
        _done_task(env["db"], f"晨活{i}")
        _retime_completed(env["db"], env["tdir"],
                          datetime(2027, 4, 3 + i, 9, 0))    # morning = 平常
    diff = advisor.observe(env["db"], now_ts=int(datetime(2027, 4, 10).timestamp()))
    assert diff.routine_deviation is None
