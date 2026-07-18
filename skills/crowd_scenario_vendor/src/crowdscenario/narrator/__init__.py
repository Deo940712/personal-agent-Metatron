"""Narrator backends: turn already-decided categorical facts into narrative prose.

The engine decides the stance deterministically and firewalled; a narrator only writes
the story over those facts. ``DeterministicNarrator`` is the default (offline, stdlib);
``FusionNarrator`` runs 2 writer LLMs + 1 judge LLM with every output firewall-screened
and a deterministic fallback.
"""

from __future__ import annotations

from crowdscenario.narrator.base import (
    EngineFacts,
    ModelFn,
    NarratorBackend,
    NarratorResult,
    PersonaFact,
)
from crowdscenario.narrator.deterministic import DeterministicNarrator
from crowdscenario.narrator.firewall import is_clean, scan_violations
from crowdscenario.narrator.fusion import FusionNarrator

__all__ = [
    "EngineFacts",
    "ModelFn",
    "NarratorBackend",
    "NarratorResult",
    "PersonaFact",
    "DeterministicNarrator",
    "FusionNarrator",
    "is_clean",
    "scan_violations",
]
