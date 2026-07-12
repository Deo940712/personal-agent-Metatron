"""part-002-slice-001 驗證:提案驗證七條、閘門三層、confirm 路徑、落地與 events。"""

import pytest

from core import proposals as P
from core import stm, writer

YES = lambda preview: True
NO = lambda preview: False


@pytest.fixture()
def db(tmp_path):
    path = tmp_path / "state.db"
    stm.init(path)
    return path


def prop(**over):
    """合法 schedule add 提案基底。"""
    base = {
        "agent": "schedule",
        "proposal_type": "schedule_change",
        "target": "new",
        "payload": {"action": "add",
                    "fields": {"title": "開會", "start_at": 1_800_000_000}},
        "confidence": 0.9,
        "evidence": ["明天開會"],
    }
    base.update(over)
    return base


def rejected_reasons(db):
    return [e["summary"] for e in stm.event_query(db, actor="writer")
            if e["action"] == "proposal_rejected"]


# ── 信封驗證(§3.1 規則 5)────────────────────────────────────────────

def test_envelope_missing_field_rejected(db):
    bad = prop()
    del bad["confidence"]
    r = writer.apply(bad, YES, db)
    assert not r.ok and "missing" in r.detail


def test_unknown_agent_rejected(db):
    assert not writer.apply(prop(agent="hacker"), YES, db).ok


def test_confidence_out_of_range_rejected(db):
    assert not writer.apply(prop(confidence=1.5), YES, db).ok
    assert not writer.apply(prop(confidence=-0.1), YES, db).ok


def test_unknown_proposal_type_rejected(db):
    assert not writer.apply(prop(proposal_type="drop_table"), YES, db).ok


def test_illegal_action_rejected(db):
    p = prop()
    p["payload"]["action"] = "delete"          # 不在 enum → 物理刪除永不可能(硬底線)
    assert not writer.apply(p, YES, db).ok


def test_unknown_fields_rejected(db):
    p = prop()
    p["payload"]["fields"]["evil_column"] = "x"
    r = writer.apply(p, YES, db)
    assert not r.ok and "unknown fields" in r.detail


def test_bad_rrule_rejected(db):
    p = prop()
    p["payload"]["fields"]["rrule"] = "FREQ=MONTHLY"   # part-002 只支援 DAILY/WEEKLY
    assert not writer.apply(p, YES, db).ok
    p["payload"]["fields"]["rrule"] = "GARBAGE"
    assert not writer.apply(p, YES, db).ok


def test_valid_rrule_accepted(db):
    p = prop()
    p["payload"]["fields"]["rrule"] = "FREQ=WEEKLY;BYDAY=MO"
    assert writer.apply(p, YES, db).ok


# ── 規則 1:target 存在 ───────────────────────────────────────────────

def test_done_on_missing_row_rejected(db):
    p = prop(target="999")
    p["payload"] = {"action": "done", "fields": {}}
    r = writer.apply(p, YES, db)
    assert not r.ok and "not found" in r.detail


def test_update_requires_numeric_target(db):
    p = prop(target="new")
    p["payload"] = {"action": "update", "fields": {"title": "改"}}
    assert not writer.apply(p, YES, db).ok


# ── 規則 3:evidence ─────────────────────────────────────────────────

def test_empty_evidence_rejected(db):
    r = writer.apply(prop(evidence=[]), YES, db)
    assert not r.ok and "evidence" in r.detail


# ── 閘門:確認流(§3.2 第二層 + 規則 7)──────────────────────────────

def test_add_requires_confirm_and_user_declines(db):
    r = writer.apply(prop(), NO, db)
    assert r.status == "needs_confirm_rejected"
    assert stm.schedule_list(db) == []                 # 沒落地


def test_noninteractive_fail_closed(db):
    r = writer.apply(prop(), None, db)                 # scheduler 情境
    assert r.status == "needs_confirm_rejected"
    assert "fail-closed" in r.detail


def test_done_does_not_need_confirm(db):
    rid = stm.schedule_add(db, "x", 1)
    p = prop(target=str(rid))
    p["payload"] = {"action": "done", "fields": {}}
    r = writer.apply(p, None, db)                      # 非互動也能 done
    assert r.ok
    assert stm.schedule_list(db, include_done=True)[0]["status"] == "done"


def test_preview_contains_readable_time(db):
    seen = {}
    def capture(preview):
        seen["p"] = preview
        return True
    writer.apply(prop(), capture, db)
    assert "start_at" in seen["p"] and "20" in seen["p"]   # 格式化年份可見


# ── 落地與 events ─────────────────────────────────────────────────────

def test_add_applies_and_logs_event(db):
    r = writer.apply(prop(), YES, db)
    assert r.ok and r.row_id == 1
    assert stm.schedule_list(db)[0]["title"] == "開會"
    changes = [e for e in stm.event_query(db) if e["action"] == "state_change"]
    assert changes and "schedule add #1" in changes[0]["summary"]


def test_update_changes_only_given_fields(db):
    rid = stm.schedule_add(db, "原標題", 100, remind_at=90)
    p = prop(target=str(rid))
    p["payload"] = {"action": "update", "fields": {"title": "新標題"}}
    assert writer.apply(p, YES, db).ok
    row = stm.schedule_list(db)[0]
    assert row["title"] == "新標題" and row["remind_at"] == 90   # 未給欄位不動


def test_cancel_schedule_and_task(db):
    sid = stm.schedule_add(db, "s", 1)
    tid = stm.task_add(db, "t")
    ps = prop(target=str(sid))
    ps["payload"] = {"action": "cancel", "fields": {}}
    assert writer.apply(ps, YES, db).ok
    pt = prop(target=str(tid), proposal_type="task_change")
    pt["payload"] = {"action": "cancel", "fields": {}}
    assert writer.apply(pt, YES, db).ok
    assert stm.schedule_list(db, include_done=True)[0]["status"] == "cancelled"
    assert stm.task_list(db, status="archived")[0]["id"] == tid  # tasks 無 cancelled → archived


def test_task_add_roundtrip(db):
    p = prop(proposal_type="task_change")
    p["payload"] = {"action": "add", "fields": {"title": "買貓砂", "due_at": 1_800_000_000}}
    r = writer.apply(p, YES, db)
    assert r.ok and stm.task_list(db)[0]["title"] == "買貓砂"


def test_task_fields_do_not_accept_schedule_fields(db):
    p = prop(proposal_type="task_change")
    p["payload"] = {"action": "add", "fields": {"title": "x", "start_at": 1}}
    assert not writer.apply(p, YES, db).ok             # start_at 不在 TASK_FIELDS


def test_every_rejection_is_logged(db):
    writer.apply(prop(agent="hacker"), YES, db)
    writer.apply(prop(evidence=[]), YES, db)
    writer.apply(prop(), None, db)
    assert len(rejected_reasons(db)) == 3              # §3.1 規則 6:拒絕必記 log
