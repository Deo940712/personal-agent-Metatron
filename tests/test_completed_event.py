"""part-011-slice-000 / todo 1:完成 task/schedule 時寫 completed 事件 + 冷儲存。

作息迴圈的訊號源:done → `events(action='completed')` + transcript entry
(evt:<id> 可回水,durable);cancel 不算完成 → 不寫 completed。
"""

import json

import pytest

import config
from core import stm, transcript, writer

T0 = 1_800_000_000


@pytest.fixture()
def env(tmp_path, monkeypatch):
    db = tmp_path / "state.db"
    stm.init(db)
    tdir = tmp_path / "transcript"
    tdir.mkdir()
    monkeypatch.setattr(config, "TRANSCRIPT_DIR", tdir)
    return {"db": db, "tdir": tdir}


def _done_task_proposal(task_id: int):
    return {
        "agent": "schedule", "proposal_type": "task_change",
        "target": str(task_id),
        "payload": {"action": "done", "fields": {}},
        "confidence": 1.0, "evidence": ["使用者說做完了"],
    }


def _completed_events(db):
    return [e for e in stm.event_query(db, actor="user")
            if e["action"] == "completed"]


def test_task_done_writes_completed_event(env):
    tid = stm.task_add(env["db"], "買貓砂")
    res = writer.apply(_done_task_proposal(tid), lambda _: True, env["db"])
    assert res.ok
    completed = _completed_events(env["db"])
    assert len(completed) == 1
    ev = completed[0]
    assert ev["target"] == f"tasks:{tid}"
    assert "買貓砂" in ev["summary"]
    # source_ids 指向冷儲存 evt:<id>
    assert ev["source_ids"] is not None
    source_ids = json.loads(ev["source_ids"])
    assert source_ids == [f"evt:{ev['id']}"]


def test_completed_event_has_transcript_entry(env):
    tid = stm.task_add(env["db"], "繳房租")
    writer.apply(_done_task_proposal(tid), lambda _: True, env["db"])
    ev = _completed_events(env["db"])[0]
    # 冷儲存可回水
    entries, missing = transcript.read_by_ids(env["tdir"], [f"evt:{ev['id']}"])
    assert missing == []
    assert entries[0]["kind"] == "event_raw"
    assert "繳房租" in json.dumps(entries[0]["payload"], ensure_ascii=False)


def test_cancel_does_not_write_completed(env):
    tid = stm.task_add(env["db"], "取消的事")
    prop = _done_task_proposal(tid)
    prop["payload"]["action"] = "cancel"
    writer.apply(prop, lambda _: True, env["db"])
    assert _completed_events(env["db"]) == []


def test_schedule_done_writes_completed(env):
    sid = stm.schedule_add(env["db"], "開會", T0)
    prop = {"agent": "schedule", "proposal_type": "schedule_change",
            "target": str(sid),
            "payload": {"action": "done", "fields": {}},
            "confidence": 1.0, "evidence": ["開完了"]}
    writer.apply(prop, lambda _: True, env["db"])
    completed = _completed_events(env["db"])
    assert len(completed) == 1
    assert completed[0]["target"] == f"schedule:{sid}"


def test_state_change_event_still_written(env):
    """既有 state_change 事件保留(不取代,是額外加 completed)。"""
    tid = stm.task_add(env["db"], "t")
    writer.apply(_done_task_proposal(tid), lambda _: True, env["db"])
    changes = [e for e in stm.event_query(env["db"], actor="writer")
               if e["action"] == "state_change" and e["target"] == f"tasks:{tid}"]
    assert len(changes) == 1
