"""Static capability catalog; this is policy data, not a plugin loader."""

from __future__ import annotations

from typing import Final

from core.tools.contracts import Permission, ToolSpec

CAPABILITIES: Final[tuple[ToolSpec, ...]] = (
    ToolSpec("今日行程與待辦", "schedule.today", (), ("discord", "mcp"), Permission.READ, ("DB1",), "core.tools.schedule.today"),
    ToolSpec("本週行程", "schedule.week", (), ("discord", "mcp"), Permission.READ, ("DB1",), "core.tools.schedule.week"),
    ToolSpec("自然語言行程提案", "schedule.propose", ("schedule",), ("cli", "discord", "mcp"), Permission.PROPOSE, ("DB1",), "core.tools.schedule.propose"),
    ToolSpec("新增待辦提案", "tasks.propose", ("schedule",), ("cli", "discord", "mcp"), Permission.PROPOSE, ("DB1",), "core.tools.tasks.add"),
    ToolSpec("完成行程或待辦", "tasks.complete", (), ("discord", "mcp"), Permission.AUTO_APPLY, ("DB1",), "core.tools.tasks.complete"),
    ToolSpec("專案進度", "projects.status", (), ("discord", "dashboard", "mcp"), Permission.READ, ("DB1",), "core.tools.projects.status"),
    ToolSpec("知識庫問答", "memory.recall", ("recall",), ("cli", "mcp"), Permission.READ, ("vault", "index", "cold-transcript"), "core.tools.memory.query"),
    ToolSpec("記憶回水", "memory.rehydrate", ("recall",), ("cli", "mcp"), Permission.READ, ("vault", "cold-transcript"), "core.tools.memory.rehydrate"),
    ToolSpec("驗證後唯一寫入", "writer.apply", (), ("internal",), Permission.APPLY, ("DB1", "vault"), "core.writer.apply"),
    ToolSpec("提醒排程", "job.remind", (), ("cli", "scheduler"), Permission.JOB, ("DB1",), "python -m core.agent --job remind"),
    ToolSpec("記憶蒸餾", "job.consolidate", ("consolidator",), ("cli", "scheduler"), Permission.JOB, ("DB1", "vault", "cold-transcript"), "python -m core.agent --job consolidate"),
    ToolSpec("專案追蹤", "job.track", ("coding_tracker",), ("cli", "scheduler"), Permission.JOB, ("DB1", "git", "beacon", "opencode"), "python -m core.agent --job track"),
    ToolSpec("知識整理", "job.curate", ("curator",), ("cli", "scheduler"), Permission.JOB, ("vault",), "python -m core.agent --job curate"),
    ToolSpec("Threads 同步", "skill.threads_sync", (), ("cli", "scheduler"), Permission.JOB, ("vault", "skill-data"), "skills.runner:threads_sync"),
)


def by_name(name: str) -> ToolSpec:
    """Return one named capability; unknown names are programmer errors."""
    for spec in CAPABILITIES:
        if spec.name == name:
            return spec
    message = f"unknown capability: {name}"
    raise LookupError(message)
