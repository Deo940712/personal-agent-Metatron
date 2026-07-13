"""part-003-slice-002:蒸餾管線(mock LLM 全路徑、驗證五條 boundary、
逐組跳過、LLM 失敗不丟資料、--job consolidate 接線)。"""

import json
from pathlib import Path

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


def good_llm(eid, topic="架構設計"):
    return lambda s, u, m, j: json.dumps({"groups": [{
        "kind": "episodic", "title": "架構定案", "topic": topic,
        "summary": "定案 DATA_DIR 放本地。",
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
        "kind": "preference", "title": "語言偏好", "topic": "溝通偏好",
        "summary": "回覆用繁中。",
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
    g = {"kind": "episodic", "title": "t", "topic": "測試主題", "summary": "s",
         "tags": ["daily-log"], "source_event_ids": [env["eid"]], "confidence": 0.9}
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
    {"topic": ""},                                          # 6. topic(backlog-022)
    {"topic": "x" * 31},
    {"topic": None},
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
        {"kind": "episodic", "title": "好組", "topic": "測試", "summary": "ok",
         "tags": ["daily-log"], "source_event_ids": [env["eid"]], "confidence": 0.9},
        {"kind": "bogus", "title": "壞組", "topic": "測試", "summary": "x",
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


# ── part-004.5-slice-001:主題連續性蒸餾(Membox,backlog-022)───────────

def two_day_env(tmp_path):
    """兩天各一顆到期 events,供跨天連結測試。"""
    db = tmp_path / "state.db"
    stm.init(db)
    vault = tmp_path / "vault"
    tdir = tmp_path / "transcript"

    e1 = stm.event_append(db, "user", "decision", "架構定案 day1")
    con = stm.connect(db)
    created = con.execute("SELECT created_at FROM events WHERE id=?", (e1,)).fetchone()[0]
    con.close()

    t1 = created + 21 * DAY
    health.decay(db, now_ts=t1)
    health.to_trash(db, now_ts=t1, transcript_dir=tdir)

    e2 = stm.event_append(db, "user", "decision", "架構定案 day2")
    t2 = t1 + DAY
    health.decay(db, now_ts=t2)
    health.to_trash(db, now_ts=t2, transcript_dir=tdir)

    now = t2 + config.TRASH_RETENTION_DAYS * DAY
    return {"db": db, "vault": vault, "tdir": tdir, "e1": e1, "e2": e2, "now": now}


def topic_llm(events_by_call, topic="架構設計"):
    """依序回傳:每次呼叫對應一個 event 一組。events_by_call = [eid, eid, ...]"""
    calls = []
    for eid in events_by_call:
        calls.append(json.dumps({"groups": [{
            "kind": "episodic", "title": f"day-{eid}", "topic": topic,
            "summary": f"事件 {eid} 摘要", "tags": ["daily-log"],
            "source_event_ids": [eid], "confidence": 0.9}]}))
    queue = list(calls)
    return lambda s, u, m, j: queue.pop(0)


def test_topic_validation_boundary(env):
    """第六條:topic 空/超長/None 被拒。"""
    for bad_topic in ["", "x" * 31, None]:
        api = bad_group_api(env, topic=bad_topic)
        stats = consolidate.run(db=env["db"], vault=env["vault"],
                                transcript_dir=env["tdir"], now_ts=env["now"], _api=api)
        assert stats["notes_written"] == 0


def test_same_topic_links_across_days(tmp_path):
    """兩天蒸餾出同主題筆記 → 自動產生雙向 related 連結。"""
    e = two_day_env(tmp_path)
    api = topic_llm([e["e1"], e["e2"]], topic="架構設計")

    stats1 = consolidate.run(db=e["db"], vault=e["vault"], transcript_dir=e["tdir"],
                             now_ts=e["now"], _api=api)
    # 第一次跑:只涵蓋到期的(e1 到期,e2 可能還沒到期——視 due_for_distill 時序)
    entries = ltm.registry_entries(e["vault"])
    assert stats1["notes_written"] >= 1

    if len(entries) < 2:
        # e2 這次未到期,補一輪(now 再往後推)確保兩篇都蒸餾完
        stats2 = consolidate.run(db=e["db"], vault=e["vault"], transcript_dir=e["tdir"],
                                 now_ts=e["now"] + DAY, _api=api)
        entries = ltm.registry_entries(e["vault"])

    assert len(entries) == 2
    notes = [ltm.read_note(e["vault"], en["path"]) for en in entries]
    ids = [en["id"] for en in entries]
    for note in notes:
        related = note["frontmatter"].get("related", [])
        other_id = [i for i in ids if i != note["frontmatter"]["id"]][0]
        assert other_id in related                          # 雙向連結成立


def test_different_topic_not_linked(tmp_path):
    e = two_day_env(tmp_path)
    calls = [
        json.dumps({"groups": [{"kind": "episodic", "title": "d1", "topic": "架構設計",
                    "summary": "s1", "tags": ["daily-log"], "source_event_ids": [e["e1"]],
                    "confidence": 0.9}]}),
        json.dumps({"groups": [{"kind": "episodic", "title": "d2", "topic": "行程管理",
                    "summary": "s2", "tags": ["daily-log"], "source_event_ids": [e["e2"]],
                    "confidence": 0.9}]}),
    ]
    queue = list(calls)
    api = lambda s, u, m, j: queue.pop(0)

    consolidate.run(db=e["db"], vault=e["vault"], transcript_dir=e["tdir"],
                    now_ts=e["now"], _api=api)
    entries = ltm.registry_entries(e["vault"])
    if len(entries) < 2:
        consolidate.run(db=e["db"], vault=e["vault"], transcript_dir=e["tdir"],
                        now_ts=e["now"] + DAY, _api=api)
        entries = ltm.registry_entries(e["vault"])

    assert len(entries) == 2
    for en in entries:
        note = ltm.read_note(e["vault"], en["path"])
        assert note["frontmatter"].get("related", []) == []  # 不同主題不連結


def test_link_same_topic_direct():
    """_link_same_topic 純函數行為:直接驗證雙向連結與時間窗。"""
    import tempfile
    vault = Path(tempfile.mkdtemp()) / "vault"
    ltm.init_vault(vault)

    old_id = ltm.write_note(vault, "episodic", title="舊筆記", body="x",
                            frontmatter={"source": "consolidation", "period": "2026-06-01",
                                         "topic": "架構設計", "tags": ["daily-log"],
                                         "summary": "s"}, ts=1_748_000_000)
    new_path = "episodic/manual-test.md"
    (vault / "episodic" / "manual-test.md").write_text(
        "---\nid: manual-test\nsource: consolidation\nperiod: 2026-06-15\n"
        "topic: 架構設計\ntags:\n  - daily-log\nsummary: new\n---\n\nbody\n",
        encoding="utf-8")
    from core import ltm as ltm_mod
    ltm_mod._registry_append(vault, "manual-test", "新筆記", new_path, "new")

    linked = consolidate._link_same_topic(vault, "manual-test", new_path,
                                          "架構設計", "2026-06-15", None)
    assert linked == 1
    old_note = ltm.read_note(vault, f"episodic/{old_id}.md")
    assert "manual-test" in old_note["frontmatter"]["related"]
    new_note = ltm.read_note(vault, new_path)
    assert old_id in new_note["frontmatter"]["related"]


def test_link_same_topic_outside_window_not_linked():
    import tempfile
    vault = Path(tempfile.mkdtemp()) / "vault"
    ltm.init_vault(vault)
    old_id = ltm.write_note(vault, "episodic", title="很舊的筆記", body="x",
                            frontmatter={"source": "consolidation", "period": "2026-01-01",
                                         "topic": "架構設計", "tags": ["daily-log"],
                                         "summary": "s"}, ts=1_735_689_600)
    linked = consolidate._link_same_topic(vault, "new-note", "episodic/new-note.md",
                                          "架構設計", "2026-06-15", None)  # >30天差
    assert linked == 0


# ── part-004.5-slice-002:矛盾偵測 + supersede(Mneme,backlog-023)──────

def profile_env(tmp_path):
    """既有一篇 profile 偏好筆記 + 一顆到期 event(偏好改變)。"""
    db = tmp_path / "state.db"
    stm.init(db)
    vault = tmp_path / "vault"
    ltm.init_vault(vault)
    tdir = tmp_path / "transcript"

    old_id = ltm.write_note(vault, "agent/profile", title="回覆語言偏好",
                            body="使用者要求回覆一律使用繁體中文。",
                            frontmatter={"source": "consolidation", "period": "2026-06-01",
                                         "topic": "溝通偏好", "tags": ["preference"],
                                         "summary": "回覆用繁中"}, ts=1_748_000_000)

    eid = stm.event_append(db, "user", "decision", "之後回覆改用英文")
    con = stm.connect(db)
    created = con.execute("SELECT created_at FROM events WHERE id=?", (eid,)).fetchone()[0]
    con.close()
    t = created + 21 * DAY
    health.decay(db, now_ts=t)
    health.to_trash(db, now_ts=t, transcript_dir=tdir)
    now = t + config.TRASH_RETENTION_DAYS * DAY
    return {"db": db, "vault": vault, "tdir": tdir, "eid": eid,
            "old_id": old_id, "now": now}


def supersede_llm(eid, supersedes):
    return lambda s, u, m, j: json.dumps({"groups": [{
        "kind": "preference", "title": "回覆語言偏好(更新)", "topic": "溝通偏好",
        "summary": "使用者更新偏好:回覆改用英文。", "tags": ["preference"],
        "source_event_ids": [eid], "confidence": 0.9, "supersedes": supersedes}]})


def test_supersede_lands_both_sides_kept(tmp_path):
    """Mneme 雙側保留:新筆記帶 supersedes;舊筆記補 superseded_by,不刪。"""
    e = profile_env(tmp_path)
    stats = consolidate.run(db=e["db"], vault=e["vault"], transcript_dir=e["tdir"],
                            now_ts=e["now"], _api=supersede_llm(e["eid"], e["old_id"]))
    assert stats["notes_written"] == 1

    entries = ltm.registry_entries(e["vault"])
    assert len(entries) == 2                                # 兩篇都在(雙側保留)
    new_entry = next(en for en in entries if en["id"] != e["old_id"])
    new_note = ltm.read_note(e["vault"], new_entry["path"])
    assert new_note["frontmatter"]["supersedes"] == e["old_id"]

    old_entry = next(en for en in entries if en["id"] == e["old_id"])
    old_note = ltm.read_note(e["vault"], old_entry["path"])
    assert old_note["frontmatter"]["superseded_by"] == new_entry["id"]
    assert "繁體中文" in old_note["body"]                    # 內容不動


def test_supersede_prompt_includes_existing_profile(tmp_path):
    """漸進揭露:蒸餾 prompt 注入既有 profile 的 INDEX 一行描述。"""
    e = profile_env(tmp_path)
    seen = {}
    def spy(s, u, m, j):
        seen["user"] = u
        return json.dumps({"groups": []})
    consolidate.run(db=e["db"], vault=e["vault"], transcript_dir=e["tdir"],
                    now_ts=e["now"], _api=spy)
    assert "既有偏好清單" in seen["user"]
    assert e["old_id"] in seen["user"]


@pytest.mark.parametrize("bad_target", ["20990101-nonexistent", "", "   "])
def test_supersede_fabricated_target_rejected(tmp_path, bad_target):
    """虛構/空 supersedes → 該組拒絕,event 留 trash。"""
    e = profile_env(tmp_path)
    stats = consolidate.run(db=e["db"], vault=e["vault"], transcript_dir=e["tdir"],
                            now_ts=e["now"], _api=supersede_llm(e["eid"], bad_target))
    assert stats["notes_written"] == 0
    assert len(ltm.registry_entries(e["vault"])) == 1       # 只有原本那篇


def test_supersede_already_superseded_rejected(tmp_path):
    """已被取代的筆記不可再被指(不疊 supersede 舊鏈)。"""
    e = profile_env(tmp_path)
    # 先手動把 old_id 標成已 superseded
    ltm.mark_superseded(e["vault"], e["old_id"], "20260701-some-newer")
    stats = consolidate.run(db=e["db"], vault=e["vault"], transcript_dir=e["tdir"],
                            now_ts=e["now"], _api=supersede_llm(e["eid"], e["old_id"]))
    assert stats["notes_written"] == 0                       # 驗證攔截


def test_mark_superseded_idempotent_guard(tmp_path):
    e = profile_env(tmp_path)
    assert ltm.mark_superseded(e["vault"], e["old_id"], "new-1")
    assert not ltm.mark_superseded(e["vault"], e["old_id"], "new-2")  # 已標記 → False
    note = ltm.read_note(e["vault"], f"agent/profile/{e['old_id']}.md")
    assert note["frontmatter"]["superseded_by"] == "new-1"   # 第一次的不被覆蓋


def test_mark_superseded_unknown_id(tmp_path):
    vault = tmp_path / "v"
    ltm.init_vault(vault)
    assert not ltm.mark_superseded(vault, "20990101-ghost", "new")


def test_u2_episodic_with_supersedes_rejected(tmp_path):
    """audit U2:episodic 帶 supersedes 曾繞過驗證直接 mark → 現在整組拒絕。"""
    e = profile_env(tmp_path)
    api = lambda s, u, m, j: json.dumps({"groups": [{
        "kind": "episodic", "title": "日誌", "topic": "T", "summary": "s",
        "tags": ["daily-log"], "source_event_ids": [e["eid"]], "confidence": 0.9,
        "supersedes": e["old_id"]}]})
    stats = consolidate.run(db=e["db"], vault=e["vault"], transcript_dir=e["tdir"],
                            now_ts=e["now"], _api=api)
    assert stats["notes_written"] == 0                       # 整組拒絕
    old = ltm.read_note(e["vault"], f"agent/profile/{e['old_id']}.md")
    assert "superseded_by" not in old["frontmatter"]         # 舊筆記未被標記