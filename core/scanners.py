"""git 與 beacon 唯讀掃描器(part-005;ARCHITECTURE §3.3)。

全唯讀:git 只跑查詢命令;beacon 只讀 .beacon/*.md。全容錯:
非 git 目錄 / 缺 .beacon / 壞檔案 → 部分結果或 None,永不 crash。
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path


def _git(repo: Path, *args: str) -> str | None:
    """跑一個唯讀 git 命令。失敗(非 repo/git 不在/逾時)→ None。"""
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=15)
        return proc.stdout.strip() if proc.returncode == 0 else None
    except (subprocess.TimeoutExpired, OSError):
        return None


def git_scan(repo_path: str | Path) -> dict | None:
    """git 唯讀掃描。非 git 目錄 → None。

    回 {branch, last_commit_at(秒), last_message, recent[3], unpushed}。
    unpushed=None 表示無 upstream(P6:不視為錯誤)。
    """
    repo = Path(repo_path)
    if not repo.exists():
        return None
    if _git(repo, "rev-parse", "--is-inside-work-tree") != "true":
        return None

    log = _git(repo, "log", "--format=%at|%s", "-3")
    recent = []
    for line in (log or "").splitlines():
        ts, _, msg = line.partition("|")
        if ts.isdigit():
            recent.append({"at": int(ts), "message": msg[:120]})

    unpushed_raw = _git(repo, "rev-list", "--count", "@{u}..HEAD")
    return {
        "branch": _git(repo, "branch", "--show-current") or "",
        "last_commit_at": recent[0]["at"] if recent else None,
        "last_message": recent[0]["message"] if recent else None,
        "recent": recent,
        "unpushed": int(unpushed_raw) if unpushed_raw and unpushed_raw.isdigit() else None,
    }


_FIELD = re.compile(r"^(Part|Slice|Status):\s*(.+)$", re.M)


def beacon_scan(repo_path: str | Path) -> dict | None:
    """讀 .beacon/CURRENT.md(P7:兩形態——active 有 Part/Slice;planning-only 只有 Status)。

    缺 .beacon 或 CURRENT.md → None(專案沒用 Beacon,不是錯誤)。
    回 {status, part, slice, goal}(缺欄位 = None)。
    """
    current = Path(repo_path) / ".beacon" / "CURRENT.md"
    if not current.exists():
        return None
    try:
        text = current.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None

    fields = {m.group(1).lower(): m.group(2).strip()
              for m in _FIELD.finditer(text)}

    # Goal 段落第一行(active 形態才有)
    goal = None
    m = re.search(r"^## Goal\s*\n+(.+)$", text, re.M)
    if m:
        goal = m.group(1).strip()[:160]

    return {
        "status": fields.get("status"),
        "part": fields.get("part"),
        "slice": fields.get("slice"),
        "goal": goal,
    }
