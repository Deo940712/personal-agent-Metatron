"""凍結 metrics + thresholds + 判定語意(Todo 6)。

規則在看結果前凍結(work plan Decision 11/14/15);看結果後不得改。
correctness/recovery/authority reads/assembled bytes/tokens/percentiles 皆
deterministic;無 LLM。任何 hard 事件(stale/leakage/safety/idempotency/
concurrency)>0 即 invalid,不得 average away。
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path

_SPEC_PATH = Path(__file__).with_name("experiment_spec.json")


class MetricsError(ValueError):
    """metric 計算或判定的前置條件違反。"""


# ── 個別 metric ──────────────────────────────────────────────────────

def _normalize(answer: dict) -> dict:
    """把 correctness 欄位正規化:set-semantics 欄位排序,其餘保留。"""
    spec = load_spec()
    set_fields = set(spec["set_semantics_fields"])
    out: dict = {}
    for key in spec["correctness_fields"]:
        val = answer.get(key)
        if key in set_fields and isinstance(val, list):
            out[key] = sorted(json.dumps(v, ensure_ascii=False, sort_keys=True)
                              for v in val)
        else:
            out[key] = val
    return out


def is_correct(oracle: dict, got: dict) -> bool:
    """normalized {claims, evidence_refs, next_action, status} 完全相等。"""
    return _normalize(oracle) == _normalize(got)


def recovery_completeness(required: set, recovered: set) -> float:
    """命中必需 oracle 欄位 / 必需總數。無必需 = 完整(1.0)。"""
    if not required:
        return 1.0
    return len(required & recovered) / len(required)


def authority_reads(opened: list[str]) -> int:
    """實際開啟的 distinct 權威 artifact 數(重複同一個計一次)。"""
    return len(set(opened))


def assembled_bytes(text: str) -> int:
    return len(text.encode("utf-8"))


def estimated_tokens(text: str) -> int:
    """啟發式:ceil(utf-8 bytes / 4)。明確非 provider tokenizer。"""
    per = load_spec()["token_bytes_per_token"]
    return math.ceil(assembled_bytes(text) / per)


def percentile(samples: list[float], pct: float) -> float:
    """線性插值百分位(nearest-rank 的連續版;deterministic)。"""
    if not samples:
        raise MetricsError("percentile of empty samples")
    ordered = sorted(samples)
    if len(ordered) == 1:
        return float(ordered[0])
    rank = (pct / 100.0) * (len(ordered) - 1)
    lo = math.floor(rank)
    hi = math.ceil(rank)
    if lo == hi:
        return float(ordered[lo])
    frac = rank - lo
    return float(ordered[lo] + (ordered[hi] - ordered[lo]) * frac)


def p50(samples: list[float]) -> float:
    return percentile(samples, 50)


def p95(samples: list[float]) -> float:
    return percentile(samples, 95)


# ── qualification / gate 邊界 ────────────────────────────────────────

def _improved(a: float, b: float, threshold_pct: float) -> bool:
    """b 相對 a 改善 ≥ threshold%。a==0:只有 b<a 不可能,故 equal 不算改善。"""
    if a <= 0:
        return False                                      # zero baseline:equal, not improved
    return (a - b) / a >= threshold_pct / 100.0 - 1e-9    # 容忍浮點


def workload_qualifies(*, a_reads: float, b_reads: float,
                       a_bytes: float, b_bytes: float) -> bool:
    """either metric(authority reads 或 assembled bytes)改善 ≥15% → qualify。"""
    threshold = load_spec()["improvement_threshold_pct"]
    return (_improved(a_reads, b_reads, threshold)
            or _improved(a_bytes, b_bytes, threshold))


def p95_within_budget(*, a_p95: float, b_p95: float) -> bool:
    """aggregate B p95 ≤ budget% of A p95。"""
    budget = load_spec()["p95_budget_pct"] / 100.0
    return b_p95 <= a_p95 * budget + 1e-9


# ── workload 結果 + 綜合判定 ─────────────────────────────────────────

@dataclass(frozen=True, slots=True)
class WorkloadResult:
    name: str
    a_correct: bool
    b_correct: bool
    a_recovery: float
    b_recovery: float
    a_reads_median: float
    b_reads_median: float
    a_bytes_median: float
    b_bytes_median: float
    hard_events: int


@dataclass(frozen=True, slots=True)
class Decision:
    outcome: str
    qualifying: int
    p95_ok: bool
    reason: str


def decide(workloads: list[WorkloadResult], *, a_p95: float, b_p95: float) -> Decision:
    """凍結門檻判定。outcome ∈ {retain_a, propose_b_design, invalid_run, inconclusive}。"""
    spec = load_spec()
    if len(workloads) != spec["workload_count"]:
        raise MetricsError(
            f"expected {spec['workload_count']} workloads, got {len(workloads)}")

    # hard fail:任一 safety 事件、correctness 失敗、recovery < 100% → invalid
    for w in workloads:
        if w.hard_events > 0:
            return Decision("invalid_run", 0, False,
                            f"hard safety event in {w.name}")
        if not (w.a_correct and w.b_correct):
            return Decision("invalid_run", 0, False,
                            f"correctness failure in {w.name}")
        if w.a_recovery < 1.0 or w.b_recovery < 1.0:
            return Decision("invalid_run", 0, False,
                            f"incomplete recovery in {w.name}")

    qualifying = sum(
        1 for w in workloads if workload_qualifies(
            a_reads=w.a_reads_median, b_reads=w.b_reads_median,
            a_bytes=w.a_bytes_median, b_bytes=w.b_bytes_median))
    p95_ok = p95_within_budget(a_p95=a_p95, b_p95=b_p95)

    if qualifying >= spec["min_qualifying_workloads"] and p95_ok:
        return Decision("propose_b_design", qualifying, p95_ok,
                        "all gates passed")
    reason = []
    if qualifying < spec["min_qualifying_workloads"]:
        reason.append(f"only {qualifying}/{spec['workload_count']} qualify")
    if not p95_ok:
        reason.append("p95 over budget")
    return Decision("retain_a", qualifying, p95_ok, "; ".join(reason))


# ── frozen spec 讀取 + hash ──────────────────────────────────────────

def load_spec() -> dict:
    return json.loads(_SPEC_PATH.read_text(encoding="utf-8"))


def spec_hash() -> str:
    """凍結 spec 的 sha256(bytes-level);記錄於 summary 供 drift 偵測。"""
    return hashlib.sha256(_SPEC_PATH.read_bytes()).hexdigest()
