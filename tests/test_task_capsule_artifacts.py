"""part-003.2-slice-001 Todo 10:atomic artifact writing + resumable identity。

原子寫 raw JSON / normalized CSV / manifest / hashes / metadata(temp file + replace,
永不 partial marker)。resume 只在 experiment ID / spec hash / fixture manifest hash /
code version / arm / repetition count 全符時允許;不符即拒絕或要求新空 root。
證據只寫進已驗證 experiment root,不碰 production。
"""

import json

import pytest

from experiments.task_capsule import artifacts as A
from experiments.task_capsule import paths as P


@pytest.fixture()
def root(tmp_path):
    return P.prepare_experiment_root(tmp_path / "exp")


def _identity(**over):
    base = dict(experiment_id="exp-1", spec_hash="s" * 64,
                fixture_hash="f" * 64, code_version="v1")
    base.update(over)
    return A.ExperimentIdentity(**base)


def _sample(name="w0", arm="A", rep=0):
    return {"workload": name, "arm": arm, "rep": rep, "correct": True,
            "authority_reads": 3, "assembled_bytes": 120, "runtime_ns": 500}


# ── atomic write:成功路徑 ────────────────────────────────────────────

def test_write_run_creates_files(root):
    w = A.ArtifactWriter(root, _identity())
    w.write_sample(_sample())
    w.finalize([_sample()])
    assert (root / A.RAW_JSON).exists()
    assert (root / A.SUMMARY_CSV).exists()
    assert (root / A.MANIFEST).exists()


def test_manifest_records_identity_and_hashes(root):
    ident = _identity()
    w = A.ArtifactWriter(root, ident)
    w.write_sample(_sample())
    w.finalize([_sample()])
    manifest = json.loads((root / A.MANIFEST).read_text(encoding="utf-8"))
    assert manifest["experiment_id"] == "exp-1"
    assert manifest["spec_hash"] == "s" * 64
    assert manifest["fixture_hash"] == "f" * 64
    assert "environment" in manifest and "python" in manifest["environment"]


def test_no_partial_marker_on_success(root):
    w = A.ArtifactWriter(root, _identity())
    w.write_sample(_sample())
    w.finalize([_sample()])
    assert not any(p.name.endswith(".tmp") for p in root.iterdir())


# ── atomic:中斷(replace 前)不留半寫檔 ──────────────────────────────

def test_interrupted_before_replace_leaves_no_corrupt_final(root, monkeypatch):
    w = A.ArtifactWriter(root, _identity())
    w.write_sample(_sample())
    # 模擬 finalize 中途炸(在 replace 前)
    import os
    orig_replace = os.replace
    calls = {"n": 0}
    def boom(src, dst):
        calls["n"] += 1
        raise OSError("simulated crash before replace")
    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError):
        w.finalize([_sample()])
    monkeypatch.setattr(os, "replace", orig_replace)
    # 最終檔不存在或未被半寫污染(atomic 保證)
    assert not (root / A.SUMMARY_CSV).exists() or \
        (root / A.SUMMARY_CSV).read_text(encoding="utf-8").strip() != ""


# ── normalized CSV/JSON 穩定排序 ─────────────────────────────────────

def test_csv_and_json_stable_ordering(root):
    samples = [_sample("wb", "B", 1), _sample("wa", "A", 0), _sample("wa", "A", 1)]
    w = A.ArtifactWriter(root, _identity())
    for s in samples:
        w.write_sample(s)
    w.finalize(samples)
    csv1 = (root / A.SUMMARY_CSV).read_text(encoding="utf-8")

    # 重寫同資料(新 root)→ 位元組相同(deterministic)
    r2 = P.prepare_experiment_root(root.parent / "exp2")
    w2 = A.ArtifactWriter(r2, _identity())
    for s in reversed(samples):                           # 不同輸入順序
        w2.write_sample(s)
    w2.finalize(list(reversed(samples)))
    csv2 = (r2 / A.SUMMARY_CSV).read_text(encoding="utf-8")
    assert csv1 == csv2                                   # normalized 排序一致


# ── resume:identity 全符 → 允許 ─────────────────────────────────────

def test_resume_allowed_when_identity_matches(root):
    ident = _identity()
    w = A.ArtifactWriter(root, ident)
    w.write_sample(_sample())
    w.finalize([_sample()])
    # 用相同 identity resume → OK
    A.assert_resumable(root, ident)                       # 不拋 = 允許


def test_resume_rejected_on_spec_hash_mismatch(root):
    w = A.ArtifactWriter(root, _identity())
    w.finalize([_sample()])
    with pytest.raises(A.ArtifactError):
        A.assert_resumable(root, _identity(spec_hash="X" * 64))


def test_resume_rejected_on_fixture_hash_mismatch(root):
    w = A.ArtifactWriter(root, _identity())
    w.finalize([_sample()])
    with pytest.raises(A.ArtifactError):
        A.assert_resumable(root, _identity(fixture_hash="Y" * 64))


def test_resume_rejected_on_code_version_mismatch(root):
    w = A.ArtifactWriter(root, _identity())
    w.finalize([_sample()])
    with pytest.raises(A.ArtifactError):
        A.assert_resumable(root, _identity(code_version="v2"))


def test_resume_rejected_on_experiment_id_mismatch(root):
    w = A.ArtifactWriter(root, _identity())
    w.finalize([_sample()])
    with pytest.raises(A.ArtifactError):
        A.assert_resumable(root, _identity(experiment_id="other"))


# ── 不寫進 production ────────────────────────────────────────────────

def test_writer_rejects_production_root():
    import config
    with pytest.raises(P.UnsafePathError):
        A.ArtifactWriter(config.DATA_DIR, _identity())
