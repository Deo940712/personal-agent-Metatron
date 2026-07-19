"""part-009-slice-000:advices 表 + baseline checkpoint + world-diff 讀取器。

Done gate 對應:
- world-diff 確定性重放(有/無變化)
- quiet 判定(無重要變化 → quiet=True)
- baseline 推進/不推進
- advices CRUD + state 機 + expire_due
"""

from datetime import datetime

import sqlite3

import pytest

from core import advisor, stm

DAY = 86_400
T0 = 1_800_000_000


@pytest.fixture()
def db(tmp_path):
    path = tmp_path / "state.db"
    stm.init(path)
    return path


# ── advices CRUD ─────────────────────────────────────────────────────

def test_advice_add_and_get(db):
    aid = stm.advice_add(db, priority="high", observation="連三天凌晨工作",
                         suggestion="明早別排重任務", expires_at=T0 + DAY,
                         evidence_ids=["evt:1", "evt:2"], dedup_key="late-work")
    row = stm.advice_get(db, aid)
    assert row["priority"] == "high"
    assert row["state"] == "pending"
    assert row["dedup_key"] == "late-work"


def test_advice_add_validation(db):
    with pytest.raises(ValueError):
        stm.advice_add(db, priority="urgent", observation="x", suggestion="y",
                       expires_at=T0)
    with pytest.raises(ValueError):
        stm.advice_add(db, priority="low", observation="  ", suggestion="y",
                       expires_at=T0)
    with pytest.raises(ValueError):
        stm.advice_add(db, priority="low", observation="x", suggestion="y",
                       expires_at=True)


def test_advice_state_machine(db):
    aid = stm.advice_add(db, priority="medium", observation="o", suggestion="s",
                         expires_at=T0 + DAY)
    assert stm.advice_set_state(db, aid, "pushed")
    assert stm.advice_set_state(db, aid, "accepted")
    assert stm.advice_get(db, aid)["state"] == "accepted"
    with pytest.raises(ValueError):
        stm.advice_set_state(db, aid, "bogus")


def test_advice_check_constraint(db):
    con = sqlite3.connect(db)
    try:
        with pytest.raises(sqlite3.IntegrityError):
            con.execute("INSERT INTO advices (priority, observation, suggestion, "
                        "expires_at, created_at) VALUES ('bogus','o','s',1,1)")
    finally:
        con.close()


def test_advice_list_excludes_expired_when_now_given(db):
    stm.advice_add(db, priority="low", observation="old", suggestion="s",
                   expires_at=T0)
    stm.advice_add(db, priority="low", observation="live", suggestion="s",
                   expires_at=T0 + 10 * DAY)
    live = stm.advice_list(db, now_ts=T0 + DAY)
    assert len(live) == 1 and live[0]["observation"] == "live"


def test_advice_dedup_and_count(db):
    # created_at 由 stm.now() 決定(真實牆鐘),故用相對 now 的窗口判定
    before = stm.now() - DAY
    stm.advice_add(db, priority="low", observation="o", suggestion="s",
                   expires_at=T0 + DAY, dedup_key="k")
    assert stm.advice_dedup_recent(db, "k", before)               # 窗口涵蓋
    assert not stm.advice_dedup_recent(db, "k", stm.now() + DAY)  # 未來窗口
    assert not stm.advice_dedup_recent(db, "", before)
    assert stm.advice_count_since(db, 0) == 1


def test_advice_expire_due(db):
    a1 = stm.advice_add(db, priority="low", observation="o1", suggestion="s",
                        expires_at=T0)
    a2 = stm.advice_add(db, priority="low", observation="o2", suggestion="s",
                        expires_at=T0 + 10 * DAY)
    n = stm.advice_expire_due(db, T0 + DAY)
    assert n == 1
    assert stm.advice_get(db, a1)["state"] == "expired"
    assert stm.advice_get(db, a2)["state"] == "pending"


def test_cli_advices_list_empty(db, capsys):
    assert stm.main(["--db", str(db), "advices", "list"]) == 0
    assert "(empty)" in capsys.readouterr().out


# ── baseline checkpoint ──────────────────────────────────────────────

def test_baseline_default_zero(db):
    assert advisor.get_baseline(db) == 0


def test_baseline_advance_roundtrip(db):
    advisor.advance_baseline(db, T0)
    assert advisor.get_baseline(db) == T0


def test_baseline_corrupt_falls_back_zero(db):
    stm.cursor_set(db, "advisor", "baseline_ts", "not-a-number")
    assert advisor.get_baseline(db) == 0


# ── world-diff 讀取器(確定性)────────────────────────────────────────

