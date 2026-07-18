"""part-009-slice-001:reflect + advice 生成 + 四重防疲勞。

Done gate 對應:
- quiet tick 零 LLM 呼叫
- reflect 產合格 advice(observation/suggestion/evidence_ids/expires_at/priority)
- 驗證五類拒絕
- 配額/去重/過期
- reflect 失敗 → baseline 不推進
"""

import json
from datetime import datetime

import pytest

import config
from core import advisor, llm, stm

DAY = 86_400
T0 = 1_800_000_000


@pytest.fixture()
def db(tmp_path):
    path = tmp_path / "state.db"
    stm.init(path)
    return path


def _api_advices(advices):
    """fake LLM:回固定 advices。記錄呼叫次數。"""
    calls = {"n": 0}

    def fake(system, user, model, json_mode):
        calls["n"] += 1
        return json.dumps({"advices": advices})
    fake.calls = calls
    return fake


def _overdue(db, title="繳房租"):
    return stm.task_add(db, title, due_at=T0 - DAY)


# ── quiet tick 零 LLM ────────────────────────────────────────────────

def test_quiet_tick_no_llm_call(db):
    api = _api_advices([])
    stats = advisor.tick(db, now_ts=T0, _api=api)
    assert stats["quiet"] is True
    assert api.calls["n"] == 0                      # reflect 未呼叫
    assert advisor.get_baseline(db) == T0           # baseline 推進


def test_reflect_short_circuits_on_quiet(db):
    api = _api_advices([{"priority": "high", "observation": "x", "suggestion": "y",
                         "evidence_ids": [], "dedup_key": "k", "ttl_days": 1}])
    from core.advisor import WorldDiff
    quiet = WorldDiff(since_ts=0, now_ts=T0)
    assert quiet.quiet
    assert advisor.reflect(quiet, db, _api=api) == []
    assert api.calls["n"] == 0


# ── reflect 產 advice ────────────────────────────────────────────────

def test_reflect_produces_valid_advice(db):
    tid = _overdue(db)
    api = _api_advices([{
        "priority": "high", "observation": "待辦逾期",
        "suggestion": "今天處理", "evidence_ids": [f"task:{tid}"],
        "dedup_key": "overdue", "ttl_days": 2}])
    stats = advisor.tick(db, now_ts=T0, _api=api)
    assert api.calls["n"] == 1
    assert stats["advices_created"] == 1
    row = stm.advice_list(db)[0]
    assert row["priority"] == "high"
    assert row["expires_at"] == T0 + 2 * DAY
    assert json.loads(row["evidence_ids"]) == [f"task:{tid}"]


def test_advice_empty_evidence_allowed(db):
    """作息偏離類:evidence_ids 可為空。"""
    stm.facet_insert(db, "routine", "active_bucket", "morning", seen_at=T0)
    advisor.advance_baseline(db, T0)
    night = int(datetime(2027, 2, 1, 2).timestamp())  # 本地 02:00 = night 桶,> T0
    con = stm.connect(db)
    for _ in range(2):
        con.execute("INSERT INTO events (ts, actor, action, summary, created_at) "
                    "VALUES (?, 'user', 'completed', 'w', ?)", (night, night))
    con.commit()
    con.close()
    api = _api_advices([{"priority": "medium", "observation": "作息偏離",
                         "suggestion": "上午別排重任務", "evidence_ids": [],
                         "dedup_key": "late_night", "ttl_days": 3}])
    stats = advisor.tick(db, now_ts=night + DAY, _api=api)
    assert stats["advices_created"] == 1


# ── 驗證五類拒絕 ─────────────────────────────────────────────────────

