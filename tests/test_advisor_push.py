"""part-009-slice-002:push + action→confirm + 校準回饋 + job 接線。

Done gate 對應:
- job 接線（--job advise / job_advise）
- push 只取 medium/high pending
- action→confirm 落地（未確認不落地）
- 回饋產 preference facet 證據（走 writer）
- 忽略/接受都記 state + 校準
"""

import json

import pytest

import config
from core import advisor, agent, stm, transcript, writer

DAY = 86_400
T0 = 1_800_000_000


@pytest.fixture()
def env(tmp_path, monkeypatch):
    db = tmp_path / "state.db"
    stm.init(db)
    tdir = tmp_path / "transcript"
    tdir.mkdir()
    monkeypatch.setattr(config, "TRANSCRIPT_DIR", tdir)
    return {"db": db, "tdir": tdir}


def _add_advice(db, *, priority="medium", dedup="k", expires=T0 + 10 * DAY,
                actions=None):
    return stm.advice_add(db, priority=priority, observation="o",
                          suggestion="s", expires_at=expires,
                          dedup_key=dedup, actions=actions)


# ── push 篩選 ────────────────────────────────────────────────────────

def test_push_only_medium_and_high(env):
    _add_advice(env["db"], priority="low", dedup="lo")
    mid = _add_advice(env["db"], priority="medium", dedup="mid")
    hi = _add_advice(env["db"], priority="high", dedup="hi")
    ids = {a["id"] for a in advisor.push_candidates(env["db"], now_ts=T0)}
    assert ids == {mid, hi}


def test_push_excludes_expired_and_nonpending(env):
    old = _add_advice(env["db"], priority="high", dedup="old", expires=T0)
    pushed = _add_advice(env["db"], priority="high", dedup="pushed")
    stm.advice_set_state(env["db"], pushed, "pushed")
    live = _add_advice(env["db"], priority="high", dedup="live")
    ids = {a["id"] for a in advisor.push_candidates(env["db"], now_ts=T0 + DAY)}
    assert ids == {live}


# ── todo 5:降頻——穩定 ignore 的 dedup_key 不再推 ─────────────────────

def _stable_ignore_facet(db, dedup):
    """建一個穩定 ignore 的 advice_pref facet(模擬使用者反覆忽略某類)。"""
    fid = stm.facet_insert(db, "preference", f"advice_pref__{dedup}", "ignore",
                           confidence=0.7)
    stm.facet_promote(db, fid, 0.6)            # → stable
    return fid


def test_push_downthrottles_stable_ignored(env):
    """某 dedup_key 有穩定 ignore facet → 該類 advice 不再推(降頻)。"""
    ignored = _add_advice(env["db"], priority="high", dedup="late_night")
    _stable_ignore_facet(env["db"], "late_night")
    other = _add_advice(env["db"], priority="high", dedup="overdue")
    ids = {a["id"] for a in advisor.push_candidates(env["db"], now_ts=T0)}
    assert other in ids
    assert ignored not in ids                  # 降頻


def test_push_keeps_provisional_ignore(env):
    """僅 provisional ignore(尚未穩定)→ 仍推(保守:多次忽略才降頻)。"""
    adv = _add_advice(env["db"], priority="high", dedup="k")
    stm.facet_insert(env["db"], "preference", "advice_pref__k", "ignore",
                     confidence=0.5)           # provisional,未 promote
    ids = {a["id"] for a in advisor.push_candidates(env["db"], now_ts=T0)}
    assert adv in ids


def test_push_keeps_stable_accept(env):
    """穩定 accept facet → 照常推(降頻只針對 ignore)。"""
    adv = _add_advice(env["db"], priority="high", dedup="useful")
    fid = stm.facet_insert(env["db"], "preference", "advice_pref__useful", "accept",
                           confidence=0.7)
    stm.facet_promote(env["db"], fid, 0.6)
    ids = {a["id"] for a in advisor.push_candidates(env["db"], now_ts=T0)}
    assert adv in ids


# ── job 接線 ─────────────────────────────────────────────────────────

def test_job_advise_pushes_via_notify(env):
    _add_advice(env["db"], priority="high", dedup="hi")
    sent = []
    rc = agent.job_advise(env["db"], notify_fn=sent.append)
    assert rc == 0
    assert len(sent) == 1 and "建議" in sent[0]
    # 推播後標 pushed
    assert stm.advice_list(env["db"], state="pushed")


