"""part-003.2-slice-001 Todo 11:deterministic checkpoint/promotion。

接受 canonical observation + current authority bundle → 只 promote 通過驗證
(source/evidence、authority-version、task match、size limit、CAS、idempotency)的
allowlisted 欄位進 capsule revision。三 trigger(explicit/precompact/stop)呼叫
同一 deterministic function,不成為 runtime hook。failed_attempts/open_loops 保留
evidence,不覆蓋已驗證 completion(除非有更新的權威事實)。
"""

import pytest

from experiments.task_capsule import checkpoint as CK
from experiments.task_capsule import models as m
from experiments.task_capsule import store as S


@pytest.fixture()
def db(tmp_path):
    p = tmp_path / "capsule.db"
    S.init(p)
    return p


def _obs(task="t1", next_action="do next", **payload_over):
    payload = {
        "task_id": task, "goal": "g", "status": "in_progress",
        "next_action": next_action, "open_loops": ["o"],
        "authority_versions": [["beacon:CURRENT", "v3"]],
    }
    payload.update(payload_over)
    return m.parse_observation({
        "source_kind": "beacon", "source_id": "part-x",
        "captured_at": 1_800_000_000, "authority_class": "observational",
        "version_or_hash": "sha:o1", "payload": payload})


CURRENT = {"beacon:CURRENT": "v3"}


# ── 三 trigger 等價 ──────────────────────────────────────────────────

@pytest.mark.parametrize("trigger", ["explicit", "precompact", "stop"])
def test_all_triggers_call_same_function(db, trigger):
    r = CK.checkpoint(db, _obs(), current_authority=CURRENT,
                      idempotency_key=f"k-{trigger}", trigger=trigger)
    assert r.promoted is True
    st = S.Store(db)
    assert st.get_current("t1").next_action == "do next"
    st.close()


# ── 基本 promotion ───────────────────────────────────────────────────

def test_first_checkpoint_creates_v1(db):
    r = CK.checkpoint(db, _obs(), current_authority=CURRENT, idempotency_key="k1")
    assert r.promoted and r.version == 1


def test_three_observations_three_revisions(db):
    CK.checkpoint(db, _obs(next_action="a"), current_authority=CURRENT,
                  idempotency_key="k1")
    CK.checkpoint(db, _obs(next_action="b"), current_authority=CURRENT,
                  idempotency_key="k2")
    CK.checkpoint(db, _obs(next_action="c"), current_authority=CURRENT,
                  idempotency_key="k3")
    st = S.Store(db)
    assert st.revision_count("t1") == 3
    assert st.get_current("t1").next_action == "c"
    st.close()


# ── idempotency:重複 key 不重複寫 ────────────────────────────────────

def test_duplicate_idempotency_key_no_double_write(db):
    CK.checkpoint(db, _obs(), current_authority=CURRENT, idempotency_key="dup")
    CK.checkpoint(db, _obs(), current_authority=CURRENT, idempotency_key="dup")
    st = S.Store(db)
    assert st.revision_count("t1") == 1
    st.close()


# ── stale authority:observation 引用過期權威 → 拒絕 promote ───────────

def test_stale_authority_rejected(db):
    obs = _obs(authority_versions=[["beacon:CURRENT", "v2"]])   # 舊版
    r = CK.checkpoint(db, obs, current_authority={"beacon:CURRENT": "v9"},
                      idempotency_key="k")
    assert r.promoted is False and "stale" in r.reason.lower()
    st = S.Store(db)
    assert st.get_current("t1") is None                  # 未寫入
    st.close()


# ── task mismatch:observation task 與指定不符 → 拒絕 ──────────────────

def test_task_mismatch_rejected(db):
    obs = _obs(task="wrong")
    with pytest.raises(CK.CheckpointError):
        CK.checkpoint(db, obs, current_authority=CURRENT,
                      idempotency_key="k", expected_task="t1")


# ── unverified observation:缺必需欄位 → 拒絕 ─────────────────────────

def test_observation_missing_next_action_rejected(db):
    obs = m.parse_observation({
        "source_kind": "beacon", "source_id": "x", "captured_at": 1_800_000_000,
        "authority_class": "observational", "version_or_hash": "sha:x",
        "payload": {"task_id": "t1", "goal": "g", "status": "open"}})  # 無 next_action
    r = CK.checkpoint(db, obs, current_authority=CURRENT, idempotency_key="k")
    assert r.promoted is False


# ── completion regression:已 done 不被無權威的舊觀測覆蓋 ─────────────

def test_completion_not_overwritten_without_newer_authority(db):
    # 先 promote 一個 done capsule
    done_obs = _obs(status="done", next_action="verify",
                    completed=["shipped"], evidence_refs=[["beacon:CURRENT", "v3"]])
    CK.checkpoint(db, done_obs, current_authority=CURRENT, idempotency_key="k1")
    # 再來一個 in_progress 舊觀測(無更新權威)→ 不得回退 completion
    regress = _obs(status="in_progress", next_action="redo")
    r = CK.checkpoint(db, regress, current_authority=CURRENT,
                      idempotency_key="k2", expected_version=1)
    assert r.promoted is False and "regress" in r.reason.lower()
    st = S.Store(db)
    assert st.get_current("t1").status is m.CapsuleStatus.DONE
    st.close()


# ── 失敗 promote 不留 partial revision ───────────────────────────────

def test_failed_promotion_leaves_no_partial(db):
    obs = _obs(authority_versions=[["beacon:CURRENT", "v2"]])   # stale → 失敗
    CK.checkpoint(db, obs, current_authority={"beacon:CURRENT": "v9"},
                  idempotency_key="k")
    st = S.Store(db)
    assert st.revision_count("t1") == 0                  # 無 partial
    st.close()


# ── only allowlisted fields promoted(不含 chain-of-thought)───────────

def test_no_freeform_fields_promoted(db):
    obs = _obs(reasoning="secret chain of thought", chat="full log")
    r = CK.checkpoint(db, obs, current_authority=CURRENT, idempotency_key="k")
    assert r.promoted
    st = S.Store(db)
    cap = st.get_current("t1")
    st.close()
    # capsule 沒有 reasoning/chat 欄位(models 本就不含);確認 promotion 不夾帶
    assert not hasattr(cap, "reasoning") and not hasattr(cap, "chat")
