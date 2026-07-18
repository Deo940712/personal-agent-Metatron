"""七 workload fixture corpus 的 loader + validator(Todo 5)。

fixtures 是合成/去識別化的重播情境;不含私人 transcript。每個 workload 分離
authoritative sources(A/B 共用)與 historical observations,帶 deterministic
oracle、expected reads、forbidden stale/cross-task claims,及 B 專屬 prior capsule
hint(不得洩漏 oracle 答案)。

manifest 與 bundle 檔案位於 `tests/fixtures/task_capsule/`。
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

_FIXTURE_DIR = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "task_capsule"
_MANIFEST = _FIXTURE_DIR / "manifest.json"


class FixtureError(ValueError):
    """fixture corpus 違反契約。"""


@dataclass(frozen=True, slots=True)
class Workload:
    name: str
    task_id: str
    session_ids: tuple[str, ...]
    run_ids: tuple[str, ...]
    authority_sources: list           # [{key, version, payload}]
    observations: list                # [{source_kind, source_id, ...}]
    oracle: dict                      # {next_action, status, claims, evidence_refs}
    expected_reads: list
    forbidden_claims: list
    prior_capsule: dict | None        # B 專屬 hint;None = 無先前 capsule
    changed_authority: dict | None    # {key, version, payload} = stale replay 版本變更


def load_manifest() -> dict:
    return json.loads(_MANIFEST.read_text(encoding="utf-8"))


def _to_workload(entry: dict) -> Workload:
    return Workload(
        name=entry["name"],
        task_id=entry["task_id"],
        session_ids=tuple(entry.get("session_ids", ())),
        run_ids=tuple(entry.get("run_ids", ())),
        authority_sources=entry["authority_sources"],
        observations=entry.get("observations", []),
        oracle=entry["oracle"],
        expected_reads=entry.get("expected_reads", []),
        forbidden_claims=entry.get("forbidden_claims", []),
        prior_capsule=entry.get("prior_capsule"),
        changed_authority=entry.get("changed_authority"),
    )


def load_all() -> list[Workload]:
    manifest = load_manifest()
    out = []
    for name in manifest["workloads"]:
        bundle = json.loads((_FIXTURE_DIR / f"{name}.json").read_text(encoding="utf-8"))
        out.append(_to_workload(bundle))
    return out


def get(name: str) -> Workload:
    for w in load_all():
        if w.name == name:
            return w
    raise FixtureError(f"unknown workload: {name}")


def workload_hash(w: Workload) -> str:
    """穩定內容 hash(排除純識別欄位無關的順序)。"""
    payload = json.dumps({
        "name": w.name,
        "task_id": w.task_id,
        "authority_sources": w.authority_sources,
        "observations": w.observations,
        "oracle": w.oracle,
        "expected_reads": sorted(w.expected_reads),
        "forbidden_claims": sorted(w.forbidden_claims),
        "prior_capsule": w.prior_capsule,
        "changed_authority": w.changed_authority,
    }, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def validate_corpus(workloads: list[Workload]) -> None:
    """拒絕違約 bundle:重複 task id、expected read 非真實 source、答案洩漏進 capsule。"""
    seen_tasks: set[str] = set()
    for w in workloads:
        if w.task_id in seen_tasks:
            raise FixtureError(f"duplicate task_id: {w.task_id}")
        seen_tasks.add(w.task_id)

        keys = {s["key"] for s in w.authority_sources}
        for r in w.expected_reads:
            if r not in keys:
                raise FixtureError(
                    f"{w.name}: expected read {r!r} not an authority source")

        if not w.oracle.get("next_action"):
            raise FixtureError(f"{w.name}: oracle missing next_action")
        if "status" not in w.oracle:
            raise FixtureError(f"{w.name}: oracle missing status")

        # B 的 prior capsule hint 不得含 oracle 的 next_action(防作弊)
        if w.prior_capsule is not None:
            hint = json.dumps(w.prior_capsule, ensure_ascii=False)
            if w.oracle["next_action"] in hint:
                raise FixtureError(
                    f"{w.name}: oracle answer leaked into prior_capsule")
