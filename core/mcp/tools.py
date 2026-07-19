"""MCP 工具層:傳輸無關的工具定義 + handler(part-006-slice-002)。

每個工具 = name + description + JSON input schema + handler。handler 復用既有能力
層(octools/scanners/stm/application),**不繞過 writer/確認邊界**:寫入工具回
pending(需確認),confirm 工具落地。傳輸(stdio/http)只做 JSON-RPC 收發。

開發迴圈 4 工具:dev_status / session_tail / directive_push / directive_list。
助理工具:schedule_list / task_list / project_status / schedule_add / task_add / confirm。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core import chat, octools, scanners, stm
from core.application import InvocationContext, invoke


class ToolError(ValueError):
    """未知工具或工具前置條件違反。"""


@dataclass(frozen=True, slots=True)
class Tool:
    name: str
    description: str
    input_schema: dict
    handler: Callable[..., dict]


def _obj(props: dict, required: list[str] | None = None) -> dict:
    schema: dict = {"type": "object", "properties": props}
    if required:
        schema["required"] = required
    return schema


# ── 開發迴圈工具 ─────────────────────────────────────────────────────

def _h_dev_status(args: dict, *, db: Path | None, _api=None) -> dict:
    """三源綜合:opencode.db session + beacon CURRENT + git。容錯。

    project 解析(part-012 修可用性):
    - 已註冊專案名 → 用其 repo_path
    - 否則若 project 本身是存在的目錄路徑 → 直接掃該路徑(免先註冊)
    掃描全容錯(git/beacon/opencode 各自失敗回 None,不 crash)。
    """
    from pathlib import Path as _Path

    project = args.get("project")
    rows = stm.project_show(db, project)
    repo = rows[0].get("repo_path") if rows else None
    if not repo and project and _Path(project).is_dir():
        repo = project                            # 未註冊 → 直接吃路徑
    sources: dict = {"opencode": None, "beacon": None, "git": None}
    if repo:
        sources["opencode"] = octools.project_activity(repo, db_path=None)
        sources["beacon"] = scanners.beacon_scan(repo)
        sources["git"] = scanners.git_scan(repo)
    text = f"專案 {project or '(all)'}:"
    if rows:
        text += f" phase={rows[0].get('phase') or '-'}"
    elif sources["git"]:
        g = sources["git"]
        text += f" branch={g.get('branch', '?')} 最新:{str(g.get('last_message', ''))[:40]}"
    elif sources["beacon"]:
        text += f" beacon={sources['beacon'].get('status', '?')}"
    return {"ok": True, "project": project, "sources": sources, "text": text}


def _h_session_tail(args: dict, *, db: Path | None, _api=None) -> dict:
    sid = args.get("session_id", "")
    n = int(args.get("n", 5))
    tail = octools.session_tail(sid, n=n)
    text = "\n".join(f"[{t['role']}] {t['text']}" for t in tail) or "(無對話)"
    return {"ok": True, "tail": tail, "text": text}


def _h_directive_push(args: dict, *, db: Path | None, _api=None) -> dict:
    try:
        did = stm.directive_add(db, args.get("project", ""), args.get("text", ""))
    except ValueError as e:
        return {"ok": False, "text": f"拒絕:{e}"}
    return {"ok": True, "directive_id": did, "text": f"已入佇列 #{did}"}


def _h_directive_list(args: dict, *, db: Path | None, _api=None) -> dict:
    status = args.get("status", "pending")
    directives = stm.directive_list(db, project=args.get("project"), status=status)
    text = "\n".join(f"#{d['id']} [{d['status']}] {d['text']}" for d in directives) \
        or "(無指令)"
    return {"ok": True, "directives": directives, "text": text}


# ── 助理工具(復用 application.invoke 統一入口)────────────────────────

def _invoke_text(text: str, db: Path | None, _api, *, allow_recall: bool = True) -> dict:
    result = invoke(text, InvocationContext(trigger="chat", allow_recall=allow_recall,
                                            channel_ref="mcp"), db=db, _api=_api)
    return {
        "ok": result.outcome not in ("rejected",),
        "text": result.text,
        "outcome": result.outcome,
        "pending_id": result.pending_id,
        "needs_confirmation": result.needs_confirmation,
    }


def _h_schedule_list(args: dict, *, db: Path | None, _api=None) -> dict:
    return _invoke_text("today", db, _api)


def _h_task_list(args: dict, *, db: Path | None, _api=None) -> dict:
    rows = stm.task_list(db)
    text = "\n".join(f"#{r['id']} {r['title']}" for r in rows) or "(無待辦)"
    return {"ok": True, "text": text}


def _h_project_status(args: dict, *, db: Path | None, _api=None) -> dict:
    return _invoke_text("proj", db, _api)


def _h_schedule_add(args: dict, *, db: Path | None, _api=None) -> dict:
    return _invoke_text(str(args.get("text", "")), db, _api)


def _h_task_add(args: dict, *, db: Path | None, _api=None) -> dict:
    return _invoke_text(f"todo {args.get('text', '')}", db, _api)


def _h_confirm(args: dict, *, db: Path | None, _api=None) -> dict:
    pid = int(args.get("pending_id"))
    approve = bool(args.get("approve", False))
    reply = chat.confirm(pid, approve, db=db)
    return {"ok": "已建立" in reply.text or "已取消" in reply.text,
            "text": reply.text}


_TOOLS: dict[str, Tool] = {}


def _register(tool: Tool) -> None:
    _TOOLS[tool.name] = tool


_register(Tool("dev_status", "讀某專案的開發進度(opencode session + beacon + git 三源)",
               _obj({"project": {"type": "string"}}), _h_dev_status))
_register(Tool("session_tail", "讀某 OpenCode session 最後 n 則對話摘要",
               _obj({"session_id": {"type": "string"}, "n": {"type": "integer"}},
                    ["session_id"]), _h_session_tail))
_register(Tool("directive_push", "下一步指令入佇列(下次 session 開場讀取)",
               _obj({"project": {"type": "string"}, "text": {"type": "string"}},
                    ["project", "text"]), _h_directive_push))
_register(Tool("directive_list", "列出指令佇列(預設 pending)",
               _obj({"project": {"type": "string"}, "status": {"type": "string"}}),
               _h_directive_list))
_register(Tool("schedule_list", "今日行程/待辦", _obj({}), _h_schedule_list))
_register(Tool("task_list", "未完成待辦清單", _obj({}), _h_task_list))
_register(Tool("project_status", "專案進度總覽", _obj({}), _h_project_status))
_register(Tool("schedule_add", "自然語言排行程(回 pending 待確認)",
               _obj({"text": {"type": "string"}}, ["text"]), _h_schedule_add))
_register(Tool("task_add", "新增待辦(回 pending 待確認)",
               _obj({"text": {"type": "string"}}, ["text"]), _h_task_add))
_register(Tool("confirm", "確認或取消一個 pending(落地寫入)",
               _obj({"pending_id": {"type": "integer"}, "approve": {"type": "boolean"}},
                    ["pending_id", "approve"]), _h_confirm))


def all_tools() -> list[Tool]:
    return list(_TOOLS.values())


def call(name: str, args: dict[str, Any], *, db: Path | None = None, _api=None) -> dict:
    """執行一個工具。未知工具 → ToolError。"""
    tool = _TOOLS.get(name)
    if tool is None:
        raise ToolError(f"unknown tool: {name!r}")
    return tool.handler(args, db=db, _api=_api)
