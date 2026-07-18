"""part-007-slice-002:證據抽取 + consolidate 掛鉤 + vault 投影 + recall 可見。

Done gate 對應(DESIGN §Verification Targets):
- routine 抽取確定性重放
- consolidate 掛鉤:preference 帶 facet_key → profile_facet 落地(LLM mock)
- 投影 roundtrip:facets → 筆記 → 刪筆記 → 重投影一致
- recall 查偏好命中投影筆記(INDEX registry 可見)
"""

import json
from datetime import datetime
from pathlib import Path

import pytest

import config
from core import consolidate, facets, health, ltm, stm, transcript

DAY = 86_400
T0 = 1_800_000_000


# ── routine 抽取器(純函數)────────────────────────────────────────────

def _completions(hours_days, key_prefix="evt"):
    """(local_hour, day_index) 序列 → completion 記錄。

    以本地時區建構 epoch(對齊 detector 的 datetime.fromtimestamp 解讀),
    確保測試意圖的「本地時段」與桶判定一致。
    """
    out = []
    base = datetime(2026, 7, 1)  # 本地午夜基準
    for i, (hour, day) in enumerate(hours_days):
        done_at = int(datetime(base.year, base.month, base.day + day,
                               hour).timestamp())
        out.append({"done_at": done_at, "source_id": f"{key_prefix}:{i}"})
    return out


def test_routine_too_few_evidence_returns_none():
    obs = facets.extract_routine(_completions([(9, 0), (9, 1)]))
    assert obs is None


def test_routine_same_day_not_enough_days():
    """夠次數但集中同一天 → 不足(跨天門檻)。"""
    obs = facets.extract_routine(_completions([(9, 0), (10, 0), (11, 0), (9, 0)]))
    assert obs is None


def test_routine_extracts_dominant_bucket():
    obs = facets.extract_routine(_completions([
        (9, 0), (10, 1), (11, 2),      # morning ×3 跨 3 天
        (20, 0),                        # evening ×1
    ]))
    assert obs is not None
    assert obs.facet_key == "active_bucket"
    assert obs.value == "morning"
    assert obs.distinct_days == 3
    assert len(obs.evidence_ids) == 3


def test_routine_is_deterministic():
    data = _completions([(9, 0), (14, 1), (9, 2), (15, 3)])
    assert facets.extract_routine(data) == facets.extract_routine(data)


def test_routine_ignores_malformed():
    bad = [{"done_at": None, "source_id": "evt:1"},
           {"done_at": T0, "source_id": None},
           {"foo": "bar"}]
    good = _completions([(9, 0), (9, 1), (9, 2)])
    assert facets.extract_routine(bad + good) is not None
    assert facets.extract_routine(bad) is None


def test_bucket_boundaries():
    assert facets._bucket_of(5) == "early_morning"
    assert facets._bucket_of(11) == "morning"
    assert facets._bucket_of(12) == "afternoon"
    assert facets._bucket_of(18) == "evening"
    assert facets._bucket_of(23) == "night"
    assert facets._bucket_of(2) == "night"


# ── consolidate 掛鉤(LLM mock)────────────────────────────────────────

@pytest.fixture()
def env(tmp_path):
    db = tmp_path / "state.db"
    stm.init(db)
    vault = tmp_path / "vault"
    tdir = tmp_path / "transcript"
    eid = stm.event_append(db, "user", "decision", "回覆一律用繁中")
    con = stm.connect(db)
    created = con.execute("SELECT created_at FROM events WHERE id=?", (eid,)).fetchone()[0]
    con.close()
    t_trash = created + 21 * DAY
    health.decay(db, now_ts=t_trash)
    health.to_trash(db, now_ts=t_trash, transcript_dir=tdir)
    now = t_trash + config.TRASH_RETENTION_DAYS * DAY
    return {"db": db, "vault": vault, "tdir": tdir, "eid": eid, "now": now}


def _pref_api(eid, *, facet_key=None, facet_class=None, value="回覆用繁中。"):
    group = {"kind": "preference", "title": "語言偏好", "topic": "溝通偏好",
             "summary": value, "tags": ["preference"],
             "source_event_ids": [eid], "confidence": 0.95}
    if facet_key:
        group["facet_key"] = facet_key
    if facet_class:
        group["facet_class"] = facet_class
    return lambda s, u, m, j: json.dumps({"groups": [group]})


