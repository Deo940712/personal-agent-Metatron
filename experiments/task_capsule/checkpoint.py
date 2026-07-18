"""deterministic checkpoint/promotion(Todo 11)。

接受 canonical observation + current authority bundle → 只 promote 通過驗證的
allowlisted 欄位進 capsule revision。三 trigger(explicit/precompact/stop)呼叫同一
deterministic function,不成為 runtime hook。failed_attempts/open_loops 保留
evidence,不覆蓋已驗證 completion(除非有更新的權威事實)。

失敗一律不留 partial:promotion 只透過 store.put 的原子交易寫入。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from experiments.task_capsule import models as m
from experiments.task_capsule import store as S

# 只允許從 observation payload 提升這些欄位(禁 chain-of-thought/chat 等)
_ALLOWLIST = (
    "goal", "constraints", "decisions", "completed", "failed_attempts",
    "open_loops", "next_action", "evidence_refs", "authority_versions", "status",
)


class CheckpointError(ValueError):
    """checkpoint 前置條件違反(如 task mismatch)。"""


@dataclass(frozen=True, slots=True)
class CheckpointResult:
    promoted: bool
    version: int | None
    reason: str


def _authority_is_fresh(obs: m.Observation, current: dict[str, str]) -> bool:
    """observation payload 引用的 authority_versions 必須全部與 current 相符。"""
    versions = obs.payload.get("authority_versions", [])
    for pair in versions:
        if not isinstance(pair, (list, tuple)) or len(pair) != 2:
            return False
        key, ver = pair
        if current.get(key) != ver:
            return False
    return bool(versions)                                 # 無 authority → 不新鮮


def _build_capsule_dict(obs: m.Observation, task_id: str, version: int,
                        prior: m.Capsule | None) -> dict:
    """從 observation payload 的 allowlisted 欄位組 capsule dict。"""
    p = obs.payload
    now = obs.captured_at
    created = prior.created_at if prior is not None else now
    out = {
        "schema_version": m.SCHEMA_VERSION,
        "task_id": task_id,
        "version": version,
        "created_at": created,
        "updated_at": now,
    }
    for field in _ALLOWLIST:
        if field in p:
            out[field] = p[field]
    # 補預設(models 要求的必填)
    out.setdefault("goal", prior.goal if prior else "")
    out.setdefault("status", "in_progress")
    out.setdefault("next_action", "")
    return out


def checkpoint(db: Path, obs: m.Observation, *, current_authority: dict[str, str],
               idempotency_key: str, trigger: str = "explicit",
               expected_task: str | None = None,
               expected_version: int | None = None) -> CheckpointResult:
    """把一個 observation 提升為 capsule revision(若通過全部驗證)。

    trigger ∈ {explicit, precompact, stop} 只是來源標記;三者走同一路徑。
    """
    if trigger not in ("explicit", "precompact", "stop"):
        raise CheckpointError(f"unknown trigger: {trigger!r}")

    task_id = obs.payload.get("task_id")
    if not isinstance(task_id, str) or not task_id:
        raise CheckpointError("observation payload missing task_id")
    if expected_task is not None and task_id != expected_task:
        raise CheckpointError(
            f"task mismatch: obs={task_id} expected={expected_task}")

    # 必需欄位(unverified observation → 拒絕)
    if not obs.payload.get("next_action"):
        return CheckpointResult(False, None, "missing next_action")

    # authority freshness
    if not _authority_is_fresh(obs, current_authority):
        return CheckpointResult(False, None, "stale or missing authority versions")

    st = S.Store(db)
    try:
        prior = st.get_current(task_id)
        # completion regression guard:已 done 不被 in_progress 舊觀測回退
        if prior is not None and prior.status is m.CapsuleStatus.DONE:
            new_status = obs.payload.get("status", "in_progress")
            if new_status != "done":
                return CheckpointResult(
                    False, prior.version, "refusing to regress completed capsule")

        next_version = (prior.version + 1) if prior is not None else 1
        cas = prior.version if prior is not None else None
        # 呼叫端可覆寫 expected_version(測試 completion regression 用)
        if expected_version is not None:
            cas = expected_version

        try:
            capsule = m.parse_capsule(
                _build_capsule_dict(obs, task_id, next_version, prior))
        except m.CapsuleError as e:
            return CheckpointResult(False, None, f"invalid capsule: {e}")

        try:
            _, ver = st.put(capsule, idempotency_key=idempotency_key,
                            expected_version=cas)
        except S.StaleVersionError as e:
            return CheckpointResult(False, None, f"cas failed: {e}")
        return CheckpointResult(True, ver, f"promoted via {trigger}")
    finally:
        st.close()
