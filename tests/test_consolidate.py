"""part-003-slice-002:蒸餾管線(mock LLM 全路徑、驗證五條 boundary、
逐組跳過、LLM 失敗不丟資料、--job consolidate 接線)。"""

import json

import pytest

import config
from core import consolidate, health, ltm, stm, transcript

DAY = 86_400


@pytest.fixture()
def env(tmp_path):
    """db + vault + transcript_dir,並塞一顆已到期的 trash event。"""
    db = tmp_path / "state.db"
    stm.init(db)
    vault = tmp_path / "vault"
    tdir = tmp_path / "transcript"

    eid = stm.event_append(db, "user", "decision", "DATA_DIR 定案放本地")
    con = stm.connect(db)
    created = con.execute("SELECT created_at FROM events WHERE id=?", (eid,)).fetchone()[0]
    con.close()

    t_trash = created + 21 * DAY
    health.decay(db, now_ts=t_trash)
    health.to_trash(db, now_ts=t_trash, transcript_dir=tdir)
    now = t_trash + config.TRASH_RETENTION_DAYS * DAY      # 保留期已滿
    return {"db": db, "vault": vault, "tdir": tdir, "eid": eid, "now": now}


def good_llm(eid):
    return lambda s, u, m, j: json.dumps({"groups": [{
        "kind": "episodic", "title": "架構定案", "summary": "定案 DATA_DIR 放本地。",
        "tags": ["daily-log"], "source_event_ids": [eid], "confidence": 0.9}]})


def event_state(db, eid):
    con = stm.connect(db)
    try:
        return con.execute("SELECT state FROM events WHERE id=?", (eid,)).fetchone()[0]
    finally:
        con.close()


# ── 全管線 ────────────────────────────────────────────────────────────

def test_full_pipeline_writes_note_and_archives(env):
    stats = consolidate.run(db=env["db"], vault=env["vault"],
                            transcript_dir=env["tdir"], now_ts=env["now"],
                            _api=good_llm(env["eid"]))
    assert stats["notes_written"] == 1 and stats["archived"] == 1

    entries = ltm.registry_entries(env["vault"])
    assert len(entries) == 1
    note = ltm.read_note(env["vault"], entries[0]["path"])
    assert note["frontmatter"]["source_ids"] == [f"evt:{env['eid']}"]  # 回水指標
    assert event_state(env["db"], env["eid"]) == "archived"

    # 回水閉環:沿 source_ids 讀回原文
    raw, missing = transcript.read_by_ids(env["tdir"], note["frontmatter"]["source_ids"])
    assert missing == [] and "DATA_DIR" in raw[0]["payload"]["summary"]


def test_preference_goes_to_agent_profile(env):
    api = lambda s, u, m, j: json.dumps({"groups": [{
        "kind": "preference", "title": "語言偏好", "summary": "回覆用繁中。",
        "tags": ["preference"], "source_event_ids": [env["eid"]], "confidence": 0.95}]})
    consolidate.run(db=env["db"], vault=env["vault"], transcript_dir=env["tdir"],
                    now_ts=env["now"], _api=api)
    assert ltm.registry_entries(env["vault"])[0]["path"].startswith("agent/profile/")


def test_empty_groups_is_valid_noop(env):
    api = lambda s, u, m, j: '{"groups": []}'
    stats = consolidate.run(db=env["db"], vault=env["vault"],
                            transcript_dir=env["tdir"], now_ts=env["now"], _api=api)
    assert stats["notes_written"] == 0
    assert event_state(env["db"], env["eid"]) == "trash"   # 未涵蓋 → 留 trash


# ── 驗證五條(boundary;KNOWN_ISSUES 教訓:空/None/界外/型別偽裝)──────

def bad_group_api(env, **overrides):
    g = {"kind": "episodic", "title": "t", "summary": "s", "tags": ["daily-log"],
         "source_event_ids": [env["eid"]], "confidence": 0.9}
    g.update(overrides)
    return lambda s, u, m, j: json.dumps({"groups": [g]})


@pytest.mark.parametrize("bad", [
    {"kind": "hallucination"},                              # 1. kind enum
    {"tags": ["not-in-vocab"]},                             # 2. 詞彙表
    {"tags": []},
    {"source_event_ids": [999_999]},                        # 3. 虛構來源
    {"source_event_ids": []},
    {"source_event_ids": [True]},                           # bool 偽裝 int
    {"confidence": 0.5},                                    # 4. 低於門檻
    {"confidence": 1.5},
    {"confidence": True},
    {"summary": ""},                                        # 5. summary
    {"summary": "x" * 501},
    {"title": "  "},
])
def test_validation_rejects_and_keeps_events_in_trash(env, bad):
    stats = consolidate.run(db=env["db"], vault=env["vault"],
                            transcript_dir=env["tdir"], now_ts=env["now"],
                            _api=bad_group_api(env, **bad))
    assert stats["notes_written"] == 0
    assert event_state(env["db"], env["eid"]) == "trash"   # 資料不丟
    rejected = [e for e in stm.event_query(env["db"], actor="consolidator")
                if e["action"] == "proposal_rejected"]
    assert len(rejected) == 1                               # 有記錄


