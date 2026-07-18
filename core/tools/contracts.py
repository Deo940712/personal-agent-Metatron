"""Shared types for capability invocation, results, and static exposure data."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import TypeAlias

ApiCall: TypeAlias = Callable[[str, str, str, bool], str]
JsonScalar: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]


class Permission(StrEnum):
    """Authority a capability needs at its application boundary."""

    READ = "read"
    PROPOSE = "propose"
    AUTO_APPLY = "auto_apply"
    APPLY = "apply"
    JOB = "job"


@dataclass(frozen=True, slots=True)
class CapabilityContext:
    """Dependencies supplied by a thin interface adapter for one invocation."""

    db: Path | None = None
    vault: Path | None = None
    idx_db: Path | None = None
    transcript_dir: Path | None = None
    channel_ref: str | None = None
    api: ApiCall | None = None


@dataclass(frozen=True, slots=True)
class CapabilityResult:
    """User-facing result that does not depend on a channel-specific reply type."""

    text: str
    pending_id: int | None = None
    needs_confirmation: bool = False
    outcome: str | None = None    # recall found/not_found 等能力回報的細分結果


@dataclass(frozen=True, slots=True)
class RehydrationResult:
    """Raw transcript entries recovered from one distilled note."""

    entries: tuple[dict[str, JsonValue], ...]


@dataclass(frozen=True, slots=True)
class ToolSpec:
    """Static ownership and exposure metadata for one application capability."""

    feature: str
    name: str
    agents: tuple[str, ...]
    interfaces: tuple[str, ...]
    permission: Permission
    storage: tuple[str, ...]
    implementation: str
