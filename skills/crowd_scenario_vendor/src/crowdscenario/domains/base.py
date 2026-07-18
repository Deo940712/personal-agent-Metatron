"""The ``DomainPack`` protocol: pluggable personas + ordinal axes + display labels.

The engine core is domain-agnostic — the same stance/consensus/chain logic rehearses a
stock crowd, a product launch, or a software migration, depending solely on which pack
you hand it. A pack bundles everything the engine once hard-coded for its first domain
(Taiwan stocks):

- ``persona_ids`` — the closed persona roster (was ``_ARCHETYPES``).
- ``contra_ids`` — personas that FADE the consensus (was ``_CONTRA``); the rest amplify.
- ``herding`` — per-persona reaction speed, used ONLY to order the narrative chain
  (was ``_HERDING``). It is never summed into a decision or the categorical stance.
- ``voice`` / ``display_name`` — per-persona, per-stance text + label (was
  ``_ARCHETYPE_VOICE`` / ``_ZH_NAME``).
- ``axes`` — the ordinal context axes (was the hard-coded discount_premium + yield),
  now a variable-length tuple; each ``Axis`` carries its own bucket function + tilt.
- ``sensitivity`` — per-persona weight on each axis, one float per axis, same order
  as ``axes`` (was ``_ARCHETYPE_SENSITIVITY``).
- ``consensus_display`` — maps the neutral CONSENSUS vocabulary to this domain's own
  display labels (stock: negative->bearish; software: negative->resist). Display only;
  never re-enters logic.
- ``register`` / ``intensity_display`` — the persona speech register and the intensity
  wording used in the narrative (were hardcoded "zh-TW" / 溫和/劇烈 in the engine);
  overridable so a non-Chinese domain can speak its own language.

FIREWALL NOTE: a pack supplies only categorical material. The per-axis ``tilt`` floats
and the ``herding`` floats are internal ordering/threshold inputs — they are collapsed
to a categorical stance (-1|0|1) inside the engine and never leave it. ``validate_pack``
refuses any pack whose parallel tables are keyed by mismatched persona sets or whose
sensitivity tuples do not match the axis count, which is how misalignment is caught
before it can corrupt a lookup or the seed hash.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType

from crowdscenario.contracts import CONSENSUS, INTENSITIES, ContractError


def _is_finite_number(value: object) -> bool:
    """True for a real finite int/float. Rejects bool (an int subclass) and NaN/inf.

    tilt/herding/sensitivity are internal ordering/threshold floats; a NaN would silently
    corrupt sorting and stance math, and a bool is not a real weight.
    """
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


@dataclass(frozen=True)
class Axis:
    """One ordinal context axis: a raw metric projected to a named bucket, plus tilt.

    ``bucket_fn`` maps a raw number to an ordinal bucket label (the ONLY thing that
    crosses the firewall). ``tilt`` maps each bucket label to a small internal float
    in roughly [-1, +1]; that float is an engine-internal stance nudge and never
    appears on an emitted artifact.
    """

    name: str
    bucket_fn: Callable[[float], str]
    tilt: Mapping[str, float]

    def __post_init__(self) -> None:
        # Freeze the tilt table read-only: a frozen dataclass only blocks rebinding the
        # attribute, not mutating the dict it points at.
        if not isinstance(self.tilt, MappingProxyType):
            object.__setattr__(self, "tilt", MappingProxyType(dict(self.tilt)))


@dataclass(frozen=True)
class DomainPack:
    """A pluggable persona/axis/vocabulary bundle. Frozen; passed in explicitly."""

    domain_id: str
    persona_ids: tuple[str, ...]
    contra_ids: frozenset[str]
    herding: Mapping[str, float]
    voice: Mapping[str, Mapping[int, str]]
    display_name: Mapping[str, str]
    axes: tuple[Axis, ...]
    sensitivity: Mapping[str, tuple[float, ...]]
    consensus_display: Mapping[str, str]
    # Narrative framing, per horizon/intensity. Kept on the pack so a non-finance
    # domain can phrase its own time-scale/shock wording (was engine _HORIZON_FRAME).
    horizon_frame: Mapping[str, str] = field(default_factory=dict)
    # OPTIONAL per-persona, per-stance voice VARIANTS. When a persona/stance has 2+
    # variants here, the engine deterministically picks one by the seed hash, so the
    # same seed always yields the same line but different scenarios read differently.
    # Empty (the default) means every persona uses its single ``voice`` line as before —
    # so a pack that supplies no variants is byte-identical to the pre-variant engine.
    voice_variants: Mapping[str, Mapping[int, tuple[str, ...]]] = field(default_factory=dict)
    # Persona speech register (was hardcoded "zh-TW" in the engine). A non-Chinese
    # domain can override it; the default reproduces the pre-part-015 value exactly.
    register: str = "zh-TW"
    # Intensity display words used in the narrative (was the hardcoded 溫和/劇烈 ternary
    # in the engine). Must cover the full INTENSITIES vocabulary; defaults keep the
    # three shipped packs byte-identical.
    intensity_display: Mapping[str, str] = field(
        default_factory=lambda: {"mild": "溫和", "severe": "劇烈"}
    )

    def __post_init__(self) -> None:
        validate_pack(self)
        _freeze_pack(self)


def _freeze_pack(pack: DomainPack) -> None:
    """Deep-freeze every pack mapping AFTER validation, so a validated pack can never be
    mutated back into an invalid state. A frozen dataclass only blocks rebinding the
    attribute; the dicts it points at stay mutable without this. ``Axis.tilt`` is frozen
    by ``Axis.__post_init__`` when each axis is constructed.
    """
    for attr in (
        "herding",
        "display_name",
        "sensitivity",
        "consensus_display",
        "horizon_frame",
        "intensity_display",
    ):
        object.__setattr__(pack, attr, MappingProxyType(dict(getattr(pack, attr))))
    # voice is nested one level: {persona: {stance: line}}.
    frozen_voice = {pid: MappingProxyType(dict(stances)) for pid, stances in pack.voice.items()}
    object.__setattr__(pack, "voice", MappingProxyType(frozen_voice))
    # voice_variants is nested one level: {persona: {stance: (lines,)}}.
    frozen_variants = {
        pid: MappingProxyType(dict(per_stance)) for pid, per_stance in pack.voice_variants.items()
    }
    object.__setattr__(pack, "voice_variants", MappingProxyType(frozen_variants))


def validate_pack(pack: DomainPack) -> None:
    """Weld the load-bearing invariants. Any violation is a firewall/lookup bug.

    Uses explicit ``raise ContractError`` (not ``assert``) so a bad pack is rejected
    even under ``python -O`` — a pack is only ever built once, so the cost is nil and
    the guarantee is that an invalid pack CANNOT be constructed in any run mode.

    1. Non-empty, unique persona roster (a lookup keyed by a duplicate id is undefined).
    2. Parallel tables (``herding``/``voice``/``display_name``/``sensitivity``) are keyed
       by EXACTLY ``persona_ids`` — no missing, no extra — so no lookup can miss.
    3. Every ``voice`` entry covers all three stances (-1|0|+1) with a non-empty line,
       so ``pack.voice[id][stance]`` (a bare index in the engine) can never KeyError.
    4. Every ``display_name`` is a non-empty string.
    5. Every ``sensitivity`` tuple has one weight per axis (length == len(axes)).
    6. Every axis ``tilt`` maps to numeric values (a non-numeric tilt would break the
       stance math or smuggle a non-ordinal signal in).
    7. ``consensus_display`` covers the full neutral CONSENSUS vocabulary and maps only
       to strings (a numeric display value would be a firewall leak).
    """
    ids = pack.persona_ids
    if not ids:
        raise ContractError("persona_ids must be non-empty")
    if len(set(ids)) != len(ids):
        raise ContractError("persona_ids must be unique")

    id_set = set(ids)
    for table_name in ("herding", "voice", "display_name", "sensitivity"):
        keys = set(getattr(pack, table_name).keys())
        if keys != id_set:
            raise ContractError(f"{table_name} keys must match persona_ids exactly")

    if not (pack.contra_ids <= id_set):
        raise ContractError("contra_ids must be a subset of persona_ids")

    for pid in ids:
        stances = pack.voice[pid]
        if set(stances.keys()) != {-1, 0, 1}:
            raise ContractError(f"voice[{pid!r}] must cover stances -1, 0, +1")
        for stance, line in stances.items():
            if not isinstance(line, str) or not line.strip():
                raise ContractError(f"voice[{pid!r}][{stance}] must be a non-empty string")
        name = pack.display_name[pid]
        if not isinstance(name, str) or not name.strip():
            raise ContractError(f"display_name[{pid!r}] must be a non-empty string")

    if not pack.axes:
        raise ContractError("a pack must define at least one axis")
    axis_names = [ax.name for ax in pack.axes]
    if len(set(axis_names)) != len(axis_names):
        raise ContractError("axis names must be unique")
    for ax in pack.axes:
        for bucket_val in ax.tilt.values():
            if not _is_finite_number(bucket_val):
                raise ContractError(
                    f"axis {ax.name!r} tilt values must be finite numbers (no bool/NaN/inf)"
                )

    for pid, hval in pack.herding.items():
        if not _is_finite_number(hval):
            raise ContractError(f"herding[{pid!r}] must be a finite number (no bool/NaN/inf)")

    n_axes = len(pack.axes)
    for pid, weights in pack.sensitivity.items():
        if len(weights) != n_axes:
            raise ContractError(f"sensitivity[{pid!r}] must have one weight per axis")
        for w in weights:
            if not _is_finite_number(w):
                raise ContractError(
                    f"sensitivity[{pid!r}] weights must be finite numbers (no bool/NaN/inf)"
                )

    if set(pack.consensus_display.keys()) != set(CONSENSUS):
        raise ContractError("consensus_display must cover exactly the CONSENSUS vocabulary")
    for label in pack.consensus_display.values():
        if not isinstance(label, str):
            raise ContractError("consensus_display values must be strings (no scalar)")

    if not isinstance(pack.register, str) or not pack.register:
        raise ContractError("register must be a non-empty string")
    if not (set(INTENSITIES) <= set(pack.intensity_display.keys())):
        raise ContractError("intensity_display must cover the INTENSITIES vocabulary")
    for word in pack.intensity_display.values():
        if not isinstance(word, str) or not word:
            raise ContractError("intensity_display values must be non-empty strings")

    # Optional voice_variants: if present, every keyed persona must be in the roster and
    # each variant list must be a non-empty tuple of non-empty strings (a numeric or
    # empty variant would break the pick or smuggle a non-categorical value in).
    for pid, per_stance in pack.voice_variants.items():
        if pid not in id_set:
            raise ContractError(f"voice_variants persona {pid!r} not in persona_ids")
        for stance, variants in per_stance.items():
            if isinstance(stance, bool) or stance not in (-1, 0, 1):
                raise ContractError(f"voice_variants[{pid!r}] stance keys must be -1|0|1")
            if not isinstance(variants, tuple) or not variants:
                raise ContractError(f"voice_variants[{pid!r}][{stance}] must be a non-empty tuple")
            for v in variants:
                if not isinstance(v, str) or not v.strip():
                    raise ContractError(
                        f"voice_variants[{pid!r}][{stance}] entries must be non-empty strings"
                    )
