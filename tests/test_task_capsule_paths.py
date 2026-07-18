"""part-003.2-slice-001 Todo 4:production-path 拒絕 + 可丟棄 workspace 生命週期。

安全關鍵:實驗只能在明確指定的非正式路徑或 temp directory 運作。任何等於或位於
production 路徑(config.STATE_DB / VAULT_PATH / INDEX_DB / TRANSCRIPT_DIR / DATA_DIR)
之下者一律拒絕,fail closed。disposal 只刪已驗證的 experiment root,拒絕
parent/root/repo 路徑。
"""

import hashlib

import pytest

import config
from experiments.task_capsule import paths as P


@pytest.fixture()
def exp_root(tmp_path):
    return tmp_path / "exp_ws"


# ── 建立/驗證 experiment root ─────────────────────────────────────────

def test_prepare_creates_experiment_root(exp_root):
    root = P.prepare_experiment_root(exp_root)
    assert root.exists() and root.is_dir()
    assert (root / P.MARKER_NAME).exists()                # 標記檔證明是實驗 root


def test_prepare_is_idempotent_when_marker_present(exp_root):
    P.prepare_experiment_root(exp_root)
    # 第二次(resume 語意):marker 相符不報錯
    again = P.prepare_experiment_root(exp_root, resume=True)
    assert again == exp_root.resolve()


def test_prepare_rejects_nonempty_without_resume(exp_root):
    exp_root.mkdir(parents=True)
    (exp_root / "stray.txt").write_text("x", encoding="utf-8")
    with pytest.raises(P.UnsafePathError):
        P.prepare_experiment_root(exp_root)               # 非空且無 marker → 拒絕


# ── 拒絕 production 路徑(逐一顯式)─────────────────────────────────────

@pytest.mark.parametrize("prod", [
    config.STATE_DB,
    config.VAULT_PATH,
    config.INDEX_DB,
    config.TRANSCRIPT_DIR,
    config.DATA_DIR,
])
def test_reject_exact_production_paths(prod):
    with pytest.raises(P.UnsafePathError):
        P.assert_safe_experiment_path(prod)


def test_reject_child_of_data_dir():
    child = config.DATA_DIR / "sub" / "exp.db"
    with pytest.raises(P.UnsafePathError):
        P.assert_safe_experiment_path(child)


def test_reject_data_dir_case_insensitive_on_windows(monkeypatch):
    """Windows 路徑大小寫不敏感:大寫變體仍須被擋。"""
    import os
    if os.name != "nt":
        pytest.skip("windows-only casing check")
    variant = config.DATA_DIR.parent / config.DATA_DIR.name.upper() / "x.db"
    with pytest.raises(P.UnsafePathError):
        P.assert_safe_experiment_path(variant)


def test_reject_relative_traversal_into_data_dir():
    sneaky = config.DATA_DIR / ".." / config.DATA_DIR.name / "x.db"
    with pytest.raises(P.UnsafePathError):
        P.assert_safe_experiment_path(sneaky)


def test_accept_temp_path(tmp_path):
    # 不拋 = 通過
    P.assert_safe_experiment_path(tmp_path / "exp.db")


# ── disposal:只刪已驗證 root,拒絕危險目標 ────────────────────────────

def test_dispose_removes_only_experiment_root(exp_root):
    root = P.prepare_experiment_root(exp_root)
    (root / "data.db").write_text("x", encoding="utf-8")
    P.dispose_experiment_root(root)
    assert not root.exists()


def test_dispose_is_idempotent(exp_root):
    root = P.prepare_experiment_root(exp_root)
    P.dispose_experiment_root(root)
    P.dispose_experiment_root(root)                       # 再刪不炸


def test_dispose_refuses_path_without_marker(tmp_path):
    plain = tmp_path / "not_an_exp"
    plain.mkdir()
    (plain / "important.txt").write_text("keep", encoding="utf-8")
    with pytest.raises(P.UnsafePathError):
        P.dispose_experiment_root(plain)                  # 無 marker → 拒刪
    assert (plain / "important.txt").exists()


@pytest.mark.parametrize("hostile", [
    config.DATA_DIR,
    config.STATE_DB,
])
def test_dispose_refuses_production_target(hostile):
    with pytest.raises(P.UnsafePathError):
        P.dispose_experiment_root(hostile)


def test_dispose_refuses_repo_root(tmp_path, monkeypatch):
    # 拒刪 repo 根/檔案系統根(即使誤傳)
    with pytest.raises(P.UnsafePathError):
        P.dispose_experiment_root(tmp_path.anchor and type(tmp_path)(tmp_path.anchor))


# ── production 檔案不受實驗影響(hash 不變)────────────────────────────

def test_production_files_untouched_by_prepare_dispose(exp_root, tmp_path):
    sentinel = tmp_path / "prod_sentinel.db"
    sentinel.write_bytes(b"production data")
    before = hashlib.sha256(sentinel.read_bytes()).hexdigest()
    root = P.prepare_experiment_root(exp_root)
    (root / "x.db").write_text("y", encoding="utf-8")
    P.dispose_experiment_root(root)
    after = hashlib.sha256(sentinel.read_bytes()).hexdigest()
    assert before == after
