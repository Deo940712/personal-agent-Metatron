"""KNOWN_ISSUES.md 修復的 regression tests(重現式逐條轉測試)。

流程教訓落實:每個 validator 配 boundary 測試(空/None/界外/型別偽裝)。
"""

import pytest

from core import llm, stm, writer
from core.llm import LLMError

YES = lambda p: True


@pytest.fixture()
def db(tmp_path):
    path = tmp_path / "state.db"
    stm.init(path)
    return path


def prop(**over):
    base = {
        "agent": "schedule", "proposal_type": "schedule_change", "target": "new",
        "payload": {"action": "add",
                    "fields": {"title": "開會", "start_at": 1_800_000_000}},
        "confidence": 0.9, "evidence": ["原句"],
    }
    base.update(over)
    return base


# ── B1:update 空 fields ─────────────────────────────────────────────

def test_b1_update_empty_fields_rejected_not_crash(db):
    rid = stm.schedule_add(db, "x", 1_800_000_000)
    p = prop(target=str(rid))
    p["payload"] = {"action": "update", "fields": {}}
    r = writer.apply(p, YES, db)                    # 曾 OperationalError crash
    assert r.status == "rejected" and "at least one field" in r.detail


# ── B2:NOT NULL 欄位設 None ─────────────────────────────────────────

@pytest.mark.parametrize("field", ["title", "start_at"])
def test_b2_not_null_field_none_rejected(db, field):
    rid = stm.schedule_add(db, "x", 1_800_000_000)
    p = prop(target=str(rid))
    p["payload"] = {"action": "update", "fields": {field: None}}
    r = writer.apply(p, YES, db)                    # 曾 IntegrityError crash
    assert r.status == "rejected" and "cannot be null" in r.detail


def test_b2_nullable_field_none_is_clear(db):
    """nullable 欄位 None = 清除,合法。"""
    rid = stm.schedule_add(db, "x", 1_800_000_000, remind_at=1_799_000_000)
    p = prop(target=str(rid))
    p["payload"] = {"action": "update", "fields": {"remind_at": None}}
    assert writer.apply(p, YES, db).ok
    assert stm.schedule_list(db)[0]["remind_at"] is None


# ── B3:界外 epoch ───────────────────────────────────────────────────

@pytest.mark.parametrize("bad", [99_999_999_999_999, -1, 0, 946_684_799, 4_102_444_801])
def test_b3_out_of_range_epoch_rejected(db, bad):
    p = prop()
    p["payload"]["fields"]["start_at"] = bad        # 曾 OSError crash 或落庫毒化
    r = writer.apply(p, YES, db)
    assert r.status == "rejected" and "out of range" in r.detail
    assert stm.schedule_list(db) == []


def test_b3_fmt_when_defends_against_poisoned_row(db):
    """雙層防禦第二層:即使壞值已落庫,list 顯示不 crash。"""
    con = stm.connect(db)
    con.execute("INSERT INTO schedule (title, start_at, created_at) "
                "VALUES ('bad', 99999999999999, 1)")
    con.commit()
    con.close()
    out = stm.fmt_when(stm.schedule_list(db)[0]["start_at"])   # 曾 OSError
    assert out.startswith("?invalid")


# ── B4:bool 偽裝 int ────────────────────────────────────────────────

@pytest.mark.parametrize("sneaky", [True, False])
def test_b4_bool_epoch_rejected(db, sneaky):
    p = prop()
    p["payload"]["fields"]["start_at"] = sneaky     # 曾靜默落庫為 0/1
    r = writer.apply(p, YES, db)
    assert r.status == "rejected" and "must be int" in r.detail


# ── B5:CLI 壞時間輸入 ───────────────────────────────────────────────

def test_b5_parse_when_friendly_error():
    with pytest.raises(ValueError, match="無法解析時間"):
        stm.parse_when("not-a-date")


def test_b5_cli_bad_date_exit_2(db):
    rc = stm.main(["--db", str(db), "schedule", "add", "x", "--start", "garbage"])
    assert rc == 2                                   # 曾裸 traceback


# ── B8:不可重試錯誤不重試 ───────────────────────────────────────────

def test_b8_4xx_fails_immediately(db):
    class Auth401(Exception):
        status_code = 401
    calls = []
    def api(system, user, model, json_mode):
        calls.append(1)
        raise Auth401("invalid key")
    with pytest.raises(LLMError):
        llm.complete("s", "u", db=db, _api=api)
    assert len(calls) == 1                           # 曾打 2 次


def test_b8_5xx_still_retries(db):
    class Server500(Exception):
        status_code = 500
    calls = []
    def api(system, user, model, json_mode):
        calls.append(1)
        raise Server500("boom")
    with pytest.raises(LLMError):
        llm.complete("s", "u", db=db, _api=api)
    assert len(calls) == 2


def test_b8_connection_error_retries(db):
    calls = []
    def api(system, user, model, json_mode):
        calls.append(1)
        raise ConnectionError("net down")
    with pytest.raises(LLMError):
        llm.complete("s", "u", db=db, _api=api)
    assert len(calls) == 2


# ── B11:events.target 語意 ──────────────────────────────────────────

def test_b11_rejection_event_target_not_polluted(db):
    writer.apply(prop(evidence=[]), YES, db)
    ev = [e for e in stm.event_query(db, actor="writer")
          if e["action"] == "proposal_rejected"][0]
    assert ev["target"] is None                      # 曾塞提案描述字串
