"""part-002.5-slice-001:pending_proposals CRUD + expire + precheck 不落地。"""

import pytest

from core import stm, writer

PROPOSAL = {
    "agent": "schedule", "proposal_type": "schedule_change", "target": "new",
    "payload": {"action": "add", "fields": {"title": "開會", "start_at": 1_800_000_000}},
    "confidence": 0.9, "evidence": ["明天開會"],
}


@pytest.fixture()
def db(tmp_path):
    path = tmp_path / "state.db"
    stm.init(path)
    return path


# ── pending CRUD ─────────────────────────────────────────────────────

def test_pending_add_get_roundtrip(db):
    pid = stm.pending_add(db, PROPOSAL, "預覽文", channel_ref="user:123")
    got = stm.pending_get(db, pid)
    assert got["proposal"] == PROPOSAL                      # JSON roundtrip
    assert got["preview"] == "預覽文"
    assert got["status"] == "pending" and got["channel_ref"] == "user:123"


def test_pending_get_missing(db):
    assert stm.pending_get(db, 999) is None


def test_pending_set_status_only_from_pending(db):
    pid = stm.pending_add(db, PROPOSAL, "p")
    assert stm.pending_set_status(db, pid, "done")
    assert stm.pending_get(db, pid)["status"] == "done"
    assert not stm.pending_set_status(db, pid, "cancelled")  # 已非 pending → 不動
    assert stm.pending_get(db, pid)["status"] == "done"


def test_pending_cross_instance_survives(db):
    """無狀態驗證:pending 存 DB1,bot 重啟(新連線)仍取得回。"""
    pid = stm.pending_add(db, PROPOSAL, "p")
    # 模擬新 process:重新從路徑讀,無共享記憶體
    got = stm.pending_get(db, pid)
    assert got and got["proposal"]["payload"]["action"] == "add"


def test_pending_expire_due(db):
    now = 1_800_000_000
    old = stm.pending_add(db, PROPOSAL, "old")
    # 手動改 created_at 到過去
    con = stm.connect(db)
    con.execute("UPDATE pending_proposals SET created_at = ? WHERE id = ?", (now - 1000, old))
    con.commit()
    con.close()
    fresh = stm.pending_add(db, PROPOSAL, "fresh")
    con = stm.connect(db)
    con.execute("UPDATE pending_proposals SET created_at = ? WHERE id = ?", (now, fresh))
    con.commit()
    con.close()

    expired = stm.pending_expire_due(db, ttl_seconds=600, now_ts=now)
    assert expired == [old]
    assert stm.pending_get(db, old)["status"] == "expired"
    assert stm.pending_get(db, fresh)["status"] == "pending"   # 未逾時不動


# ── precheck 不落地 ──────────────────────────────────────────────────

def test_precheck_valid_needs_confirm_no_landing(db):
    pre = writer.precheck(PROPOSAL, db)
    assert pre.ok and pre.needs_confirm
    assert "start_at" in pre.preview
    assert stm.schedule_list(db) == []                      # 關鍵:precheck 不落地


def test_precheck_invalid_rejected(db):
    bad = {**PROPOSAL, "payload": {"action": "delete", "fields": {}}}
    pre = writer.precheck(bad, db)
    assert not pre.ok and "illegal action" in pre.reason


def test_precheck_missing_target_rejected(db):
    bad = {**PROPOSAL, "target": "999",
           "payload": {"action": "done", "fields": {}}}
    pre = writer.precheck(bad, db)
    assert not pre.ok and "not found" in pre.reason


def test_precheck_done_needs_no_confirm(db):
    rid = stm.schedule_add(db, "x", 1_800_000_000)
    p = {**PROPOSAL, "target": str(rid), "payload": {"action": "done", "fields": {}}}
    pre = writer.precheck(p, db)
    assert pre.ok and not pre.needs_confirm                 # done 免確認


def test_apply_validated_lands(db):
    pre = writer.precheck(PROPOSAL, db)
    r = writer.apply_validated(pre.proposal, db)
    assert r.ok and stm.schedule_list(db)[0]["title"] == "開會"


# ── audit A2'/A3':第二階段重驗(confirm_and_apply)────────────────────

def test_confirm_and_apply_from_dict(db):
    """A3':pending 存的是 dict,confirm_and_apply 接 dict 落地。"""
    pid = stm.pending_add(db, PROPOSAL, "preview")
    got = stm.pending_get(db, pid)
    r = writer.confirm_and_apply(got["proposal"], db)       # dict 直接進,不炸
    assert r.ok and stm.schedule_list(db)[0]["title"] == "開會"


def test_confirm_and_apply_revalidates_deleted_target(db):
    """A2':precheck 後 target 被刪 → 第二階段重驗攔截,不落地空 row。"""
    rid = stm.schedule_add(db, "victim", 1_800_000_000)
    upd = {**PROPOSAL, "target": str(rid),
           "payload": {"action": "update", "fields": {"title": "改"}}}
    pid = stm.pending_add(db, upd, "preview")               # 第一階段存下
    con = stm.connect(db)                                    # 期間 target 被刪
    con.execute("DELETE FROM schedule WHERE id = ?", (rid,))
    con.commit()
    con.close()
    got = stm.pending_get(db, pid)
    r = writer.confirm_and_apply(got["proposal"], db)       # 第二階段重驗
    assert not r.ok and "revalidation failed" in r.detail


def test_confirm_and_apply_rejects_tampered_dict(db):
    """confirm_and_apply 不信任 pending 內容:被竄改成非法也重驗攔截。"""
    tampered = {**PROPOSAL, "payload": {"action": "delete", "fields": {}}}
    r = writer.confirm_and_apply(tampered, db)
    assert not r.ok and "revalidation failed" in r.detail
