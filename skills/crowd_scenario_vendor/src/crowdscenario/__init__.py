"""crowd-scenario — a deterministic, firewalled crowd rehearsal engine.

Rehearse (not predict) how a synthetic crowd of persona archetypes might react to an
already-decided event. The engine is domain-pluggable: a ``DomainPack`` supplies the
persona roster, the ordinal axes, and the display labels, so the same firewalled
engine can rehearse Taiwan retail investors (``STOCK_TW``), a product launch
(``PRODUCT_LAUNCH``), or any other crowd you model as a pack.

Whatever the domain, the engine reads only a bucketed ScenarioSeed and emits only a
categorical, non-authoritative CrowdNarrative — it can never leak a decision-grade
number into your own analysis.
"""

from __future__ import annotations

from crowdscenario.composer import compose_divergence, posture_from_score
from crowdscenario.contracts import (
    CONSENSUS,
    DIVERGENCE_BUCKETS,
    HORIZONS,
    INTENSITIES,
    ContractError,
    CrowdNarrative,
    NarrativeDivergence,
    PersonaReaction,
    ScenarioSeed,
)
from crowdscenario.domains import Axis, DomainPack, validate_pack
from crowdscenario.domains.product import PRODUCT_LAUNCH
from crowdscenario.domains.software import SOFTWARE_MIGRATION
from crowdscenario.domains.stock_tw import STOCK_TW
from crowdscenario.engine import run_scenario
from crowdscenario.narrator import (
    DeterministicNarrator,
    EngineFacts,
    FusionNarrator,
    NarratorBackend,
    NarratorResult,
    PersonaFact,
    scan_violations,
)
from crowdscenario.seed import make_seed

__all__ = [
    "CONSENSUS",
    "DIVERGENCE_BUCKETS",
    "HORIZONS",
    "INTENSITIES",
    "ContractError",
    "CrowdNarrative",
    "NarrativeDivergence",
    "PersonaReaction",
    "ScenarioSeed",
    "Axis",
    "DomainPack",
    "validate_pack",
    "STOCK_TW",
    "PRODUCT_LAUNCH",
    "SOFTWARE_MIGRATION",
    "DeterministicNarrator",
    "FusionNarrator",
    "NarratorBackend",
    "NarratorResult",
    "EngineFacts",
    "PersonaFact",
    "scan_violations",
    "compose_divergence",
    "posture_from_score",
    "run_scenario",
    "make_seed",
]

__version__ = "0.2.0"
