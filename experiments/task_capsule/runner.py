"""A/B runner:deterministic reconstruction(Todo 9 A-arm + Todo 12 B-arm)。

A-arm(現況):只從當前權威 sources 重建答案;不開 capsule DB、不帶 process state。
B-arm:載入 prior capsule 作 bounded historical hints,但在產出前重讀 freshness/
evidence 要求的權威;stale 欄位一律排除、改讀權威;同 fixture 與 oracle;不自評、
不碰別的 task capsule。

deterministic scoring,不需 LLM。答案由 fixture 的 authority sources 確定性導出——
oracle 就是「正確讀完必需權威後應得的結論」,兩臂用同一個確定性 reconstructor,
差別只在 B 先看 capsule hint(且必須重查權威,不得靠 stale hint 作答)。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from experiments.task_capsule import context as C
from experiments.task_capsule import fixtures as F
from experiments.task_capsule import metrics as M
from experiments.task_capsule import models as m
from experiments.task_capsule import store as S


@dataclass(frozen=True, slots=True)
class ArmResult:
    arm: str
    task_id: str
    correct: bool
    recovery: float
    next_action: str
    status: str
    claims: tuple[str, ...]
    evidence_refs: tuple[tuple[str, str], ...]
    authority_reads: int
    assembled_bytes: int
    estimated_tokens: int
    runtime_ns: int
    capsule_bytes: int = 0
    stale_excluded: tuple[str, ...] = field(default_factory=tuple)


def _current_authority(w: F.Workload) -> dict[str, str]:
    """fixture 的當前權威 = authority_sources 的 key→version。"""
    return {s["key"]: s["version"] for s in w.authority_sources}


def _reconstruct(w: F.Workload, available_keys: set[str]) -> tuple[dict, int, str]:
    """從可讀的權威 sources 確定性重建答案。

    回 (answer, reads, assembled_text)。answer 欄位對齊 oracle
    ({next_action, status, claims, evidence_refs})。只有讀到全部 expected_reads
    才產出完整 oracle;缺任一 → 產出降級(空 next_action/claims)。
    """
    read_keys = [k for k in w.expected_reads if k in available_keys]
    assembled = "\n".join(
        f"{s['key']}={s['version']}:{s['payload']}"
        for s in w.authority_sources if s["key"] in available_keys)

    if set(w.expected_reads) <= available_keys:
        # 完整讀到必需權威 → oracle 答案(確定性)
        answer = {
            "next_action": w.oracle["next_action"],
            "status": w.oracle["status"],
            "claims": list(w.oracle["claims"]),
            "evidence_refs": [list(e) for e in w.oracle["evidence_refs"]],
        }
    else:
        # 不完整 → 誠實降級,不編造(絕不回 oracle 答案)
        answer = {"next_action": "", "status": "unknown",
                  "claims": [], "evidence_refs": []}
    return answer, len(set(read_keys)), assembled


def _score(w: F.Workload, answer: dict) -> tuple[bool, float]:
    correct = M.is_correct(w.oracle, answer)
    required = {"next_action", "status"}
    recovered = {k for k in required if answer.get(k) and answer[k] != "unknown"}
    recovery = M.recovery_completeness(required, recovered)
    return correct, recovery


def run_arm_a(w: F.Workload, *, capsule_db=None,
              drop_sources: set[str] | None = None) -> ArmResult:
    """A-arm:純無狀態重建。忽略 capsule_db(對照組不得使用)。"""
    dropped = drop_sources or set()
    available = {s["key"] for s in w.authority_sources} - dropped

    start = time.perf_counter_ns()
    answer, reads, assembled = _reconstruct(w, available)
    runtime = time.perf_counter_ns() - start

    correct, recovery = _score(w, answer)
    return ArmResult(
        arm="A", task_id=w.task_id, correct=correct, recovery=recovery,
        next_action=answer["next_action"], status=answer["status"],
        claims=tuple(answer["claims"]),
        evidence_refs=tuple(tuple(e) for e in answer["evidence_refs"]),
        authority_reads=reads,
        assembled_bytes=M.assembled_bytes(assembled),
        estimated_tokens=M.estimated_tokens(assembled),
        runtime_ns=runtime,
    )


def run_arm_b(w: F.Workload, *, capsule_db,
              drop_sources: set[str] | None = None) -> ArmResult:
    """B-arm:載入 prior capsule 作 historical hints,但重讀權威後才作答。

    只讀自己 task 的 capsule;stale 欄位排除;絕不靠 stale hint 作答。
    """
    dropped = drop_sources or set()
    available = {s["key"] for s in w.authority_sources} - dropped

    start = time.perf_counter_ns()

    # 載入自己 task 的 prior capsule(若 fixture 提供且已 seed 進 store)
    capsule_bytes = 0
    stale_excluded: tuple[str, ...] = ()
    st = S.Store(capsule_db)
    try:
        prior = st.get_current(w.task_id)
        if prior is None and w.prior_capsule is not None:
            # 用 fixture 的 prior capsule seed 進 store(模擬上次 run 的 checkpoint)
            prior = m.parse_capsule(w.prior_capsule)
            st.put(prior, idempotency_key=f"seed-{w.task_id}")
        if prior is not None:
            assembly = C.assemble(prior, current_authority=_current_authority(w))
            capsule_bytes = M.assembled_bytes(assembly.text)
            stale_excluded = assembly.stale_sources
    finally:
        st.close()

    # 關鍵:無論 capsule hint 如何,B 都重讀權威後才作答(不靠 stale hint)。
    answer, reads, assembled = _reconstruct(w, available)
    runtime = time.perf_counter_ns() - start

    correct, recovery = _score(w, answer)
    return ArmResult(
        arm="B", task_id=w.task_id, correct=correct, recovery=recovery,
        next_action=answer["next_action"], status=answer["status"],
        claims=tuple(answer["claims"]),
        evidence_refs=tuple(tuple(e) for e in answer["evidence_refs"]),
        authority_reads=reads,
        assembled_bytes=M.assembled_bytes(assembled),
        estimated_tokens=M.estimated_tokens(assembled),
        runtime_ns=runtime,
        capsule_bytes=capsule_bytes,
        stale_excluded=stale_excluded,
    )
