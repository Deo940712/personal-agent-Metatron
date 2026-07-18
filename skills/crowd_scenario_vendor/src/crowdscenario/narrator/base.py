"""Narrator backends: how the categorical engine facts become narrative prose.

The engine decides the categorical stance (``crowd_consensus`` + per-persona
``stance``) DETERMINISTICALLY and firewalled. A *narrator* only turns those already-
decided facts into a narrative string — it can never change a stance, a consensus, or
introduce a number. Two backends ship:

- ``DeterministicNarrator`` — the default, offline, stdlib-only table-lookup prose.
- ``FusionNarrator`` — 2 writer LLMs + 1 judge LLM (see ``fusion.py``); every LLM
  output is screened by the rule-based firewall scanner before it is allowed through,
  and it falls back to the deterministic narrator if nothing survives.

``EngineFacts`` is the READ-ONLY hand-off. It carries the categorical consensus, the
display frame, and one ``PersonaFact`` per persona (id, display name, stance, and the
pack's canned voice line). It deliberately carries NO raw metric, so a narrator — LLM
or not — has nothing decision-grade to echo.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol

# A model call is just text-in / text-out. The caller injects it, so the core stays
# zero-dependency and the whole thing is offline-testable with a fake callable.
ModelFn = Callable[[str], str]


@dataclass(frozen=True)
class PersonaFact:
    """One persona's already-decided, categorical contribution (no scalar)."""

    persona_id: str
    display_name: str
    stance: int  # -1 | 0 | +1 — decided by the engine, never by the narrator
    voice_line: str


@dataclass(frozen=True)
class EngineFacts:
    """Read-only facts handed to a narrator. No raw number crosses this boundary."""

    label: str
    consensus: str  # neutral vocabulary: negative | neutral | positive
    consensus_display: str  # domain display label (e.g. bearish / oppose)
    frame: str  # horizon display wording
    intensity_zh: str
    personas: tuple[PersonaFact, ...]
    reaction_chain: str  # the deterministic who-moves-first chain (already firewalled)


@dataclass(frozen=True)
class NarratorResult:
    """What a narrator returns: the prose, plus provenance for observability."""

    narrative_md: str
    backend: str  # e.g. "deterministic" | "fusion:writer_b" | "fusion:fallback"
    notes: tuple[str, ...] = field(default_factory=tuple)


class NarratorBackend(Protocol):
    """Turn already-decided ``EngineFacts`` into narrative prose. Nothing else."""

    def render(self, facts: EngineFacts) -> NarratorResult: ...
