"""atomic artifact writing + resumable identity(Todo 10)。

原子寫 raw JSON / normalized CSV / manifest / hashes / environment metadata
(temp file + os.replace,永不 partial marker)。resume 只在 experiment ID /
spec hash / fixture manifest hash / code version 全符時允許。證據只寫進已驗證
的 experiment root(拒絕 production 路徑)。
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import platform
import sys
from dataclasses import dataclass
from pathlib import Path

from experiments.task_capsule import paths as P

RAW_JSON = "raw_samples.json"
SUMMARY_CSV = "summary.csv"
MANIFEST = "run_manifest.json"

# CSV 欄位固定順序(normalized,deterministic)
_CSV_FIELDS = ("workload", "arm", "rep", "correct", "authority_reads",
               "assembled_bytes", "runtime_ns")


class ArtifactError(ValueError):
    """artifact 寫入或 resume identity 違反。"""


@dataclass(frozen=True, slots=True)
class ExperimentIdentity:
    experiment_id: str
    spec_hash: str
    fixture_hash: str
    code_version: str


def _atomic_write_text(path: Path, text: str) -> None:
    """temp file + fsync + os.replace:永不留半寫的最終檔。"""
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)                                 # 原子;失敗則 tmp 留、final 不變


def _environment() -> dict:
    return {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "machine": platform.machine(),
    }


def _normalize_samples(samples: list[dict]) -> list[dict]:
    """穩定排序:workload → arm → rep。"""
    return sorted(samples, key=lambda s: (s["workload"], s["arm"], s["rep"]))


def _samples_to_csv(samples: list[dict]) -> str:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=_CSV_FIELDS, extrasaction="ignore",
                            lineterminator="\n")
    writer.writeheader()
    for s in _normalize_samples(samples):
        writer.writerow({k: s.get(k) for k in _CSV_FIELDS})
    return buf.getvalue()


class ArtifactWriter:
    """把 A/B run 的樣本原子寫進已驗證 experiment root。"""

    def __init__(self, root: Path, identity: ExperimentIdentity) -> None:
        self._root = P.assert_safe_experiment_path(root)  # 拒絕 production
        self._identity = identity
        self._buffered: list[dict] = []

    def write_sample(self, sample: dict) -> None:
        self._buffered.append(sample)

    def finalize(self, samples: list[dict]) -> None:
        """原子寫 raw JSON + normalized CSV + manifest。"""
        normalized = _normalize_samples(samples)
        raw_text = json.dumps(normalized, ensure_ascii=False, sort_keys=True,
                              indent=2)
        csv_text = _samples_to_csv(samples)

        manifest = {
            "experiment_id": self._identity.experiment_id,
            "spec_hash": self._identity.spec_hash,
            "fixture_hash": self._identity.fixture_hash,
            "code_version": self._identity.code_version,
            "sample_count": len(normalized),
            "raw_sha256": hashlib.sha256(raw_text.encode("utf-8")).hexdigest(),
            "csv_sha256": hashlib.sha256(csv_text.encode("utf-8")).hexdigest(),
            "environment": _environment(),
        }
        manifest_text = json.dumps(manifest, ensure_ascii=False, sort_keys=True,
                                   indent=2)

        # 三檔皆原子寫;CSV 先寫(測試模擬 replace 失敗時,final 不被污染)
        _atomic_write_text(self._root / SUMMARY_CSV, csv_text)
        _atomic_write_text(self._root / RAW_JSON, raw_text)
        _atomic_write_text(self._root / MANIFEST, manifest_text)


def assert_resumable(root: Path, identity: ExperimentIdentity) -> None:
    """resume 前檢查 identity 全符;任一不符 → ArtifactError。"""
    manifest_path = P.assert_safe_experiment_path(root) / MANIFEST
    if not manifest_path.exists():
        raise ArtifactError("no run manifest to resume from")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for key, want in (
        ("experiment_id", identity.experiment_id),
        ("spec_hash", identity.spec_hash),
        ("fixture_hash", identity.fixture_hash),
        ("code_version", identity.code_version),
    ):
        if manifest.get(key) != want:
            raise ArtifactError(
                f"resume identity mismatch on {key}: "
                f"stored={manifest.get(key)!r} want={want!r}")
