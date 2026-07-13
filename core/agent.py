"""Orchestrator 入口(ARCHITECTURE §6.1/§6.6)。

無狀態:一次呼叫 = INSERT agent_runs → 組上下文 → 派工 → writer → 回覆 → 死。
下次呼叫從 DB1 重建上下文,無 session 殘留。

用法:
    python -m core.agent "明天下午兩點開會 提前30分提醒"
    python -m core.agent --job remind      # 排程入口:到期提醒(確定性,不經 LLM)
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable

from core import stm, subagents, writer
from core.llm import LLMError
from core.subagents import SubagentError


# ── agent_runs 記錄(§6.1:每次呼叫都留稽核) ─────────────────────────

def _run_start(db: Path | None, trigger: str) -> int:
    con = stm.connect(db)
    try:
        cur = con.execute(
            "INSERT INTO agent_runs (started_at, trigger) VALUES (?, ?)",
            (stm.now(), trigger))
        con.commit()
        return cur.lastrowid
    finally:
        con.close()


def _run_finish(db: Path | None, run_id: int, status: str,
                summary: str | None = None, error: str | None = None) -> None:
    con = stm.connect(db)
    try:
        con.execute(
            "UPDATE agent_runs SET finished_at = ?, status = ?, summary = ?, error = ? "
            "WHERE id = ?",
            (stm.now(), status, summary, error, run_id))
        con.commit()
    finally:
        con.close()


# ── B6 緩解:done/cancel 的 target 白名單 ────────────────────────────

def _enforce_target_whitelist(proposal: dict, active_ids: set[int]) -> str | None:
    """done/cancel 只能指向本次注入的 active 清單;越界 → 錯誤訊息(拒絕)。"""
    action = proposal.get("payload", {}).get("action")
    if action not in {"done", "cancel"}:
        return None
    target = proposal.get("target", "")
    if not str(target).isdigit() or int(target) not in active_ids:
        return (f"{action} target #{target} 不在目前 active 清單中"
                f"(prompt injection 防護;請先 list 確認 id)")
    return None


# ── invoke:自然語言入口(§6.1 全流程)────────────────────────────────

def invoke(text: str, trigger: str = "cli", *,
           confirm_fn: Callable[[str], bool] | None = None,
           reply_fn: Callable[[str], None] = print,
           db: Path | None = None, _api=None) -> int:
    """一次呼叫的完整生命週期。回傳 exit code(0 ok / 1 rejected / 2 error)。"""
    run_id = _run_start(db, trigger)
    try:
        # 知識查詢前綴 → recall(CLI 是本機,放行;part-004)
        stripped = text.strip()
        recall_prefixes = ("recall", "查", "找筆記", "知識")
        if any(stripped.startswith(p) for p in recall_prefixes):
            from core import recall as recall_mod
            for p in recall_prefixes:
                if stripped.startswith(p):
                    query = stripped[len(p):].strip() or stripped
                    break
            result = recall_mod.ask(query, db=db, _api=_api)
            _run_finish(db, run_id, "ok" if result.ok else "partial",
                        summary=f"recall steps={result.steps}")
            reply_fn(result.text)
            return 0 if result.ok else 1

        active = stm.schedule_list(db) + stm.task_list(db)
        proposal = subagents.run_schedule(text, active_items=active, db=db, _api=_api)

        if "error" in proposal:
            _run_finish(db, run_id, "ok", summary=f"not actionable: {proposal['error']}")
            reply_fn(f"這不是行程/待辦:{proposal['error']}")
            return 1

        wl_err = _enforce_target_whitelist(
            proposal, {r["id"] for r in active})
        if wl_err:
            stm.event_append(db, "orchestrator", "proposal_rejected", wl_err)
            _run_finish(db, run_id, "ok", summary="whitelist rejected")
            reply_fn(f"已拒絕:{wl_err}")
            return 1

        result = writer.apply(proposal, confirm_fn, db)
        _run_finish(db, run_id, "ok", summary=result.detail)
        reply_fn(f"{'✔' if result.ok else '✘'} {result.detail}")
        return 0 if result.ok else 1

    except (LLMError, SubagentError) as e:
        _run_finish(db, run_id, "error", error=str(e))
        reply_fn(f"執行失敗:{e}")
        return 2
    except Exception as e:                          # noqa: BLE001 — 頂層防線:run 不可卡 running
        _run_finish(db, run_id, "error", error=f"{type(e).__name__}: {e}")
        reply_fn(f"內部錯誤:{type(e).__name__}: {e}")
        return 2


# ── remind job(§6.6:確定性,不經 LLM)──────────────────────────────

_WEEKDAYS = {"MO": 0, "TU": 1, "WE": 2, "TH": 3, "FR": 4, "SA": 5, "SU": 6}


def rrule_next(rrule: str, after_epoch: int) -> int:
    """確定性前推:回傳 after_epoch 之後的下一次發生(epoch)。

    支援 part-002 子集:FREQ=DAILY / FREQ=WEEKLY;BYDAY=...(proposals 已驗證格式)。
    """
    parts = dict(p.split("=", 1) for p in rrule.split(";") if "=" in p)
    base = datetime.fromtimestamp(after_epoch)
    if parts["FREQ"] == "DAILY":
        return int((base + timedelta(days=1)).timestamp())
    # WEEKLY:找下一個符合 BYDAY 的日子(未指定 BYDAY = 每週同日)
    days = sorted(_WEEKDAYS[d] for d in parts.get("BYDAY", "").split(",") if d) or [base.weekday()]
    for ahead in range(1, 8):
        cand = base + timedelta(days=ahead)
        if cand.weekday() in days:
            return int(cand.timestamp())
    return int((base + timedelta(days=7)).timestamp())      # 不可達,防禦性


def job_remind(db: Path | None = None,
               notify_fn: Callable[[str], None] = print) -> int:
    """到期提醒:partial index 查詢 → 通知 → 單次標記 / 重複前推。

    順道清理逾時的待確認提案(part-002.5;不多開 job)。
    notify_fn 預設 console;Discord bot 注入 DM 推播。
    """
    from core import chat
    run_id = _run_start(db, "scheduler")
    try:
        chat.expire_pending(db)                     # 順掃逾時 pending
        con = stm.connect(db)
        try:
            due = con.execute(
                "SELECT id, title, start_at, remind_at, rrule FROM schedule "
                "WHERE remind_at <= ? AND status = 'active' AND reminded_at IS NULL",
                (stm.now(),)).fetchall()
        finally:
            con.close()

        for row_id, title, start_at, _remind_at, rrule in due:
            notify_fn(f"提醒:{title} @ {stm.fmt_when(start_at)}")
            con = stm.connect(db)
            try:
                if rrule is None:
                    con.execute("UPDATE schedule SET reminded_at = ? WHERE id = ?",
                                (stm.now(), row_id))
                else:
                    # 重複行程:整組時間前推,reminded_at 清回 NULL 等下一輪
                    next_start = rrule_next(rrule, start_at)
                    delta = next_start - start_at
                    con.execute(
                        "UPDATE schedule SET start_at = ?, "
                        "end_at = CASE WHEN end_at IS NULL THEN NULL ELSE end_at + ? END, "
                        "remind_at = remind_at + ?, reminded_at = NULL WHERE id = ?",
                        (next_start, delta, delta, row_id))
                con.commit()
            finally:
                con.close()
            stm.event_append(db, "orchestrator", "completed",
                             f"reminded #{row_id} {title}", target=f"schedule:{row_id}")

        _run_finish(db, run_id, "ok", summary=f"reminded {len(due)}")
        return 0
    except Exception as e:                          # noqa: BLE001 — 頂層防線
        _run_finish(db, run_id, "error", error=f"{type(e).__name__}: {e}")
        return 2


# ── CLI ──────────────────────────────────────────────────────────────

def _cli_confirm(preview: str) -> bool:
    print(preview)
    return input("confirm? [y/N] ").strip().lower() == "y"


def job_consolidate(db: Path | None = None) -> int:
    """夜間蒸餾入口(委派 consolidate.run;§6.3)。"""
    from core import consolidate                    # 延遲 import:remind 路徑不載 llm
    run_id = _run_start(db, "scheduler")
    try:
        stats = consolidate.run(db=db)
        _run_finish(db, run_id, "ok", summary=f"consolidate {stats}")
        print(f"OK: {stats}")
        return 0
    except Exception as e:                          # noqa: BLE001 — 頂層防線
        _run_finish(db, run_id, "error", error=f"{type(e).__name__}: {e}")
        print(f"ERROR: {e}")
        return 2


def job_curate(db: Path | None = None) -> int:
    """curator 入口(part-004;委派 curate.run)。"""
    from core import curate                     # 延遲 import
    run_id = _run_start(db, "scheduler")
    try:
        stats = curate.run(db=db)
        _run_finish(db, run_id, "ok", summary=f"curate {stats}")
        print(f"OK: {stats}")
        return 0
    except Exception as e:                      # noqa: BLE001 — 頂層防線
        _run_finish(db, run_id, "error", error=f"{type(e).__name__}: {e}")
        print(f"ERROR: {e}")
        return 2


def job_track(db: Path | None = None) -> int:
    """coding_tracker 入口(part-005;委派 track.run)。"""
    from core import track                      # 延遲 import
    run_id = _run_start(db, "scheduler")
    try:
        stats = track.run(db=db)
        _run_finish(db, run_id, "ok", summary=f"track {stats}")
        print(f"OK: {stats}")
        return 0
    except Exception as e:                      # noqa: BLE001 — 頂層防線
        _run_finish(db, run_id, "error", error=f"{type(e).__name__}: {e}")
        print(f"ERROR: {e}")
        return 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m core.agent", description=__doc__)
    parser.add_argument("text", nargs="?", default=None, help="自然語言指令")
    parser.add_argument("--job", choices=["remind", "consolidate", "curate", "track"],
                        default=None, help="排程 job")
    parser.add_argument("--db", type=Path, default=None)
    parser.add_argument("--yes", action="store_true", help="跳過確認(測試/腳本用)")
    args = parser.parse_args(argv)

    if args.job == "remind":
        return job_remind(args.db)
    if args.job == "consolidate":
        return job_consolidate(args.db)
    if args.job == "curate":
        return job_curate(args.db)
    if args.job == "track":
        return job_track(args.db)
    if not args.text:
        parser.error("需要自然語言指令或 --job")
    confirm = (lambda p: (print(p), True)[1]) if args.yes else _cli_confirm
    return invoke(args.text, "cli", confirm_fn=confirm, db=args.db)


if __name__ == "__main__":
    sys.exit(main())