def test_preference_without_facet_key_makes_no_facet(env):
    """向後相容:preference 不帶 facet_key → 只寫 vault 筆記,不建 facet。"""
    consolidate.run(db=env["db"], vault=env["vault"], transcript_dir=env["tdir"],
                    now_ts=env["now"], _api=_pref_api(env["eid"]))
    assert stm.facet_list(env["db"]) == []


def test_preference_with_facet_key_creates_facet(env):
    consolidate.run(db=env["db"], vault=env["vault"], transcript_dir=env["tdir"],
                    now_ts=env["now"],
                    _api=_pref_api(env["eid"], facet_key="reply_lang"))
    row = stm.facet_get_active(env["db"], "preference", "reply_lang")
    assert row is not None
    assert row["state"] == "provisional"
    assert json.loads(row["evidence_ids"]) == [f"evt:{env['eid']}"]


def test_facet_class_override(env):
    consolidate.run(db=env["db"], vault=env["vault"], transcript_dir=env["tdir"],
                    now_ts=env["now"],
                    _api=_pref_api(env["eid"], facet_key="active_bucket",
                                   facet_class="routine"))
    assert stm.facet_get_active(env["db"], "routine", "active_bucket") is not None


def test_facet_reinforce_on_repeat(env):
    """同 facet_key 第二輪蒸餾 → reinforce(evidence_count 累積),不重複 create。"""
    api = _pref_api(env["eid"], facet_key="reply_lang")
    consolidate.run(db=env["db"], vault=env["vault"], transcript_dir=env["tdir"],
                    now_ts=env["now"], _api=api)
    fid = stm.facet_get_active(env["db"], "preference", "reply_lang")["id"]
    # 第二顆 event → 第二輪
    eid2 = stm.event_append(env["db"], "user", "decision", "再次確認繁中")
    con = stm.connect(env["db"])
    created = con.execute("SELECT created_at FROM events WHERE id=?", (eid2,)).fetchone()[0]
    con.close()
    t2 = created + 21 * DAY
    health.decay(env["db"], now_ts=t2)
    health.to_trash(env["db"], now_ts=t2, transcript_dir=env["tdir"])
    now2 = t2 + config.TRASH_RETENTION_DAYS * DAY
    consolidate.run(db=env["db"], vault=env["vault"], transcript_dir=env["tdir"],
                    now_ts=now2, _api=_pref_api(eid2, facet_key="reply_lang"))
    row = stm.facet_get(env["db"], fid)
    assert row["evidence_count"] == 2                 # 累積,非新建
    assert len([r for r in stm.facet_list(env["db"])
                if r["facet_key"] == "reply_lang"]) == 1


def test_facet_rejected_on_fabricated_evidence_does_not_crash(env, monkeypatch):
    """facet 的 evidence 不在 transcript → writer 拒絕,但蒸餾筆記照常寫、job 不炸。"""
    # 用空 transcript_dir 讓 evidence 驗證必失敗
    empty_tdir = env["tdir"].parent / "empty_transcript"
    empty_tdir.mkdir()
    stats = consolidate.run(db=env["db"], vault=env["vault"],
                            transcript_dir=empty_tdir, now_ts=env["now"],
                            _api=_pref_api(env["eid"], facet_key="reply_lang"))
    assert stm.facet_list(env["db"]) == []            # facet 未建(evidence 假)
    rej = [e for e in stm.event_query(env["db"], actor="consolidator")
           if e["action"] == "proposal_rejected"]
    assert any("reply_lang" in e["summary"] for e in rej)


# ── vault 投影 ────────────────────────────────────────────────────────

