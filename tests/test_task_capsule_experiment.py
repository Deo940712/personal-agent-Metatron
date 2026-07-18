"""part-003.2-slice-001 Todo 13:實驗 orchestrator + CLI。

跑七 workload × 兩臂,每臂 1 warmup(排除)+ 30 measured samples,paired AB/BA
順序(seed 20260716,執行前持久化)。產出 summary JSON/CSV 到已驗證 experiment
root。abort on:safety 失敗、spec/fixture drift、missing/duplicate sample、
production path。deterministic:同版本第二次跑得同 correctness/reads/context/decision。
"""

import json

import pytest

from experiments.task_capsule import experiment as E
from experiments.task_capsule import paths as P


@pytest.fixture()
def root(tmp_path):
    return P.prepare_experiment_root(tmp_path / "exp")


# ── 執行:結構完整 ───────────────────────────────────────────────────

def test_run_produces_summary(root):
    summary = E.run_experiment(root, measured_samples=3)   # 小樣本加速測試
    assert summary["workload_count"] == 7
    assert set(summary["arms"]) == {"A", "B"}
    assert "decision" in summary
    assert summary["spec_hash"] and summary["fixture_hash"]


def test_summary_has_all_seven_workloads_both_arms(root):
    summary = E.run_experiment(root, measured_samples=3)
    for name in summary["per_workload"]:
        assert "A" in summary["per_workload"][name]
        assert "B" in summary["per_workload"][name]
    assert len(summary["per_workload"]) == 7


def test_paired_order_persisted(root):
    E.run_experiment(root, measured_samples=3)
    order = json.loads((root / E.ORDER_FILE).read_text(encoding="utf-8"))
    assert order["seed"] == 20260716
    assert len(order["pairs"]) > 0
    for p in order["pairs"]:
        assert p in ("AB", "BA")


def test_warmup_excluded_from_aggregates(root):
    summary = E.run_experiment(root, measured_samples=5)
    # 每 workload/arm 應恰有 measured_samples 個計入(warmup 排除)
    for name, arms in summary["per_workload"].items():
        assert arms["A"]["sample_count"] == 5
        assert arms["B"]["sample_count"] == 5


# ── deterministic:第二次跑得同決策/正確率/reads ──────────────────────

def test_deterministic_across_fresh_runs(tmp_path):
    r1 = P.prepare_experiment_root(tmp_path / "e1")
    r2 = P.prepare_experiment_root(tmp_path / "e2")
    s1 = E.run_experiment(r1, measured_samples=3)
    s2 = E.run_experiment(r2, measured_samples=3)
    assert s1["decision"]["outcome"] == s2["decision"]["outcome"]
    for name in s1["per_workload"]:
        a1 = s1["per_workload"][name]["A"]
        a2 = s2["per_workload"][name]["A"]
        assert a1["correct"] == a2["correct"]
        assert a1["authority_reads_median"] == a2["authority_reads_median"]


# ── safety:注入 forbidden claim → invalid（hard gate）─────────────────

def test_safety_failure_makes_invalid(root, monkeypatch):
    # 讓 A-arm 產出一個 forbidden claim → hard event → invalid_run
    from experiments.task_capsule import runner as R
    orig = R.run_arm_a

    def tainted(w, **kw):
        res = orig(w, **kw)
        # 硬塞一個該 workload 的 forbidden claim
        if w.forbidden_claims:
            object.__setattr__(res, "claims", res.claims + (w.forbidden_claims[0],))
        return res
    monkeypatch.setattr(R, "run_arm_a", tainted)
    summary = E.run_experiment(root, measured_samples=2)
    assert summary["decision"]["outcome"] == "invalid_run"


# ── 拒絕 production 路徑 ──────────────────────────────────────────────

def test_run_rejects_production_root():
    import config
    with pytest.raises(P.UnsafePathError):
        E.run_experiment(config.DATA_DIR, measured_samples=2)


# ── spec/fixture drift:resume identity 不符 → 拒絕 ────────────────────

def test_resume_rejects_fixture_drift(root, monkeypatch):
    E.run_experiment(root, measured_samples=2)
    # 竄改 fixture hash 來源 → resume 應偵測 drift
    from experiments.task_capsule import artifacts as A
    with pytest.raises(A.ArtifactError):
        E.resume_experiment(root, override_fixture_hash="deadbeef" * 8,
                            measured_samples=2)


# ── evidence 匯出到 .omo/evidence(非 production)─────────────────────

def test_export_evidence_writes_summary_files(root, tmp_path):
    summary = E.run_experiment(root, measured_samples=3)
    out = tmp_path / "evidence"
    out.mkdir()
    E.export_evidence(summary, root, out)
    assert (out / "task-13-ecc-task-capsule-experiment-summary.json").exists()
    assert (out / "task-13-ecc-task-capsule-experiment-summary.csv").exists()
