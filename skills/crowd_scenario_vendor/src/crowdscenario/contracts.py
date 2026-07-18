"""Firewall contracts: the only objects the crowd layer may read and emit.

The crowd scenario engine is a **non-authoritative narrative side-rail**. Its
contracts are deliberately shaped so it *cannot* leak a decision-grade number:

- ``ScenarioSeed`` (read-side): the ONLY thing the engine reads — a frozen,
  bucketed projection carrying ordinal context only, never a raw metric (a price,
  a yield, a churn rate, a migration-effort score — whatever the domain measures).
- ``CrowdNarrative`` (write-side): the ONLY thing the engine emits — a categorical
  crowd stance + narrative, with **no numeric scalar** anything could sum into a
  decision. ``non_authoritative`` is hard-wired ``True``.
- ``NarrativeDivergence`` (report-side): crowd-vs-your-own read, a bucket + two
  categorical postures — again no additive scalar.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType

# Domain-neutral stance vocabulary. A domain pack maps these back to its own display
# labels (e.g. the stock pack renders negative->bearish, positive->bullish).
CONSENSUS = ("negative", "neutral", "positive")
HORIZONS = ("intraday", "swing", "long")
INTENSITIES = ("mild", "severe")
DIVERGENCE_BUCKETS = ("LOW", "MEDIUM", "HIGH")


class ContractError(ValueError):
    """Raised when a firewall contract invariant is violated.

    A subclass of ``ValueError`` so callers can catch it as a value error, but a
    distinct type so a contract breach is never confused with an ordinary bad value.
    These checks run as explicit ``raise`` (not ``assert``), so they survive
    ``python -O`` — the firewall must NOT be strippable by optimize mode.
    """


@dataclass(frozen=True)
class ScenarioSeed:
    """Read-side firewall contract: the only thing the crowd engine may read.

    A frozen projection carrying ONLY bucketed ordinal context — e.g.
    ``discount_premium -> "deep_discount"`` in a stock pack, or
    ``migration_effort -> "high_effort"`` in a software pack. Personas never see raw
    numbers, which structurally prevents echoing or recomputing an authoritative figure.
    """

    seed_id: str
    rng_seed: int
    # The already-decided event being rehearsed. Kept under its historical name for
    # serialized-schema stability; ``make_seed`` accepts the neutral ``scenario_label``.
    market_scenario_label: str
    # Which domain pack produced this seed. Bound so ``run_scenario`` can refuse a
    # stock seed run against a product pack (a silent semantic mismatch otherwise).
    domain_id: str = "stock_tw"
    # Ordinal buckets only — NO raw metric numbers (price/nav/yield/effort/churn/...).
    ordinal_context: Mapping[str, str] = field(default_factory=dict)
    seed_hash: str = ""
    # Rehearsal dimensions: which time-scale and how strong the shock. Categorical
    # only (no numeric scalar), so they stay firewall-safe while changing which
    # cohort leads the reaction chain.
    horizon: str = "swing"  # intraday | swing | long
    intensity: str = "mild"  # mild | severe

    def __post_init__(self) -> None:
        if self.horizon not in HORIZONS:
            raise ContractError("horizon out of vocabulary")
        if self.intensity not in INTENSITIES:
            raise ContractError("intensity out of vocabulary")
        # Ordinal buckets only: every key AND value must be a non-empty string. This is
        # the read-side firewall's teeth — a raw number (price/yield/nav) or an empty
        # label can never ride into the engine, even via a direct constructor call.
        # ``isinstance(x, str)`` also excludes bool/int/float (a bool is an int subclass,
        # and neither is a str), so a numeric value is rejected here.
        for key, value in self.ordinal_context.items():
            if not isinstance(key, str) or not key:
                raise ContractError("ordinal_context keys must be non-empty strings")
            if not isinstance(value, str) or not value:
                raise ContractError(
                    "ordinal_context values must be non-empty strings (ordinal buckets only)"
                )
        # Deep-freeze the ordinal map: a frozen dataclass only stops rebinding the
        # attribute, not mutating the dict it points at. Wrapping it read-only closes
        # the "seed.ordinal_context['yield'] = ...' after construction" hole.
        if not isinstance(self.ordinal_context, MappingProxyType):
            object.__setattr__(
                self, "ordinal_context", MappingProxyType(dict(self.ordinal_context))
            )


@dataclass(frozen=True)
class PersonaReaction:
    archetype_id: str
    stance: int  # -1 (contra) | 0 (neutral) | +1 (pro)
    register: str
    excerpt: str
    is_synthetic: bool = True

    def __post_init__(self) -> None:
        # ``stance`` is a bounded categorical label, not a free integer or a weight.
        # Exclude bool explicitly: a bool is an int subclass and ``True in (-1, 0, 1)``
        # is True, so True/False would otherwise slip past as a stance.
        if isinstance(self.stance, bool) or self.stance not in (-1, 0, 1):
            raise ContractError("stance must be -1, 0, or +1")
        if self.is_synthetic is not True:
            raise ContractError("persona reaction must be synthetic")
        if not isinstance(self.archetype_id, str) or not self.archetype_id:
            raise ContractError("archetype_id must be a non-empty string")
        if not isinstance(self.register, str) or not self.register:
            raise ContractError("register must be a non-empty string")
        if not isinstance(self.excerpt, str):
            raise ContractError("excerpt must be a string")


@dataclass(frozen=True)
class CrowdNarrative:
    """Write-side firewall contract: the ONLY thing the crowd engine may emit.

    There is **no numeric scalar modifier** — its very shape would invite a
    "just add 0.05" leak. The engine emits a categorical crowd stance + narrative
    only; the crowd-vs-your-own divergence is computed later, so the engine never
    knows (and cannot echo) an authoritative posture.
    """

    seed_id: str
    rng_seed: int
    # Declared size of the SYNTHETIC crowd population being rehearsed (0 for a dry
    # stub, else 20..50). This is the population the roster is meant to stand in for —
    # it is deliberately decoupled from ``len(persona_samples)``, which is the fixed
    # archetype roster (the pack's persona_ids). Do not read it as a sample count.
    n_personas: int
    crowd_consensus: str  # negative | neutral | positive (NO numeric modifier)
    narrative_md: str
    persona_samples: tuple[PersonaReaction, ...] = field(default_factory=tuple)
    synthetic_population: bool = True
    non_authoritative: bool = True  # HARD-WIRED True
    artifact_type: str = "CrowdNarrative"
    # Narrator provenance for observability: which backend produced ``narrative_md``
    # ("deterministic" | "fusion:judge" | "fusion:writer" | "fusion:fallback") and any
    # per-run notes. Categorical strings only — no scalar, so still firewall-safe.
    narrator_backend: str = "deterministic"
    narrator_notes: tuple[str, ...] = field(default_factory=tuple)
    # Categorical schema tag for forward-compatible deserialization. A string (not an
    # int) on purpose — it is a label, never a scalar anything could sum into a decision.
    schema_version: str = "1"

    def __post_init__(self) -> None:
        if self.crowd_consensus not in CONSENSUS:
            raise ContractError("crowd_consensus out of vocabulary")
        if not (self.n_personas == 0 or 20 <= self.n_personas <= 50):
            raise ContractError("n_personas 0 or 20..50")
        if self.non_authoritative is not True:
            raise ContractError("crowd narrative must be non-authoritative")
        if self.synthetic_population is not True:
            raise ContractError("crowd population must be synthetic")


@dataclass(frozen=True)
class NarrativeDivergence:
    """Report-time artifact: crowd-vs-your-own-read divergence (categorical, bounded).

    No additive scalar anything could silently wire into a sort — only a bucket and
    two categorical postures. Computed at report time from the crowd narrative + an
    external posture you supply; never produced inside the engine.
    """

    seed_id: str
    crowd_consensus: str  # negative | neutral | positive
    external_posture: str  # negative | neutral | positive
    divergence_bucket: str  # LOW | MEDIUM | HIGH
    narrative_intensity: int  # 1 | 2 | 3
    non_authoritative: bool = True
    synthetic_population: bool = True
    artifact_type: str = "NarrativeDivergence"
    storylines: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.crowd_consensus not in CONSENSUS:
            raise ContractError("crowd_consensus out of vocabulary")
        if self.external_posture not in CONSENSUS:
            raise ContractError("external_posture out of vocabulary")
        if self.divergence_bucket not in DIVERGENCE_BUCKETS:
            raise ContractError("bad divergence_bucket")
        if self.narrative_intensity not in (1, 2, 3):
            raise ContractError("narrative_intensity 1|2|3")
        if self.non_authoritative is not True:
            raise ContractError("divergence artifact must be non-authoritative")
        if self.synthetic_population is not True:
            raise ContractError("divergence artifact must be synthetic")
