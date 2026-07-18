"""part-003.2-slice-001 Todo 5:七 workload fixture corpus 驗證。

每個 workload bundle:
- authoritative sources(A/B 共用)與 historical observations 分離
- task/session/run IDs、initial + changed authority versions
- expected next action/claims/evidence/status(deterministic oracle)
- expected source reads、forbidden stale/cross-task claims
- 內容 hash;manifest version;答案不得洩漏進 B 的 capsule hint

用合成/去識別化內容;不含私人 transcript/session dump。
"""

import json

import pytest

from experiments.task_capsule import fixtures as F

REQUIRED_WORKLOADS = {
    "three_run_continuation",
    "next_day_resume",
    "parallel_agent_handoff",
    "changed_constraint",
    "superseded_preference",
    "evidence_rehydrate",
    "cancel_restart",
}


# ── manifest + corpus 完整性 ─────────────────────────────────────────

def test_exactly_seven_uniquely_named_workloads():
    names = [w.name for w in F.load_all()]
    assert len(names) == 7
    assert set(names) == REQUIRED_WORKLOADS
    assert len(set(names)) == 7                           # 無重複


def test_manifest_version_present():
    m = F.load_manifest()
    assert isinstance(m["manifest_version"], int) and m["manifest_version"] >= 1


def test_each_workload_has_shared_authority_and_oracle():
    for w in F.load_all():
        assert w.authority_sources, f"{w.name} missing authority sources"
        assert w.oracle.get("next_action"), f"{w.name} oracle missing next_action"
        assert "status" in w.oracle, f"{w.name} oracle missing status"


def test_each_workload_declares_expected_reads():
    for w in F.load_all():
        assert isinstance(w.expected_reads, (list, tuple))
        # expected reads 必須全部是真實 authority source key
        keys = {s["key"] for s in w.authority_sources}
        for r in w.expected_reads:
            assert r in keys, f"{w.name}: expected read {r} not an authority source"


def test_each_workload_declares_negative_assertions():
    """每個 workload 必須聲明禁止的 stale/cross-task claim(對抗污染)。"""
    for w in F.load_all():
        assert isinstance(w.forbidden_claims, (list, tuple))


# ── prior capsule hint(B 專屬)不得洩漏 oracle 答案 ───────────────────

def test_b_capsule_hint_does_not_leak_oracle_answer():
    for w in F.load_all():
        if w.prior_capsule is None:
            continue
        hint = json.dumps(w.prior_capsule, ensure_ascii=False)
        # oracle 的 next_action 不得原封出現在 capsule hint(否則 B 作弊)
        assert w.oracle["next_action"] not in hint, \
            f"{w.name}: oracle answer leaked into B capsule hint"


# ── 內容 hash 穩定 ───────────────────────────────────────────────────

def test_content_hash_stable_across_loads():
    h1 = {w.name: F.workload_hash(w) for w in F.load_all()}
    h2 = {w.name: F.workload_hash(w) for w in F.load_all()}
    assert h1 == h2
    assert all(len(h) == 64 for h in h1.values())


# ── validator 拒絕破壞契約的 bundle ──────────────────────────────────

def test_validator_rejects_duplicate_task_ids():
    bad = [
        F.Workload(name="a", task_id="dup", session_ids=("s1",), run_ids=("r1",),
                   authority_sources=[{"key": "k", "version": "v1", "payload": {}}],
                   observations=[], oracle={"next_action": "go", "status": "open",
                                            "claims": [], "evidence_refs": []},
                   expected_reads=["k"], forbidden_claims=[], prior_capsule=None,
                   changed_authority=None),
        F.Workload(name="b", task_id="dup", session_ids=("s2",), run_ids=("r2",),
                   authority_sources=[{"key": "k", "version": "v1", "payload": {}}],
                   observations=[], oracle={"next_action": "go", "status": "open",
                                            "claims": [], "evidence_refs": []},
                   expected_reads=["k"], forbidden_claims=[], prior_capsule=None,
                   changed_authority=None),
    ]
    with pytest.raises(F.FixtureError):
        F.validate_corpus(bad)


def test_validator_rejects_expected_read_not_in_sources():
    bad = [F.Workload(
        name="x", task_id="t", session_ids=("s",), run_ids=("r",),
        authority_sources=[{"key": "real", "version": "v1", "payload": {}}],
        observations=[], oracle={"next_action": "go", "status": "open",
                                 "claims": [], "evidence_refs": []},
        expected_reads=["ghost"], forbidden_claims=[], prior_capsule=None,
        changed_authority=None)]
    with pytest.raises(F.FixtureError):
        F.validate_corpus(bad)


def test_validator_rejects_answer_leak_into_capsule():
    bad = [F.Workload(
        name="x", task_id="t", session_ids=("s",), run_ids=("r",),
        authority_sources=[{"key": "k", "version": "v1", "payload": {}}],
        observations=[],
        oracle={"next_action": "SECRET_ACTION", "status": "open",
                "claims": [], "evidence_refs": []},
        expected_reads=["k"], forbidden_claims=[],
        prior_capsule={"next_action": "SECRET_ACTION"},   # 洩漏!
        changed_authority=None)]
    with pytest.raises(F.FixtureError):
        F.validate_corpus(bad)


def test_validator_accepts_real_corpus():
    F.validate_corpus(F.load_all())                       # 不拋 = 通過


# ── changed authority(stale replay workloads)─────────────────────────

def test_changed_constraint_has_changed_authority():
    w = F.get("changed_constraint")
    assert w.changed_authority is not None                # 有版本變更以測 stale


def test_superseded_preference_has_changed_authority():
    w = F.get("superseded_preference")
    assert w.changed_authority is not None
