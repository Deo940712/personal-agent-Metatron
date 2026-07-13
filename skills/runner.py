"""Skill 執行器(part-004;ARCHITECTURE §6.5)。

跑 sync skill 的管線步驟(子行程),捕捉結果寫 DB1(cursors + agent_runs)。
skill 本體是黑箱(threads-sync 自帶 state.db/config);整合面只有:
- 環境變數覆蓋(THREADS_SYNC_VAULT → config.VAULT_PATH 等)
- exit code / stdout 關鍵字 → status 判定(ok / login_expired / error)

用法:
    python -m skills.runner threads_sync [--steps sync,threads,media,classify,moc]
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

import config
from core import stm

SKILLS_DIR = Path(__file__).resolve().parent

# threads-sync 的五步驟(依 README 順序;鍵 = --steps 用短名)
THREADS_SYNC_STEPS = {
    "sync": "sync.py",
    "threads": "sync_threads.py",
    "media": "sync_media.py",
    "classify": "classify.py",
    "moc": "build_moc.py",
}

# stdout/stderr 關鍵字 → login_expired 判定(threads-sync 的主要壞掉模式)
LOGIN_EXPIRED_MARKERS = ("login_expired", "not authenticated", "anti_scripting",
                         "xfb_auth_platform")


def _threads_sync_env() -> dict:
    """整合面:把 vault 指到本專案 vault;data 留在 vendor 目錄(skill 自帶狀態)。"""
    env = {**os.environ, "PYTHONUTF8": "1"}   # part-001 教訓:cp950
    env["THREADS_SYNC_VAULT"] = str(config.VAULT_PATH)
    env.setdefault("THREADS_SYNC_HEADLESS", "1")   # 排程情境無頭;手動可覆蓋
    return env


def classify_output(returncode: int, output: str) -> str:
    """exit code + 輸出 → agent_runs.status。"""
    low = output.lower()
    if any(m in low for m in LOGIN_EXPIRED_MARKERS):
        return "login_expired"
    return "ok" if returncode == 0 else "error"


def run_step(script: Path, env: dict, timeout: int = 1800) -> tuple[int, str]:
    """跑一個步驟腳本。回 (returncode, 合併輸出)。逾時視為 error。"""
    try:
        proc = subprocess.run(
            [sys.executable, str(script)],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            env=env, cwd=script.parent.parent, timeout=timeout)
        return proc.returncode, (proc.stdout or "") + (proc.stderr or "")
    except subprocess.TimeoutExpired:
        return 1, f"TIMEOUT after {timeout}s"


def run_threads_sync(db: Path | None = None, steps: list[str] | None = None,
                     _run_step=None) -> str:
    """跑 threads-sync 管線。回最終 status。_run_step 供測試注入。

    任一步 login_expired → 中止(後續步驟無意義);error → 中止;
    全部 ok → 記 cursors last_run。
    """
    runner = _run_step or run_step
    pkg = SKILLS_DIR / "threads_sync_vendor" / "threads-sync"
    env = _threads_sync_env()
    selected = steps or list(THREADS_SYNC_STEPS)

    run_id_con = stm.connect(db)
    try:
        cur = run_id_con.execute(
            "INSERT INTO agent_runs (started_at, trigger) VALUES (?, 'scheduler')",
            (stm.now(),))
        run_id = cur.lastrowid
        run_id_con.commit()
    finally:
        run_id_con.close()

    status, detail = "ok", []
    for name in selected:
        script = pkg / THREADS_SYNC_STEPS[name]
        rc, output = runner(script, env)
        step_status = classify_output(rc, output)
        detail.append(f"{name}={step_status}")
        stm.event_append(db, "sync-threads", "completed" if step_status == "ok" else "failed",
                         f"threads_sync step {name}: {step_status}")
        if step_status != "ok":
            status = step_status
            break  # login_expired / error → 中止管線

    if status == "ok":
        stm.cursor_set(db, "threads_sync", "last_run", str(stm.now()))

    con = stm.connect(db)
    try:
        con.execute(
            "UPDATE agent_runs SET finished_at = ?, status = ?, summary = ? WHERE id = ?",
            (stm.now(), status, f"threads_sync: {' '.join(detail)}", run_id))
        con.commit()
    finally:
        con.close()
    return status


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m skills.runner")
    parser.add_argument("skill", choices=["threads_sync"])
    parser.add_argument("--steps", default=None,
                        help=f"逗號分隔子集(預設全部): {','.join(THREADS_SYNC_STEPS)}")
    parser.add_argument("--db", type=Path, default=None)
    args = parser.parse_args(argv)

    steps = None
    if args.steps:
        steps = [s.strip() for s in args.steps.split(",") if s.strip()]
        unknown = set(steps) - THREADS_SYNC_STEPS.keys()
        if unknown:
            print(f"ERROR: unknown steps {sorted(unknown)}", file=sys.stderr)
            return 2

    status = run_threads_sync(args.db, steps)
    print(f"threads_sync: {status}")
    return 0 if status == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
