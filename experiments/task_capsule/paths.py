"""production-path 拒絕 + 可丟棄 workspace 生命週期(Todo 4)。

安全關鍵:實驗絕不觸碰正式資料。任何等於或位於 config 的 production 路徑
(STATE_DB / VAULT_PATH / INDEX_DB / TRANSCRIPT_DIR / DATA_DIR)之下者一律 raise
UnsafePathError。每個 production 路徑顯式列名,使未來 DATA_DIR 搬移不會靜默解防。

experiment root 以 marker 檔標記;disposal 只刪帶 marker 的目錄,拒絕
parent/root/repo/production 目標。
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import config

MARKER_NAME = ".task_capsule_experiment"

# 顯式列名的 production 路徑(work plan 修訂 3:不靠 DATA_DIR 單一屏障)
_PROD_PATHS = (
    config.STATE_DB,
    config.VAULT_PATH,
    config.INDEX_DB,
    config.TRANSCRIPT_DIR,
    config.DATA_DIR,
)


class UnsafePathError(ValueError):
    """路徑落在 production 範圍或不是可安全處置的 experiment root。"""


def _norm(p: Path) -> Path:
    """解析 symlink/junction、正規化;Windows 上大小寫折疊以供比較。"""
    resolved = Path(os.path.abspath(os.path.normpath(str(p))))
    try:
        resolved = resolved.resolve()
    except OSError:
        pass
    if os.name == "nt":
        return Path(os.path.normcase(str(resolved)))
    return resolved


def _is_within(child: Path, parent: Path) -> bool:
    c, pa = _norm(child), _norm(parent)
    if c == pa:
        return True
    try:
        c.relative_to(pa)
        return True
    except ValueError:
        return False


def assert_safe_experiment_path(path: Path) -> Path:
    """拒絕任何等於或位於 production 路徑之下者。回傳正規化後的路徑。"""
    target = _norm(path)
    for prod in _PROD_PATHS:
        if _is_within(target, prod):
            raise UnsafePathError(
                f"refusing production path: {path} is at/under {prod}")
    return target


def _is_dangerous_root(path: Path) -> bool:
    """檔案系統根、磁碟根、或 repo 根等不可刪目標。"""
    norm = _norm(path)
    if norm == _norm(Path(norm.anchor)) if norm.anchor else False:
        return True
    # repo 根(本檔向上三層:experiments/task_capsule/paths.py → repo)
    repo_root = _norm(Path(__file__).resolve().parents[2])
    return norm == repo_root


def prepare_experiment_root(root: Path, *, resume: bool = False) -> Path:
    """建立(或 resume)一個帶 marker 的 experiment root。

    - 拒絕 production 路徑。
    - 已存在且有 marker:resume=True 才接受;否則視同重用需 resume。
    - 已存在且非空且無 marker:拒絕(避免誤用真實目錄)。
    """
    safe = assert_safe_experiment_path(root)
    marker = safe / MARKER_NAME
    if safe.exists():
        if marker.exists():
            if resume:
                return safe
            # 有 marker 但未要求 resume:視為重用,允許(冪等 prepare)
            return safe
        if any(safe.iterdir()):
            raise UnsafePathError(
                f"refusing non-empty non-experiment directory: {root}")
    safe.mkdir(parents=True, exist_ok=True)
    marker.write_text("task_capsule experiment workspace; safe to delete\n",
                      encoding="utf-8")
    return safe


def dispose_experiment_root(root: Path) -> None:
    """只刪已驗證的 experiment root(帶 marker)。冪等。

    拒絕:production 路徑、危險根(fs/disk/repo root)、無 marker 的目錄。
    """
    safe = assert_safe_experiment_path(root)
    if _is_dangerous_root(safe):
        raise UnsafePathError(f"refusing to dispose dangerous root: {root}")
    if not safe.exists():
        return                                            # 冪等:已不存在
    if not (safe / MARKER_NAME).exists():
        raise UnsafePathError(
            f"refusing to dispose directory without experiment marker: {root}")
    shutil.rmtree(safe)
