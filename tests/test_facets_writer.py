"""part-007-slice-001:profile_facet 提案 → writer 驗證落地。

Done gate 對應:
- 合法三 action(create/reinforce/supersede)落地
- 五類拒絕路徑:偽 evidence / pinned / forgotten / 不存在 supersede 目標 /
  已被取代目標
- 拒絕記 events(action=proposal_rejected)
"""

import pytest

import config
from core import facets, proposals as P, stm, transcript, writer

DAY = 86400
T0 = 1_800_000_000


@pytest.fixture()
def env(tmp_path, monkeypatch):
    """真 DB + 真 transcript(tmp);writer 走預設 config 路徑。"""
    db = tmp_path / "state.db"
    stm.init(db)
    tdir = tmp_path / "transcript"
    tdir.mkdir()
    monkeypatch.setattr(config, "TRANSCRIPT_DIR", tdir)
    # 預埋真實證據
    for i in (1, 2, 3, 4):
        transcript.append(tdir, f"evt:{i}", "event_raw",
                          {"summary": f"evidence {i}"}, ts=T0 + i)
    return db


def facet_proposal(action="create", *, facet_class="preference",
                   facet_key="reply_lang", value="zh-TW",
                   evidence_ids=None, supersedes_id=None,
                   agent="consolidator", confidence=0.7):
    payload = {
        "action": action,
        "facet_class": facet_class,
        "facet_key": facet_key,
        "value": value,
        "evidence_ids": evidence_ids or ["evt:1"],
    }
    if supersedes_id is not None:
        payload["supersedes_id"] = supersedes_id
    return {
        "agent": agent,
        "proposal_type": "profile_facet",
        "target": f"facet:{facet_class}/{facet_key}",
        "payload": payload,
        "confidence": confidence,
        "evidence": ["原句證據"],
    }


def rejected_events(db):
    return [e for e in stm.event_query(db, actor="writer")
            if e["action"] == "proposal_rejected"]


# ── payload 驗證(純結構,無 DB)─────────────────────────────────────

def test_payload_validator_rejects_bad_shapes():
    cases = [
        {"action": "bogus", "facet_class": "preference", "facet_key": "k",
         "value": "v", "evidence_ids": ["evt:1"]},
        {"action": "create", "facet_class": "bogus", "facet_key": "k",
         "value": "v", "evidence_ids": ["evt:1"]},
        {"action": "create", "facet_class": "preference", "facet_key": " ",
         "value": "v", "evidence_ids": ["evt:1"]},
        {"action": "create", "facet_class": "preference", "facet_key": "k",
         "value": "", "evidence_ids": ["evt:1"]},
        {"action": "create", "facet_class": "preference", "facet_key": "k",
         "value": "v", "evidence_ids": []},
        {"action": "create", "facet_class": "preference", "facet_key": "k",
         "value": "v", "evidence_ids": ["no-namespace"]},
        {"action": "supersede", "facet_class": "preference", "facet_key": "k",
         "value": "v", "evidence_ids": ["evt:1"]},  # 缺 supersedes_id
        {"action": "supersede", "facet_class": "preference", "facet_key": "k",
         "value": "v", "evidence_ids": ["evt:1"], "supersedes_id": True},  # bool 陷阱
    ]
    for payload in cases:
        with pytest.raises(P.ProposalError):
            P.validate_profile_facet(payload)


def test_confirmation_policy():
    """create/reinforce 免確認;supersede 需確認(§3.2 閘門)。"""
    create = P.parse_envelope(facet_proposal("create"))
    reinforce = P.parse_envelope(facet_proposal("reinforce"))
    supersede = P.parse_envelope(facet_proposal("supersede", supersedes_id=1))
    assert not P.needs_confirmation(create)
    assert not P.needs_confirmation(reinforce)
    assert P.needs_confirmation(supersede)


def test_precheck_target_addressing(env):
    bad = facet_proposal("create")
    bad["target"] = "facet:wrong/address"
    pre = writer.precheck(bad, env)
    assert not pre.ok
    assert "target" in pre.reason


# ── 三 action 落地 ───────────────────────────────────────────────────

def test_create_lands_provisional(env):
    res = writer.apply(facet_proposal("create"), None, env)
    assert res.ok
    row = stm.facet_get_active(env, "preference", "reply_lang")
    assert row["state"] == "provisional"
    assert row["value"] == "zh-TW"


def test_create_duplicate_active_rejected(env):
    assert writer.apply(facet_proposal("create"), None, env).ok
    res = writer.apply(facet_proposal("create", value="en"), None, env)
    assert not res.ok
    assert "already exists" in res.detail


