"""part-003.2-slice-001 Todo 9(A-arm)+ Todo 12(B-arm):A/B runner。

A-arm(現況):只從當前權威 sources 重建;不開 capsule DB、不收 B artifacts;
run 間不帶 process state。記錄 reads/bytes/tokens/runtime/claims/evidence/recovery。

B-arm:載入 prior capsule 作 bounded historical hints,然後在產出前重讀
freshness/evidence 要求的權威;同 fixture 與 oracle;不自評、不繞過 stale 檢查、
不碰別的 task capsule。

deterministic scoring,不需 LLM。
"""

import pytest

from experiments.task_capsule import fixtures as F
from experiments.task_capsule import runner as R
from experiments.task_capsule import store as S


@pytest.fixture()
def db(tmp_path):
    p = tmp_path / "capsule.db"
    S.init(p)
    return p


# ── A-arm:七 fixture 全部正確重建 ────────────────────────────────────

@pytest.mark.parametrize("wl", sorted(f.name for f in F.load_all()))
def test_arm_a_reconstructs_all_fixtures(wl):
    w = F.get(wl)
    result = R.run_arm_a(w)
    assert result.correct is True, f"{wl}: A-arm answer != oracle"
    assert result.recovery == 1.0
    assert result.next_action == w.oracle["next_action"]
    assert result.status == w.oracle["status"]


def test_arm_a_does_not_open_capsule_db(db):
    """A-arm 絕不觸碰 capsule store(對照組必須無狀態)。"""
    w = F.get("three_run_continuation")
    result = R.run_arm_a(w, capsule_db=db)                # 即使給了 db 也不該用
    # store 應為空(A-arm 沒寫入)
    st = S.Store(db)
    assert st.revision_count(w.task_id) == 0
    st.close()
    assert result.correct


def test_arm_a_records_metrics():
    w = F.get("three_run_continuation")
    r = R.run_arm_a(w)
    assert r.authority_reads == len(w.expected_reads)     # 讀了所有必需權威
    assert r.assembled_bytes > 0
    assert r.estimated_tokens > 0
    assert r.runtime_ns >= 0


def test_arm_a_deterministic_claims_across_runs():
    w = F.get("three_run_continuation")
    r1 = R.run_arm_a(w)
    r2 = R.run_arm_a(w)
    assert r1.claims == r2.claims and r1.evidence_refs == r2.evidence_refs
    # runtime 可不同,不比


def test_arm_a_missing_source_reports_incomplete():
    """移除必需權威 → A-arm 誠實回不完整,不編造。"""
    w = F.get("three_run_continuation")
    r = R.run_arm_a(w, drop_sources={w.expected_reads[0]})
    assert r.recovery < 1.0 or r.correct is False         # 不完整或不正確,絕不假成功


# ── A-arm 不含 forbidden stale/cross-task claim ───────────────────────

def test_arm_a_no_forbidden_claims():
    for w in F.load_all():
        r = R.run_arm_a(w)
        for bad in w.forbidden_claims:
            assert bad not in r.claims, f"{w.name}: A-arm emitted forbidden {bad!r}"


# ── B-arm:七 fixture 全部正確(用 capsule hints 但重查權威)────────────

@pytest.mark.parametrize("wl", sorted(f.name for f in F.load_all()))
def test_arm_b_matches_oracle(wl, db):
    w = F.get(wl)
    result = R.run_arm_b(w, capsule_db=db)
    assert result.correct is True, f"{wl}: B-arm answer != oracle"
    assert result.recovery == 1.0
    assert result.next_action == w.oracle["next_action"]


def test_arm_b_rereads_authority_on_stale_capsule(db):
    """changed_constraint:prior capsule 是舊版 → B 必須重讀權威、不用 stale。"""
    w = F.get("changed_constraint")
    r = R.run_arm_b(w, capsule_db=db)
    assert r.correct                                      # 得到新版正確答案
    for bad in w.forbidden_claims:
        assert bad not in r.claims                        # 沒有沿用舊 constraint


def test_arm_b_superseded_preference_not_stale(db):
    w = F.get("superseded_preference")
    r = R.run_arm_b(w, capsule_db=db)
    assert r.correct
    assert "format in English" not in r.claims


def test_arm_b_no_forbidden_claims(db):
    for w in F.load_all():
        r = R.run_arm_b(w, capsule_db=db)
        for bad in w.forbidden_claims:
            assert bad not in r.claims, f"{w.name}: B-arm emitted forbidden {bad!r}"


def test_arm_b_does_not_access_other_task_capsule(db):
    """B 只讀自己 task 的 capsule;別的 task 存在也不撈。"""
    other = F.get("next_day_resume")
    st = S.Store(db)
    from experiments.task_capsule import models as m
    st.put(m.parse_capsule(other.prior_capsule), idempotency_key="other")
    st.close()
    w = F.get("three_run_continuation")
    r = R.run_arm_b(w, capsule_db=db)
    assert r.task_id == w.task_id and r.correct           # 沒被別的 task 污染


# ── A/B 同 fixture、同 oracle(公平性)────────────────────────────────

def test_arm_a_and_b_same_oracle_target(db):
    for w in F.load_all():
        ra = R.run_arm_a(w)
        rb = R.run_arm_b(w, capsule_db=db)
        assert ra.next_action == rb.next_action == w.oracle["next_action"]