def test_partial_batch_good_group_applies_bad_skipped(env):
    """逐組跳過:同批一好一壞 → 好的落地,壞的記錄。"""
    api = lambda s, u, m, j: json.dumps({"groups": [
        {"kind": "episodic", "title": "好組", "summary": "ok",
         "tags": ["daily-log"], "source_event_ids": [env["eid"]], "confidence": 0.9},
        {"kind": "bogus", "title": "壞組", "summary": "x",
         "tags": ["daily-log"], "source_event_ids": [env["eid"]], "confidence": 0.9}]})
    stats = consolidate.run(db=env["db"], vault=env["vault"],
                            transcript_dir=env["tdir"], now_ts=env["now"], _api=api)
    assert stats["notes_written"] == 1
    assert event_state(env["db"], env["eid"]) == "archived"


# ── LLM 失敗不丟資料 ─────────────────────────────────────────────────

def test_llm_failure_keeps_events_in_trash(env):
    def boom(s, u, m, j):
        raise ConnectionError("down all night")
    stats = consolidate.run(db=env["db"], vault=env["vault"],
                            transcript_dir=env["tdir"], now_ts=env["now"], _api=boom)
    assert stats["batches_failed"] == 1
    assert event_state(env["db"], env["eid"]) == "trash"   # 下輪重試


# ── 分組 ─────────────────────────────────────────────────────────────

def test_group_by_day_splits_oversized(env):
    events = [{"id": i, "ts": 1_752_300_000 + (i % 2) * DAY, "actor": "u",
               "action": "a", "summary": "s"} for i in range(120)]
    groups = consolidate._group_by_day(events)
    assert all(len(g) <= consolidate.MAX_EVENTS_PER_GROUP for g in groups)
    assert sum(len(g) for g in groups) == 120


# ── --job consolidate 接線 ───────────────────────────────────────────

def test_job_consolidate_records_agent_run(env, monkeypatch):
    from core import agent
    monkeypatch.setattr(config, "VAULT_PATH", env["vault"])
    monkeypatch.setattr(config, "TRANSCRIPT_DIR", env["tdir"])
    monkeypatch.setattr(consolidate, "run",
                        lambda **kw: {"trashed": 0, "due": 0, "notes_written": 0,
                                      "archived": 0, "batches_failed": 0})
    rc = agent.job_consolidate(env["db"])
    assert rc == 0
    con = stm.connect(env["db"])
    row = con.execute("SELECT trigger, status FROM agent_runs "
                      "ORDER BY id DESC LIMIT 1").fetchone()
    con.close()
    assert row == ("scheduler", "ok")


# ── audit gate (slice-002) regression ────────────────────────────────

def test_s5_groups_not_list_rejected_no_crash(env):
    """audit S5:LLM 回 groups 非 list → 曾 AttributeError crash。"""
    api = lambda s, u, m, j: '{"groups": "not a list"}'
    stats = consolidate.run(db=env["db"], vault=env["vault"],
                            transcript_dir=env["tdir"], now_ts=env["now"], _api=api)
    assert stats["notes_written"] == 0
    assert event_state(env["db"], env["eid"]) == "trash"    # 資料不丟


def test_s6_group_not_dict_rejected_no_crash(env):
    """audit S6:group 是字串混入 → 曾 AttributeError crash。"""
    api = lambda s, u, m, j: '{"groups": ["just a string"]}'
    stats = consolidate.run(db=env["db"], vault=env["vault"],
                            transcript_dir=env["tdir"], now_ts=env["now"], _api=api)
    assert stats["notes_written"] == 0
    rejected = [e for e in stm.event_query(env["db"], actor="consolidator")
                if e["action"] == "proposal_rejected"]
    assert rejected


def test_s8_illegal_subdir_rejected(env):
    """audit S8:打錯子目錄名 → 曾靜默建野目錄。"""
    with pytest.raises(ValueError, match="illegal subdir"):
        ltm.write_note(env["vault"], "episodi", title="typo", body="x",
                       frontmatter={"source": "c", "tags": ["daily-log"],
                                    "summary": "s"}, ts=1_752_300_000)