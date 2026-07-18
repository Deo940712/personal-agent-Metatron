"""part-003.2-slice-001 Todo 6:凍結 metrics + thresholds + 判定語意。

規則在看結果前凍結(work plan Decision 11/14/15):
- correctness = normalized {claims, evidence_refs, next_action, status} 完全相等
- recovery completeness = 命中必需 oracle 欄位 / 必需總數
- authority reads = 實際開啟的 distinct 權威 artifact 數(重複同一個計一次)
- assembled context = UTF-8 byte length;est tokens = ceil(bytes/4)(啟發式,非 tokenizer)
- runtime = perf_counter_ns 只圍 reconstruction;p50/p95 皆報,gate 只用 p95
- stale/leakage/safety/idempotency/concurrency = 整數事件計數,>0 即 hard fail

adoption gate:兩臂全 workload 完全正確 + 100% recovery;所有 hard 事件為 0;
七 workload 至少四個(authority reads 或 assembled bytes 中位數改善 ≥15%)qualify;
aggregate B p95 ≤ 110% A p95。否則 retain_a。
"""

import pytest

from experiments.task_capsule import metrics as M


# ── 個別 metric 計算 ─────────────────────────────────────────────────

def test_correctness_exact_match():
    oracle = {"claims": ["a"], "evidence_refs": [["r", "v"]],
              "next_action": "go", "status": "in_progress"}
    assert M.is_correct(oracle, dict(oracle)) is True


def test_correctness_mismatch_next_action():
    oracle = {"claims": ["a"], "evidence_refs": [], "next_action": "go", "status": "open"}
    got = {**oracle, "next_action": "stop"}
    assert M.is_correct(oracle, got) is False


def test_correctness_order_insensitive_for_sets():
    oracle = {"claims": ["a", "b"], "evidence_refs": [["r", "v"]],
              "next_action": "go", "status": "open"}
    got = {"claims": ["b", "a"], "evidence_refs": [["r", "v"]],
           "next_action": "go", "status": "open"}
    assert M.is_correct(oracle, got) is True


def test_recovery_completeness_ratio():
    assert M.recovery_completeness({"goal", "next"}, {"goal", "next"}) == 1.0
    assert M.recovery_completeness({"goal", "next"}, {"goal"}) == 0.5
    assert M.recovery_completeness(set(), set()) == 1.0    # 無必需欄位 = 完整


def test_authority_reads_distinct():
    assert M.authority_reads(["a", "a", "b"]) == 2         # 重複計一次


def test_assembled_bytes_and_tokens():
    assert M.assembled_bytes("héllo") == len("héllo".encode("utf-8"))
    assert M.estimated_tokens("x" * 8) == 2                # ceil(8/4)
    assert M.estimated_tokens("x" * 9) == 3                # ceil(9/4)


