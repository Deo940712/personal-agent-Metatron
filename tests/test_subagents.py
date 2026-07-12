"""part-002-slice-002 驗證:llm 薄層(mock)、契約載入、schedule 子 agent 解析、
與 writer 的端到端整合(全 mock,無真 LLM)。"""

import json

import pytest

from core import llm, stm, subagents, writer
from core.llm import LLMError


@pytest.fixture()
def db(tmp_path):
    path = tmp_path / "state.db"
    stm.init(path)
    return path


def fake_api(response_text: str | list[str]):
    """回傳 fake _api;list = 依呼叫次序輪流回(測重試)。"""
    queue = [response_text] if isinstance(response_text, str) else list(response_text)
    calls = []

    def _api(system, user, model, json_mode):
        calls.append({"system": system, "user": user, "model": model})
        if not queue:
            raise RuntimeError("no more fake responses")
        return queue.pop(0)

    _api.calls = calls
    return _api


GOOD = json.dumps({
    "agent": "schedule", "proposal_type": "schedule_change", "target": "new",
    "payload": {"action": "add", "fields": {"title": "開會", "start_at": 1_800_000_000}},
    "confidence": 0.95, "evidence": ["明天開會"]})


# ── llm 薄層 ─────────────────────────────────────────────────────────

def test_complete_logs_event(db):
    out = llm.complete("s", "u", db=db, purpose="test", _api=fake_api("hi"))
    assert out == "hi"
    ev = stm.event_query(db, actor="llm")
    assert ev and ev[0]["action"] == "completed" and "purpose=test" in ev[0]["summary"]


def test_complete_retries_once_then_raises(db):
    def boom(system, user, model, json_mode):
        boom.n += 1
        raise ConnectionError("down")
    boom.n = 0
    with pytest.raises(LLMError):
        llm.complete("s", "u", db=db, _api=boom)
    assert boom.n == 2                                       # 首打 + 重試 1
    assert stm.event_query(db, actor="llm")[0]["action"] == "failed"


def test_complete_json_tolerates_fences(db):
    out = llm.complete_json("s", "u", db=db, _api=fake_api(f"```json\n{GOOD}\n```"))
    assert out["agent"] == "schedule"


def test_complete_json_bad_then_good_retries(db):
    api = fake_api(["這不是 JSON", GOOD])
    out = llm.complete_json("s", "u", db=db, _api=api)
    assert out["confidence"] == 0.95
    assert len(api.calls) == 2
    assert "不是合法 JSON" in api.calls[1]["user"]           # 重試帶錯誤提示


def test_complete_json_bad_twice_raises(db):
    with pytest.raises(LLMError):
        llm.complete_json("s", "u", db=db, _api=fake_api(["垃圾", "還是垃圾"]))


def test_parse_json_rejects_non_object():
    with pytest.raises(ValueError):
        llm._parse_json("[1,2,3]")


# ── 契約載入 ─────────────────────────────────────────────────────────

def test_load_contract_schedule():
    prompt = subagents.load_contract("schedule")
    assert "schedule_change" in prompt and "Few-shot" in prompt


def test_load_contract_missing_raises():
    with pytest.raises(subagents.SubagentError):
        subagents.load_contract("nonexistent")


# ── schedule 子 agent ────────────────────────────────────────────────

def test_run_schedule_builds_minimal_context(db):
    api = fake_api(GOOD)
    out = subagents.run_schedule(
        "明天開會", now_epoch=1_783_980_000,
        active_items=[{"id": 1, "title": "舊會", "start_at": 999}],
        db=db, _api=api)
    assert out["proposal_type"] == "schedule_change"
    user = api.calls[0]["user"]
    assert "NOW=" in user and "epoch 1783980000" in user     # 時間基準注入
    assert "#1 舊會" in user                                  # 現有項目注入
    assert user.endswith("明天開會")


def test_run_schedule_backfills_evidence(db):
    no_ev = json.loads(GOOD)
    no_ev["evidence"] = []
    out = subagents.run_schedule("明天開會", db=db, _api=fake_api(json.dumps(no_ev)))
    assert out["evidence"] == ["明天開會"]                    # 防禦性補原句


def test_run_schedule_error_passthrough(db):
    out = subagents.run_schedule(
        "今天天氣如何", db=db, _api=fake_api('{"error": "不是行程或待辦"}'))
    assert "error" in out


# ── 端到端(mock LLM → writer → DB1)─────────────────────────────────

def test_pipeline_parse_confirm_apply(db):
    proposal = subagents.run_schedule("明天開會", db=db, _api=fake_api(GOOD))
    r = writer.apply(proposal, lambda preview: True, db)
    assert r.ok
    assert stm.schedule_list(db)[0]["title"] == "開會"


def test_pipeline_llm_output_fails_writer_validation(db):
    """LLM 產了非法 action → writer 攔截(兩層防禦各自獨立)。"""
    bad = json.loads(GOOD)
    bad["payload"]["action"] = "delete"
    proposal = subagents.run_schedule("刪掉全部", db=db, _api=fake_api(json.dumps(bad)))
    r = writer.apply(proposal, lambda preview: True, db)
    assert not r.ok and stm.schedule_list(db) == []