def test_validation_rejections(db):
    valid = {"task:1"}
    cases = [
        {"priority": "urgent", "observation": "o", "suggestion": "s",
         "evidence_ids": [], "dedup_key": "k", "ttl_days": 1},        # 非法 priority
        {"priority": "low", "observation": " ", "suggestion": "s",
         "evidence_ids": [], "dedup_key": "k", "ttl_days": 1},        # 空 observation
        {"priority": "low", "observation": "o", "suggestion": "s",
         "evidence_ids": ["task:999"], "dedup_key": "k", "ttl_days": 1},  # 偽 evidence
        {"priority": "low", "observation": "o", "suggestion": "s",
         "evidence_ids": [], "dedup_key": "k", "ttl_days": 99},       # ttl 超界
        {"priority": "low", "observation": "o", "suggestion": "s",
         "evidence_ids": [], "dedup_key": "", "ttl_days": 1},         # 空 dedup_key
    ]
    for raw in cases:
        assert advisor._validate_advice(raw, valid) is not None


def test_reflect_drops_invalid_keeps_valid(db):
    tid = _overdue(db)
    api = _api_advices([
        {"priority": "high", "observation": "好建議", "suggestion": "做這個",
         "evidence_ids": [f"task:{tid}"], "dedup_key": "ok", "ttl_days": 2},
        {"priority": "bogus", "observation": "壞", "suggestion": "s",
         "evidence_ids": [], "dedup_key": "bad", "ttl_days": 1},
    ])
    stats = advisor.tick(db, now_ts=T0, _api=api)
    assert stats["advices_created"] == 1            # 只留合格的
    rej = [e for e in stm.event_query(db, actor="advisor")
           if e["action"] == "proposal_rejected"]
    assert any("illegal priority" in e["summary"] for e in rej)


# ── 四重防疲勞 ───────────────────────────────────────────────────────

def test_daily_quota(db):
    # 產超過配額的候選 → 只落地配額數
    for i in range(config.ADVICE_DAILY_QUOTA + 2):
        stm.task_add(db, f"逾期{i}", due_at=T0 - DAY)
    tasks = stm.task_list(db)
    advices = [{"priority": "medium", "observation": f"逾期 {t['id']}",
                "suggestion": "處理", "evidence_ids": [f"task:{t['id']}"],
                "dedup_key": f"od_{t['id']}", "ttl_days": 2} for t in tasks]
    api = _api_advices(advices)
    stats = advisor.tick(db, now_ts=T0, _api=api)
    assert stats["advices_created"] == config.ADVICE_DAILY_QUOTA
    assert stats["skipped_quota"] >= 1


def test_dedup_window(db):
    tid = _overdue(db)
    adv = {"priority": "high", "observation": "逾期", "suggestion": "做",
           "evidence_ids": [f"task:{tid}"], "dedup_key": "same_key", "ttl_days": 2}
    advisor.tick(db, now_ts=T0, _api=_api_advices([adv]))
    # 第二次 tick 同 dedup_key(且在窗口內)→ 去重跳過
    stm.task_add(db, "另一逾期", due_at=T0 - DAY)   # 讓 world-diff 非 quiet
    stats = advisor.tick(db, now_ts=T0 + DAY, _api=_api_advices([adv]))
    assert stats["skipped_dedup"] >= 1


def test_expiry_cleared_on_tick(db):
    aid = stm.advice_add(db, priority="low", observation="舊", suggestion="s",
                         expires_at=T0 - DAY)      # 已過期
    _overdue(db)
    advisor.tick(db, now_ts=T0, _api=_api_advices([]))
    assert stm.advice_get(db, aid)["state"] == "expired"


# ── reflect 失敗 baseline 不推進 ─────────────────────────────────────

def test_reflect_failure_does_not_advance_baseline(db):
    advisor.advance_baseline(db, T0 - 10 * DAY)
    _overdue(db)

    def boom(system, user, model, json_mode):
        raise llm.LLMError("simulated failure")
    stats = advisor.tick(db, now_ts=T0, _api=boom)
    assert stats.get("reflect_failed") is True
    assert advisor.get_baseline(db) == T0 - 10 * DAY   # 未推進,下次重看