def test_percentiles():
    samples = [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
    assert M.p50(samples) == pytest.approx(M.percentile(samples, 50))
    assert M.p95(samples) >= M.p50(samples)


# ── workload qualification:15% 邊界(either metric)───────────────────

def test_workload_qualifies_at_exactly_15pct_reads():
    # A reads median 100, B 85 → 正好 15% 改善 → qualify
    assert M.workload_qualifies(a_reads=100, b_reads=85, a_bytes=100, b_bytes=100) is True


def test_workload_not_qualify_at_14_99pct():
    assert M.workload_qualifies(a_reads=100, b_reads=85.01, a_bytes=100, b_bytes=100) is False


def test_workload_qualifies_via_bytes_only():
    # reads 沒改善,但 bytes 改善 ≥15% → either metric → qualify
    assert M.workload_qualifies(a_reads=100, b_reads=100, a_bytes=100, b_bytes=80) is True


def test_zero_baseline_equal_is_not_improvement():
    # A=0,B=0 → equal,不算 improved
    assert M.workload_qualifies(a_reads=0, b_reads=0, a_bytes=0, b_bytes=0) is False


# ── p95 gate 邊界:110% / 110.01% ─────────────────────────────────────

def test_p95_gate_at_exactly_110pct_passes():
    assert M.p95_within_budget(a_p95=100.0, b_p95=110.0) is True


def test_p95_gate_just_over_110pct_fails():
    assert M.p95_within_budget(a_p95=100.0, b_p95=110.01) is False


# ── 綜合判定 ─────────────────────────────────────────────────────────

def _perfect_workloads(n_qualify: int):
    """建 7 個 workload 結果:全部正確、100% recovery、無 safety 事件。
    前 n_qualify 個在 reads 改善 15%,其餘持平。"""
    wls = []
    for i in range(7):
        improved = i < n_qualify
        wls.append(M.WorkloadResult(
            name=f"w{i}",
            a_correct=True, b_correct=True,
            a_recovery=1.0, b_recovery=1.0,
            a_reads_median=100, b_reads_median=85 if improved else 100,
            a_bytes_median=100, b_bytes_median=100,
            hard_events=0,
        ))
    return wls


def test_decide_propose_b_when_all_gates_pass():
    wls = _perfect_workloads(4)
    decision = M.decide(wls, a_p95=100.0, b_p95=105.0)
    assert decision.outcome == "propose_b_design"


def test_decide_retain_a_when_only_three_qualify():
    wls = _perfect_workloads(3)
    decision = M.decide(wls, a_p95=100.0, b_p95=105.0)
    assert decision.outcome == "retain_a"                 # <4 qualify


def test_decide_retain_a_when_p95_over_budget():
    wls = _perfect_workloads(4)
    decision = M.decide(wls, a_p95=100.0, b_p95=120.0)
    assert decision.outcome == "retain_a"


def test_decide_invalid_on_any_safety_event():
    wls = _perfect_workloads(4)
    wls[2] = M.WorkloadResult(
        name="w2", a_correct=True, b_correct=True, a_recovery=1.0, b_recovery=1.0,
        a_reads_median=100, b_reads_median=85, a_bytes_median=100, b_bytes_median=100,
        hard_events=1)                                    # 一個 safety 事件
    decision = M.decide(wls, a_p95=100.0, b_p95=105.0)
    assert decision.outcome == "invalid_run"              # 不得 average away


def test_decide_invalid_on_correctness_failure():
    wls = _perfect_workloads(4)
    wls[0] = M.WorkloadResult(
        name="w0", a_correct=True, b_correct=False, a_recovery=1.0, b_recovery=1.0,
        a_reads_median=100, b_reads_median=85, a_bytes_median=100, b_bytes_median=100,
        hard_events=0)
    decision = M.decide(wls, a_p95=100.0, b_p95=105.0)
    assert decision.outcome == "invalid_run"


def test_decide_invalid_on_incomplete_recovery():
    wls = _perfect_workloads(4)
    wls[1] = M.WorkloadResult(
        name="w1", a_correct=True, b_correct=True, a_recovery=1.0, b_recovery=0.5,
        a_reads_median=100, b_reads_median=85, a_bytes_median=100, b_bytes_median=100,
        hard_events=0)
    decision = M.decide(wls, a_p95=100.0, b_p95=105.0)
    assert decision.outcome == "invalid_run"


def test_decide_requires_seven_workloads():
    with pytest.raises(M.MetricsError):
        M.decide(_perfect_workloads(4)[:6], a_p95=100.0, b_p95=105.0)


# ── frozen spec 檔 ───────────────────────────────────────────────────

def test_experiment_spec_is_frozen_and_hashable():
    spec = M.load_spec()
    assert spec["improvement_threshold_pct"] == 15
    assert spec["min_qualifying_workloads"] == 4
    assert spec["p95_budget_pct"] == 110
    assert spec["workload_count"] == 7
    h1 = M.spec_hash()
    h2 = M.spec_hash()
    assert h1 == h2 and len(h1) == 64                     # 穩定 sha256