def test_reinforce_accumulates_and_promotes(env):
    assert writer.apply(facet_proposal("create"), None, env).ok
    fid = stm.facet_get_active(env, "preference", "reply_lang")["id"]
    # 人工拉開時間跨度以觸發升級(detector 需跨天;writer 內部 last_seen=now(),
    # 故 first_seen 需相對真實 now 回推)
    con = stm.connect(env)
    con.execute("UPDATE profile_facets SET first_seen_at = ? WHERE id = ?",
                (stm.now() - (config.FACET_STABLE_MIN_DAYS + 1) * DAY, fid))
    con.commit()
    con.close()
    for eid in ("evt:2", "evt:3"):
        res = writer.apply(facet_proposal("reinforce", evidence_ids=[eid]), None, env)
        assert res.ok
    row = stm.facet_get(env, fid)
    assert row["evidence_count"] >= config.FACET_STABLE_MIN_EVIDENCE
    assert row["state"] == "stable"          # writer 內建 detector 升級


def test_supersede_lands_with_confirm(env):
    assert writer.apply(facet_proposal("create"), None, env).ok
    old_id = stm.facet_get_active(env, "preference", "reply_lang")["id"]
    res = writer.apply(
        facet_proposal("supersede", value="en-US", evidence_ids=["evt:2"],
                       supersedes_id=old_id),
        lambda preview: True, env)           # 使用者確認
    assert res.ok
    old = stm.facet_get(env, old_id)
    assert old["state"] == "superseded"
    assert old["superseded_by"] == res.row_id
    new = stm.facet_get_active(env, "preference", "reply_lang")
    assert (new["id"], new["value"]) == (res.row_id, "en-US")


def test_supersede_without_confirm_fail_closed(env):
    assert writer.apply(facet_proposal("create"), None, env).ok
    old_id = stm.facet_get_active(env, "preference", "reply_lang")["id"]
    res = writer.apply(
        facet_proposal("supersede", value="en", evidence_ids=["evt:2"],
                       supersedes_id=old_id),
        None, env)                            # 非互動 → fail-closed
    assert res.status == "needs_confirm_rejected"
    assert stm.facet_get(env, old_id)["state"] == "provisional"  # 未動


# ── 五類拒絕路徑 ─────────────────────────────────────────────────────

def test_reject_fabricated_evidence(env):
    res = writer.apply(facet_proposal("create", evidence_ids=["evt:999"]), None, env)
    assert not res.ok
    assert "not found in transcript" in res.detail
    assert stm.facet_get_active(env, "preference", "reply_lang") is None
    assert any("not found in transcript" in e["summary"] for e in rejected_events(env))


def test_reject_reinforce_pinned(env):
    assert writer.apply(facet_proposal("create"), None, env).ok
    fid = stm.facet_get_active(env, "preference", "reply_lang")["id"]
    stm.facet_set_user_state(env, fid, "pinned")
    res = writer.apply(facet_proposal("reinforce", evidence_ids=["evt:2"]), None, env)
    assert not res.ok
    assert "pinned" in res.detail


def test_reject_reinforce_forgotten(env):
    assert writer.apply(facet_proposal("create"), None, env).ok
    fid = stm.facet_get_active(env, "preference", "reply_lang")["id"]
    stm.facet_set_user_state(env, fid, "forgotten")
    res = writer.apply(facet_proposal("reinforce", evidence_ids=["evt:2"]), None, env)
    assert not res.ok                        # forgotten 後無 active 可 reinforce
    assert "no active facet" in res.detail


def test_reject_supersede_missing_target(env):
    res = writer.apply(
        facet_proposal("supersede", supersedes_id=9999),
        lambda _: True, env)
    assert not res.ok
    assert "not found" in res.detail


def test_reject_supersede_already_superseded(env):
    assert writer.apply(facet_proposal("create"), None, env).ok
    old_id = stm.facet_get_active(env, "preference", "reply_lang")["id"]
    first = writer.apply(
        facet_proposal("supersede", value="v2", evidence_ids=["evt:2"],
                       supersedes_id=old_id),
        lambda _: True, env)
    assert first.ok
    res = writer.apply(
        facet_proposal("supersede", value="v3", evidence_ids=["evt:3"],
                       supersedes_id=old_id),                 # 目標已被取代
        lambda _: True, env)
    assert not res.ok
    assert "not active" in res.detail


def test_reject_supersede_pinned(env):
    assert writer.apply(facet_proposal("create"), None, env).ok
    old_id = stm.facet_get_active(env, "preference", "reply_lang")["id"]
    stm.facet_set_user_state(env, old_id, "pinned")
    res = writer.apply(
        facet_proposal("supersede", value="v2", evidence_ids=["evt:2"],
                       supersedes_id=old_id),
        lambda _: True, env)
    assert not res.ok
    assert "pinned" in res.detail


def test_reject_supersede_class_key_mismatch(env):
    assert writer.apply(facet_proposal("create"), None, env).ok
    other = stm.facet_insert(env, "tooling", "editor", "vscode", seen_at=T0)
    res = writer.apply(
        facet_proposal("supersede", value="en", evidence_ids=["evt:2"],
                       supersedes_id=other),                  # 指到別的 class/key
        lambda _: True, env)
    assert not res.ok
    assert "mismatch" in res.detail


def test_rejections_logged_to_events(env):
    writer.apply(facet_proposal("create", evidence_ids=["evt:999"]), None, env)
    writer.apply(facet_proposal("reinforce"), None, env)      # 無 active 可 reinforce
    assert len(rejected_events(env)) >= 2
