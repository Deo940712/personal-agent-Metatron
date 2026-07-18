"""Task Capsule + canonical observation 的 typed 資料契約(Todo 3)。

parse-then-validate:未知 JSON-like 輸入解析成 validated 型別,壞的一律
raise CapsuleError。標準庫 frozen dataclass + StrEnum,無 Pydantic/第三方依賴。

契約邊界(work plan Decisions 4-7,MEM-08):
- Capsule 只保存結構化 checkpoint + evidence reference;禁 chain-of-thought/完整聊天。
- Observation 帶 provenance(source kind/id、captured_at、authority class、版本/hash);
  observation 本身非權威,只有 deterministic validation 可 promote 進 capsule revision。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum

SCHEMA_VERSION = 1
MAX_FIELD_CHARS = 2000
MAX_LIST_ITEMS = 200
# epoch 合理區間(對齊 core/proposals 的 EPOCH_MIN/MAX 精神:2000-01-01 ~ 2100-01-01)
EPOCH_MIN = 946_684_800
EPOCH_MAX = 4_102_444_800


class CapsuleError(ValueError):
    """capsule/observation 契約層驗證失敗。"""


class CapsuleStatus(StrEnum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    DONE = "done"
    CANCELLED = "cancelled"


class AuthorityClass(StrEnum):
    AUTHORITATIVE = "authoritative"
    OBSERVATIONAL = "observational"


@dataclass(frozen=True, slots=True)
class Capsule:
    """最小 Task Capsule。欄位固定;無 transcript/chain-of-thought/raw prompt。"""

    schema_version: int
    task_id: str
    version: int
    status: CapsuleStatus
    goal: str
    constraints: tuple[str, ...]
    decisions: tuple[str, ...]
    completed: tuple[str, ...]
    failed_attempts: tuple[str, ...]
    open_loops: tuple[str, ...]
    next_action: str
    evidence_refs: tuple[tuple[str, str], ...]        # (ref_id, version_or_hash)
    authority_versions: tuple[tuple[str, str], ...]   # (source_key, version_or_hash)
    created_at: int
    updated_at: int


@dataclass(frozen=True, slots=True)
class Observation:
    """canonical observation snapshot。observational,非權威。"""

    source_kind: str
    source_id: str
    captured_at: int
    authority_class: AuthorityClass
    version_or_hash: str
    payload: dict


# ── 驗證輔助 ─────────────────────────────────────────────────────────

def _req_str(raw: dict, key: str) -> str:
    val = raw.get(key)
    if not isinstance(val, str) or not val.strip():
        raise CapsuleError(f"{key} must be a non-empty string")
    if len(val) > MAX_FIELD_CHARS:
        raise CapsuleError(f"{key} exceeds {MAX_FIELD_CHARS} chars")
    return val


def _req_int(raw: dict, key: str) -> int:
    val = raw.get(key)
    if isinstance(val, bool) or not isinstance(val, int):   # bool 是 int 子類,排除
        raise CapsuleError(f"{key} must be int, got {type(val).__name__}")
    return val


def _epoch(raw: dict, key: str) -> int:
    val = _req_int(raw, key)
    if not (EPOCH_MIN <= val <= EPOCH_MAX):
        raise CapsuleError(f"{key} out of epoch range: {val}")
    return val


def _str_tuple(raw: dict, key: str) -> tuple[str, ...]:
    val = raw.get(key, ())
    if not isinstance(val, (list, tuple)):
        raise CapsuleError(f"{key} must be a list")
    items = list(val)
    if len(items) > MAX_LIST_ITEMS:
        raise CapsuleError(f"{key} too long (>{MAX_LIST_ITEMS})")
    for it in items:
        if not isinstance(it, str) or not it.strip():
            raise CapsuleError(f"{key} items must be non-empty strings")
        if len(it) > MAX_FIELD_CHARS:
            raise CapsuleError(f"{key} item exceeds {MAX_FIELD_CHARS} chars")
    if len(set(items)) != len(items):
        raise CapsuleError(f"{key} contains duplicates")
    return tuple(items)


def _pair_tuple(raw: dict, key: str) -> tuple[tuple[str, str], ...]:
    val = raw.get(key, ())
    if not isinstance(val, (list, tuple)):
        raise CapsuleError(f"{key} must be a list")
    out: list[tuple[str, str]] = []
    for it in val:
        if not isinstance(it, (list, tuple)) or len(it) != 2:
            raise CapsuleError(f"{key} items must be [ref, version] pairs")
        a, b = it
        if not isinstance(a, str) or not a.strip() or not isinstance(b, str) or not b.strip():
            raise CapsuleError(f"{key} pair members must be non-empty strings")
        out.append((a, b))
    if len(out) > MAX_LIST_ITEMS:
        raise CapsuleError(f"{key} too long (>{MAX_LIST_ITEMS})")
    if len({p[0] for p in out}) != len(out):
        raise CapsuleError(f"{key} has duplicate ref ids")
    return tuple(out)


# ── capsule parse / serialize ────────────────────────────────────────

def parse_capsule(raw: dict) -> Capsule:
    """dict → validated Capsule。缺欄/型別錯/違約 → CapsuleError。"""
    if not isinstance(raw, dict):
        raise CapsuleError("capsule must be an object")

    schema_version = _req_int(raw, "schema_version")
    if schema_version != SCHEMA_VERSION:
        raise CapsuleError(f"unknown schema_version: {schema_version}")

    version = _req_int(raw, "version")
    if version < 1:
        raise CapsuleError(f"version must be >= 1: {version}")

    status_raw = raw.get("status")
    try:
        status = CapsuleStatus(status_raw)
    except ValueError as e:
        raise CapsuleError(f"invalid status: {status_raw!r}") from e

    completed = _str_tuple(raw, "completed")
    evidence_refs = _pair_tuple(raw, "evidence_refs")
    if completed and not evidence_refs:
        raise CapsuleError("completed claims require evidence_refs")

    created_at = _epoch(raw, "created_at")
    updated_at = _epoch(raw, "updated_at")
    if updated_at < created_at:
        raise CapsuleError("updated_at cannot precede created_at")

    return Capsule(
        schema_version=schema_version,
        task_id=_req_str(raw, "task_id"),
        version=version,
        status=status,
        goal=_req_str(raw, "goal"),
        constraints=_str_tuple(raw, "constraints"),
        decisions=_str_tuple(raw, "decisions"),
        completed=completed,
        failed_attempts=_str_tuple(raw, "failed_attempts"),
        open_loops=_str_tuple(raw, "open_loops"),
        next_action=_req_str(raw, "next_action"),
        evidence_refs=evidence_refs,
        authority_versions=_pair_tuple(raw, "authority_versions"),
        created_at=created_at,
        updated_at=updated_at,
    )


def _capsule_to_dict(c: Capsule) -> dict:
    return {
        "schema_version": c.schema_version,
        "task_id": c.task_id,
        "version": c.version,
        "status": str(c.status),
        "goal": c.goal,
        "constraints": list(c.constraints),
        "decisions": list(c.decisions),
        "completed": list(c.completed),
        "failed_attempts": list(c.failed_attempts),
        "open_loops": list(c.open_loops),
        "next_action": c.next_action,
        "evidence_refs": [list(p) for p in c.evidence_refs],
        "authority_versions": [list(p) for p in c.authority_versions],
        "created_at": c.created_at,
        "updated_at": c.updated_at,
    }


def to_canonical_json(c: Capsule) -> str:
    """穩定序列化:sort_keys 保證 deterministic;ensure_ascii=False 保中文可讀。"""
    return json.dumps(_capsule_to_dict(c), ensure_ascii=False,
                      sort_keys=True, separators=(",", ":"))


def from_canonical_json(text: str) -> dict:
    obj = json.loads(text)
    if not isinstance(obj, dict):
        raise CapsuleError("canonical json must decode to an object")
    return obj


# ── observation parse / serialize ────────────────────────────────────

def parse_observation(raw: dict) -> Observation:
    if not isinstance(raw, dict):
        raise CapsuleError("observation must be an object")
    ac_raw = raw.get("authority_class")
    try:
        authority_class = AuthorityClass(ac_raw)
    except ValueError as e:
        raise CapsuleError(f"invalid authority_class: {ac_raw!r}") from e
    payload = raw.get("payload")
    if not isinstance(payload, dict):
        raise CapsuleError("observation payload must be an object")
    return Observation(
        source_kind=_req_str(raw, "source_kind"),
        source_id=_req_str(raw, "source_id"),
        captured_at=_epoch(raw, "captured_at"),
        authority_class=authority_class,
        version_or_hash=_req_str(raw, "version_or_hash"),
        payload=payload,
    )


def observation_canonical_json(o: Observation) -> str:
    return json.dumps({
        "source_kind": o.source_kind,
        "source_id": o.source_id,
        "captured_at": o.captured_at,
        "authority_class": str(o.authority_class),
        "version_or_hash": o.version_or_hash,
        "payload": o.payload,
    }, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
