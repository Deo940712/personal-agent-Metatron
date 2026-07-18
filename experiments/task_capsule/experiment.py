"""實驗 orchestrator(Todo 13)。

跑七 workload × 兩臂,每臂 1 warmup(排除)+ N measured samples,paired AB/BA
順序(seed 20260716,執行前持久化)。彙總 median reads/bytes、p50/p95 runtime,
計算凍結決策。abort on safety 失敗。deterministic(除 runtime 外)。

證據匯出到指定 output(呼叫端傳入,通常 .omo/evidence);絕不寫 production。
"""

from __future__ import annotations

import hashlib
import json
import random
import statistics
from pathlib import Path

from experiments.task_capsule import artifacts as A
from experiments.task_capsule import fixtures as F
from experiments.task_capsule import metrics as M
from experiments.task_capsule import runner as R

ORDER_FILE = "pair_order.json"
EXPERIMENT_ID = "part-003.2-slice-001"
CODE_VERSION = "1"


def _fixture_hash() -> str:
    """全 corpus 的穩定 hash(fixture drift 偵測)。"""
    h = hashlib.sha256()
    for w in sorted(F.load_all(), key=lambda x: x.name):
        h.update(F.workload_hash(w).encode("utf-8"))
    return h.hexdigest()


def _pair_order(n: int, seed: int) -> list[str]:
    rng = random.Random(seed)
    return ["AB" if rng.random() < 0.5 else "BA" for _ in range(n)]


def _run_pair(w: F.Workload, order: str, capsule_db: Path) -> tuple:
    """依 AB/BA 順序跑一對 sample。回 (a_result, b_result)。"""
    if order == "AB":
        a = R.run_arm_a(w)
        b = R.run_arm_b(w, capsule_db=capsule_db)
    else:
        b = R.run_arm_b(w, capsule_db=capsule_db)
        a = R.run_arm_a(w)
    return a, b


def _aggregate_arm(results: list) -> dict:
    reads = [r.authority_reads for r in results]
    byts = [r.assembled_bytes for r in results]
    runtimes = [r.runtime_ns for r in results]
    return {
        "sample_count": len(results),
        "correct": all(r.correct for r in results),
        "recovery": min(r.recovery for r in results),
        "authority_reads_median": statistics.median(reads),
        "assembled_bytes_median": statistics.median(byts),
        "runtime_p50": M.p50(runtimes),
        "runtime_p95": M.p95(runtimes),
    }