def test_projection_roundtrip(env):
    """facets → 投影筆記 → 刪筆記 → 重投影一致(facets 是真相)。"""
    transcript.append(env["tdir"], "evt:100", "event_raw", {"summary": "x"}, ts=T0)
    fid = stm.facet_insert(env["db"], "preference", "reply_lang", "zh-TW",
                           confidence=0.8, evidence_ids=["evt:100"], seen_at=T0)
    stm.facet_promote(env["db"], fid, 0.6)

    r1 = facets.project_to_vault(env["db"], env["vault"])
    assert r1["projected"] == 1
    entries = [e for e in ltm.registry_entries(env["vault"])
               if e["path"].startswith("agent/profile/")]
    assert len(entries) == 1
    note = ltm.read_note(env["vault"], entries[0]["path"])
    assert note["frontmatter"]["source"] == "agent_knowledge"
    assert note["frontmatter"]["facet_key"] == "reply_lang"
    assert note["frontmatter"]["source_ids"] == ["evt:100"]
    assert "zh-TW" in note["body"]

    # 刪投影筆記,重投影 → 內容一致(facets 未變)
    (env["vault"] / entries[0]["path"]).unlink()
    facets.project_to_vault(env["db"], env["vault"])
    live = [e for e in ltm.registry_entries(env["vault"])
            if e["path"].startswith("agent/profile/")
            and (env["vault"] / e["path"]).exists()]
    note2 = ltm.read_note(env["vault"], live[-1]["path"])
    assert note2["frontmatter"]["facet_key"] == "reply_lang"
    assert "zh-TW" in note2["body"]


def test_projection_skips_low_confidence(env):
    stm.facet_insert(env["db"], "preference", "k", "v", confidence=0.2, seen_at=T0)
    r = facets.project_to_vault(env["db"], env["vault"], min_confidence=0.5)
    assert r["projected"] == 0 and r["skipped_low_confidence"] == 1


def test_projection_reproject_supersedes_old(env):
    """同 facet 值變更後重投影 → 舊投影筆記標 superseded(不刪)。"""
    transcript.append(env["tdir"], "evt:1", "event_raw", {"summary": "x"}, ts=T0)
    fid = stm.facet_insert(env["db"], "preference", "reply_lang", "zh-TW",
                           confidence=0.8, evidence_ids=["evt:1"], seen_at=T0)
    facets.project_to_vault(env["db"], env["vault"])
    # 改值(直接改 DB 模擬 supersede 後的新 active)
    con = stm.connect(env["db"])
    con.execute("UPDATE profile_facets SET value = 'en-US' WHERE id = ?", (fid,))
    con.commit()
    con.close()
    facets.project_to_vault(env["db"], env["vault"])
    profile_notes = [ltm.read_note(env["vault"], e["path"])
                     for e in ltm.registry_entries(env["vault"])
                     if e["path"].startswith("agent/profile/")]
    superseded = [n for n in profile_notes if n and n["frontmatter"].get("superseded_by")]
    active = [n for n in profile_notes
              if n and not n["frontmatter"].get("superseded_by")]
    assert len(superseded) == 1
    assert len(active) == 1 and "en-US" in active[0]["body"]


# ── recall 可見性(投影筆記進 INDEX registry)──────────────────────────

def test_projected_facet_visible_in_registry(env):
    """recall 走 index-first:投影筆記必須出現在 INDEX registry。"""
    transcript.append(env["tdir"], "evt:7", "event_raw", {"summary": "x"}, ts=T0)
    stm.facet_insert(env["db"], "preference", "reply_lang", "zh-TW",
                     confidence=0.9, evidence_ids=["evt:7"], seen_at=T0)
    facets.project_to_vault(env["db"], env["vault"])
    reg = ltm.registry_entries(env["vault"])
    hit = [e for e in reg if "reply_lang" in e["summary"] or "reply_lang" in e["title"]]
    assert hit, "projected facet must be discoverable via INDEX registry"


def test_job_run_includes_projection(env):
    """夜間 job 尾端自動投影:preference facet → 投影統計 > 0。"""
    stats = consolidate.run(db=env["db"], vault=env["vault"], transcript_dir=env["tdir"],
                            now_ts=env["now"],
                            _api=_pref_api(env["eid"], facet_key="reply_lang"))
    assert stats["facets_projected"] >= 1
    reg = [e for e in ltm.registry_entries(env["vault"])
           if e["path"].startswith("agent/profile/")]
    assert any("reply_lang" in e["title"] or "reply_lang" in e["summary"] for e in reg)