def test_observe_empty_is_quiet(db):
    diff = advisor.observe(db, now_ts=T0)
    assert diff.quiet
    assert diff.as_summary()["quiet"] is True


def test_observe_new_schedule_after_baseline(db):
    advisor.advance_baseline(db, T0)
    # baseline 前的行程不算;之後的算
    con = stm.connect(db)
    con.execute("INSERT INTO schedule (title, start_at, status, created_at) "
                "VALUES ('old', ?, 'active', ?)", (T0 + DAY, T0 - DAY))
    con.execute("INSERT INTO schedule (title, start_at, status, created_at) "
                "VALUES ('new', ?, 'active', ?)", (T0 + 2 * DAY, T0 + 100))
    con.commit()
    con.close()
    diff = advisor.observe(db, now_ts=T0 + DAY)
    assert not diff.quiet
    assert [s["title"] for s in diff.new_schedule] == ["new"]


def test_observe_overdue_tasks(db):
    stm.task_add(db, "late", due_at=T0 - DAY)
    stm.task_add(db, "future", due_at=T0 + DAY)
    done_id = stm.task_add(db, "done-late", due_at=T0 - DAY)
    stm.task_set_status(db, done_id, "done")
    diff = advisor.observe(db, now_ts=T0)
    assert [t["title"] for t in diff.overdue_tasks] == ["late"]


def test_observe_stalled_projects(db):
    stm.project_set(db, "proj-a", phase="p1", blockers=["等 API key"])
    stm.project_set(db, "proj-b", phase="p2")
    diff = advisor.observe(db, now_ts=T0)
    assert [p["name"] for p in diff.stalled_projects] == ["proj-a"]


def test_observe_routine_deviation(db):
    # 穩定 morning routine facet + baseline 後兩筆 night 完成事件 → 偏離
    stm.facet_insert(db, "routine", "active_bucket", "morning",
                     confidence=0.9, seen_at=T0)
    advisor.advance_baseline(db, T0)
    # 本地 02:00(= night 桶)且在 baseline(T0=2027-01-15)之後
    night = int(datetime(2027, 2, 1, 2).timestamp())
    assert night > T0
    con = stm.connect(db)
    for _ in range(2):
        con.execute("INSERT INTO events (ts, actor, action, summary, created_at) "
                    "VALUES (?, 'user', 'completed', 'work', ?)", (night, night))
    con.commit()
    con.close()
    diff = advisor.observe(db, now_ts=night + DAY)
    assert diff.routine_deviation is not None
    assert diff.routine_deviation["expected_bucket"] == "morning"
    assert diff.routine_deviation["off_bucket_count"] == 2


def test_observe_is_deterministic(db):
    stm.task_add(db, "late", due_at=T0 - DAY)
    d1 = advisor.observe(db, now_ts=T0)
    d2 = advisor.observe(db, now_ts=T0)
    assert d1.as_summary() == d2.as_summary()


# ── todo 6:world-diff new_knowledge 訊號(scout untrusted inbox count-only)──

def test_observe_new_knowledge_from_scout_inbox(db, tmp_path, monkeypatch):
    import config
    from core import scout
    from skills.web_fetch import FetchedEntry
    vault = tmp_path / "vault"
    monkeypatch.setattr(config, "SCOUT_ALLOWLIST_DOMAINS", ["arxiv.org"])
    for i in range(2):
        scout.fetch_and_land(
            db, vault, "https://arxiv.org/rss", f"topic{i}",
            lambda url, i=i: [FetchedEntry(url=f"https://arxiv.org/abs/{i}",
                                           title=f"paper{i}", author="a",
                                           body="b", published="")],
            now_ts=T0)
    diff = advisor.observe(db, now_ts=T0, vault=vault)
    assert diff.new_knowledge == 2
    assert diff.quiet is False
    assert diff.as_summary()["new_knowledge"] == 2


def test_observe_new_knowledge_ignores_trusted(db, tmp_path):
    from core import ltm
    vault = tmp_path / "vault"
    ltm.init_vault(vault)
    # 一般(非 external_untrusted)inbox 筆記不算 new_knowledge
    ltm.write_note(vault, "semantic", title="自己的", body="x",
                   frontmatter={"source": "manual", "tags": ["inbox"],
                                "summary": "s"}, ts=T0)
    diff = advisor.observe(db, now_ts=T0, vault=vault)
    assert diff.new_knowledge == 0


def test_observe_no_vault_no_knowledge(db):
    """未給 vault(或 vault 不存在)→ new_knowledge 0,不炸。"""
    diff = advisor.observe(db, now_ts=T0)
    assert diff.new_knowledge == 0