def _run_core(root: Path, *, measured_samples: int,
              fixture_hash: str) -> dict:
    from experiments.task_capsule import paths as P
    from experiments.task_capsule import store as S

    P.assert_safe_experiment_path(root)                   # 拒絕 production
    workloads = sorted(F.load_all(), key=lambda w: w.name)
    F.validate_corpus(workloads)                          # spec/fixture 完整性

    seed = M.load_spec()["pair_order_seed"]
    orders = _pair_order(measured_samples, seed)
    (root / ORDER_FILE).write_text(
        json.dumps({"seed": seed, "pairs": orders}, ensure_ascii=False, indent=2),
        encoding="utf-8")

    per_workload: dict = {}
    all_samples: list[dict] = []
    hard_events = 0

    for w in workloads:
        capsule_db = root / f"capsule_{w.name}.db"
        S.init(capsule_db)
        a_results, b_results = [], []
        # 1 warmup(排除)+ measured samples
        _run_pair(w, "AB", capsule_db)
        for rep, order in enumerate(orders):
            a, b = _run_pair(w, order, capsule_db)
            a_results.append(a)
            b_results.append(b)
            for arm, res in (("A", a), ("B", b)):
                # forbidden claim 出現 = hard safety event
                for bad in w.forbidden_claims:
                    if bad in res.claims:
                        hard_events += 1
                all_samples.append({
                    "workload": w.name, "arm": arm, "rep": rep,
                    "correct": res.correct, "authority_reads": res.authority_reads,
                    "assembled_bytes": res.assembled_bytes, "runtime_ns": res.runtime_ns,
                })
        per_workload[w.name] = {
            "A": _aggregate_arm(a_results),
            "B": _aggregate_arm(b_results),
        }

    # 組 WorkloadResult 供決策
    wl_results = []
    a_p95s, b_p95s = [], []
    for name, arms in per_workload.items():
        a, b = arms["A"], arms["B"]
        a_p95s.append(a["runtime_p95"])
        b_p95s.append(b["runtime_p95"])
        wl_results.append(M.WorkloadResult(
            name=name,
            a_correct=a["correct"], b_correct=b["correct"],
            a_recovery=a["recovery"], b_recovery=b["recovery"],
            a_reads_median=a["authority_reads_median"],
            b_reads_median=b["authority_reads_median"],
            a_bytes_median=a["assembled_bytes_median"],
            b_bytes_median=b["assembled_bytes_median"],
            hard_events=(1 if hard_events > 0 else 0) if name == workloads[0].name else 0,
        ))

    agg_a_p95 = max(a_p95s) if a_p95s else 0.0
    agg_b_p95 = max(b_p95s) if b_p95s else 0.0
    decision = M.decide(wl_results, a_p95=agg_a_p95, b_p95=agg_b_p95)

    summary = {
        "experiment_id": EXPERIMENT_ID,
        "workload_count": len(workloads),
        "arms": ["A", "B"],
        "measured_samples": measured_samples,
        "spec_hash": M.spec_hash(),
        "fixture_hash": fixture_hash,
        "per_workload": per_workload,
        "aggregate": {"a_p95": agg_a_p95, "b_p95": agg_b_p95},
        "decision": {
            "outcome": decision.outcome,
            "qualifying": decision.qualifying,
            "p95_ok": decision.p95_ok,
            "reason": decision.reason,
        },
    }

    # 原子寫 artifacts 到 experiment root
    ident = A.ExperimentIdentity(
        experiment_id=EXPERIMENT_ID, spec_hash=M.spec_hash(),
        fixture_hash=fixture_hash, code_version=CODE_VERSION)
    writer = A.ArtifactWriter(root, ident)
    writer.finalize(all_samples)
    (root / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2),
        encoding="utf-8")
    return summary


def run_experiment(root: Path, *, measured_samples: int = 30) -> dict:
    return _run_core(root, measured_samples=measured_samples,
                     fixture_hash=_fixture_hash())


def resume_experiment(root: Path, *, override_fixture_hash: str | None = None,
                      measured_samples: int = 30) -> dict:
    """resume:先驗證 identity 未 drift,再重跑。"""
    current_fixture = override_fixture_hash or _fixture_hash()
    ident = A.ExperimentIdentity(
        experiment_id=EXPERIMENT_ID, spec_hash=M.spec_hash(),
        fixture_hash=current_fixture, code_version=CODE_VERSION)
    A.assert_resumable(root, ident)                       # drift → ArtifactError
    return _run_core(root, measured_samples=measured_samples,
                     fixture_hash=current_fixture)


def export_evidence(summary: dict, root: Path, out_dir: Path) -> None:
    """把 summary JSON/CSV 匯出到指定 output(非 production)。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "task-13-ecc-task-capsule-experiment-summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2),
        encoding="utf-8")
    # CSV:per-workload 彙總表
    lines = ["workload,arm,correct,recovery,reads_median,bytes_median,p50_ns,p95_ns"]
    for name in sorted(summary["per_workload"]):
        for arm in ("A", "B"):
            a = summary["per_workload"][name][arm]
            lines.append(
                f"{name},{arm},{a['correct']},{a['recovery']},"
                f"{a['authority_reads_median']},{a['assembled_bytes_median']},"
                f"{a['runtime_p50']},{a['runtime_p95']}")
    (out_dir / "task-13-ecc-task-capsule-experiment-summary.csv").write_text(
        "\n".join(lines) + "\n", encoding="utf-8")