def test_job_advise_records_agent_run(env):
    agent.job_advise(env["db"], notify_fn=lambda _: None)
    runs = [r for r in stm.event_query(env["db"]) if r]  # 至少不炸
    con = stm.connect(env["db"])
    n = con.execute("SELECT COUNT(*) FROM agent_runs WHERE status='ok'").fetchone()[0]
    con.close()
    assert n >= 1


def test_cli_job_advise(env, capsys):
    _add_advice(env["db"], priority="high", dedup="hi")
    rc = agent.main(["--job", "advise", "--db", str(env["db"])])
    assert rc == 0
    assert "OK" in capsys.readouterr().out


# ── action → confirm ─────────────────────────────────────────────────

def _schedule_action():
    return [{"label": "建立提醒",
             "proposal": {"agent": "schedule", "proposal_type": "schedule_change",
                          "target": "new",
                          "payload": {"action": "add",
                                      "fields": {"title": "上午別排重任務",
                                                 "start_at": T0 + 2 * DAY}},
                          "confidence": 0.8, "evidence": ["advice action"]}}]


def test_action_requires_confirm(env):
    aid = _add_advice(env["db"], priority="high", actions=_schedule_action())
    # 未確認(confirm_fn 回 False)→ 不落地
    res = advisor.apply_action(env["db"], aid, 0, lambda _: False)
    assert not res.ok
    assert stm.schedule_list(env["db"]) == []


def test_action_lands_on_confirm(env):
    aid = _add_advice(env["db"], priority="high", actions=_schedule_action())
    res = advisor.apply_action(env["db"], aid, 0, lambda _: True)
    assert res.ok
    titles = [s["title"] for s in stm.schedule_list(env["db"])]
    assert "上午別排重任務" in titles


def test_action_none_when_no_actions(env):
    aid = _add_advice(env["db"], priority="high")     # 無 actions
    assert advisor.apply_action(env["db"], aid, 0, lambda _: True) is None


def test_action_index_out_of_range(env):
    aid = _add_advice(env["db"], priority="high", actions=_schedule_action())
    assert advisor.apply_action(env["db"], aid, 5, lambda _: True) is None


# ── 校準回饋 ─────────────────────────────────────────────────────────

def test_accept_records_facet_evidence(env):
    aid = _add_advice(env["db"], priority="high", dedup="late_night")
    r = advisor.record_feedback(env["db"], aid, accepted=True)
    assert r["ok"]
    assert stm.advice_get(env["db"], aid)["state"] == "accepted"
    facet = stm.facet_get_active(env["db"], "preference", "advice_pref__late_night")
    assert facet is not None
    assert facet["value"] == "accept"


def test_ignore_records_facet_evidence(env):
    aid = _add_advice(env["db"], priority="high", dedup="late_night")
    r = advisor.record_feedback(env["db"], aid, accepted=False)
    assert r["ok"]
    assert stm.advice_get(env["db"], aid)["state"] == "ignored"
    facet = stm.facet_get_active(env["db"], "preference", "advice_pref__late_night")
    assert facet["value"] == "ignore"


def test_repeated_feedback_reinforces(env):
    """同 dedup_key 多次回饋 → facet reinforce（證據累積），不重複 create。"""
    a1 = _add_advice(env["db"], priority="high", dedup="late_night")
    advisor.record_feedback(env["db"], a1, accepted=False)
    fid = stm.facet_get_active(env["db"], "preference", "advice_pref__late_night")["id"]
    a2 = _add_advice(env["db"], priority="high", dedup="late_night")
    advisor.record_feedback(env["db"], a2, accepted=False)
    row = stm.facet_get(env["db"], fid)
    assert row["evidence_count"] == 2
    assert len([f for f in stm.facet_list(env["db"])
                if f["facet_key"] == "advice_pref__late_night"]) == 1


def test_feedback_missing_advice(env):
    r = advisor.record_feedback(env["db"], 9999, accepted=True)
    assert not r["ok"]


def test_feedback_goes_through_writer(env):
    """校準 facet 走 writer（evidence 存在於 transcript）——不繞過驗證。"""
    aid = _add_advice(env["db"], priority="high", dedup="k")
    advisor.record_feedback(env["db"], aid, accepted=True)
    # facet 的 evidence_ids 指向真實 transcript entry（record_feedback 有寫入）
    facet = stm.facet_get_active(env["db"], "preference", "advice_pref__k")
    eids = json.loads(facet["evidence_ids"])
    _, missing = transcript.read_by_ids(env["tdir"], eids)
    assert missing == []
