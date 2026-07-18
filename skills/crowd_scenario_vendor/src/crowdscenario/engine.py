"""The Crowd Scenario Engine — a non-authoritative narrative side-rail.

Reads ONLY a frozen ScenarioSeed; emits ONLY a ``CrowdNarrative`` (a categorical
crowd stance + narrative — NO numeric modifier). It reads no raw market number and
returns no decision-grade scalar, so it is safe to run alongside any decision
system without ever being able to move a computed number.

Rehearse (not predict) how 10 Taiwan retail investor archetypes might react to an
already-decided market event: each archetype speaks in its own voice, reads the
frozen ordinal context by its own sensitivity, and the whole thing is ordered into
a who-moves-first reaction chain. Deterministic per seed.
"""

from __future__ import annotations

import hashlib

from crowdscenario.contracts import (
    ContractError,
    CrowdNarrative,
    PersonaReaction,
    ScenarioSeed,
)
from crowdscenario.domains import DomainPack
from crowdscenario.domains.stock_tw import STOCK_TW
from crowdscenario.narrator.base import EngineFacts, NarratorBackend, PersonaFact
from crowdscenario.narrator.deterministic import DeterministicNarrator

# Horizon shifts WHO leads the chain. Three genuinely distinct orderings (domain-neutral,
# so this stays engine-level; the per-horizon display wording lives on ``pack.horizon_frame``):
#   - intraday: the fastest herders lead        -> sort by herding, descending
#   - long:     the slow fundamentals cohorts lead -> sort by herding, ascending
#   - swing:    no cohort clearly leads (middle ground) -> keep roster order, no herding sort
# swing is deliberately NOT a herding sort so it cannot collapse into intraday/long.
_HORIZON_ORDER = {"intraday": "herding_desc", "swing": "roster", "long": "herding_asc"}
_DEFAULT_FRAME = "波段"


def _internal_view(seed: ScenarioSeed) -> float:
    """Deterministic, reproducible crowd lean in [-1, +1] (internal only)."""
    digest = hashlib.sha256(seed.seed_hash.encode("utf-8")).hexdigest()
    return round((int(digest[:8], 16) / 0xFFFFFFFF) * 2 - 1, 4)


def _consensus(view: float) -> str:
    if view > 0.15:
        return "positive"
    if view < -0.15:
        return "negative"
    return "neutral"


# consensus_mode vocabulary:
#   - "hashed": direction from the seed hash (the legacy default).
#   - "aggregate": persona majority, but personas react against the HASHED baseline
#     (so the hash still tints the initial lean before the majority is taken).
#   - "aggregate_neutral": EXPERIMENTAL (part-008). Personas react against a NEUTRAL
#     baseline, so the emitted direction is a pure function of the ordinal context +
#     per-persona sensitivity — the seed hash never touches the direction. Kept for the
#     consensus-model evaluation; NOT the public default. Its persona_samples therefore
#     differ from the hashed/aggregate modes (different baseline), which is expected.
CONSENSUS_MODES = ("hashed", "aggregate", "aggregate_neutral")

# Net-stance threshold for aggregate mode: a clear majority (|net| > 1, i.e. at least a
# 2-vote edge) flips the crowd; anything tighter stays neutral. Integer comparison, so
# it is fully deterministic with no reliance on dict/set iteration order.
_AGGREGATE_THRESHOLD = 1


def _aggregate_consensus(stances: tuple[int, ...]) -> str:
    """Categorical crowd consensus derived from the persona majority (deterministic).

    Pure function of the integer net stance — no scalar leaves, no randomness, no
    iteration-order dependence. ``net > 1`` -> positive, ``net < -1`` -> negative,
    otherwise neutral.
    """
    net = sum(stances)
    if net > _AGGREGATE_THRESHOLD:
        return "positive"
    if net < -_AGGREGATE_THRESHOLD:
        return "negative"
    return "neutral"


def _stance_for(
    persona: str, consensus: str, ordinal: dict[str, str], pack: DomainPack = STOCK_TW
) -> int:
    """This persona's categorical stance (-1|0|1) under ``pack``.

    Baseline lean comes from the seed-derived consensus (a contra persona fades it,
    a pro persona amplifies it). Each persona then applies its OWN reading of every
    ordinal axis the pack defines, weighted by its per-axis sensitivity, so within one
    scenario cohorts diverge instead of flipping in lockstep. Deterministic and
    scalar-free: the internal lean is thresholded back to -1|0|1 before it leaves.
    """
    base = 0.0 if consensus == "neutral" else (1.0 if consensus == "positive" else -1.0)
    lean = base if persona not in pack.contra_ids else -base

    if ordinal:
        weights = pack.sensitivity.get(persona, (0.0,) * len(pack.axes))
        tilt = 0.0
        for axis, weight in zip(pack.axes, weights, strict=True):
            bucket = ordinal.get(axis.name)
            if bucket is not None:
                if bucket not in axis.tilt:
                    raise ContractError(f"unknown bucket {bucket!r} for axis {axis.name!r}")
                tilt += weight * axis.tilt[bucket]
        lean += 0.9 * tilt

    if lean > 0.15:
        return 1
    if lean < -0.15:
        return -1
    return 0


def _pick_voice(pack: DomainPack, persona: str, stance: int, seed_hash: str) -> str:
    """The voice line for a persona/stance, choosing a variant deterministically.

    If the pack supplies ``voice_variants`` for this persona/stance, one is picked by the
    seed hash (so the same seed always yields the same line, but different scenarios read
    differently). Otherwise the single ``voice`` line is used — making a pack with no
    variants byte-identical to the pre-variant engine. The per-persona hash offset keeps
    different personas from all landing on the same variant index.
    """
    variants = pack.voice_variants.get(persona, {}).get(stance)
    if variants:
        offset = (pack.persona_ids.index(persona) * 2) % max(len(seed_hash) - 2, 1)
        idx = int(seed_hash[offset:offset + 2] or "0", 16) % len(variants)
        return variants[idx]
    return pack.voice.get(persona, {}).get(stance, "條件式情境反應。")


def _excerpt_for(persona: str, stance: int, label: str, pack: DomainPack, seed_hash: str) -> str:
    """This persona's own line for its stance under the scenario `label`."""
    voice = _pick_voice(pack, persona, stance, seed_hash)
    return f"[synthetic|{persona}] 對「{label}」:{voice}(非預測)"


def _reaction_chain(
    samples: tuple[PersonaReaction, ...], seed: ScenarioSeed, pack: DomainPack
) -> str:
    """A 2-3 step who-moves-first storyline, ordered by horizon.

    Horizon picks the ordering (intraday -> fastest herders lead; long -> slow
    fundamentals cohorts lead; swing -> roster order, a genuine middle ground that leans
    on neither speed extreme). Intensity widens the framing (severe -> note the tail also
    capitulates). Pure narrative — no number is produced or consumed.
    """
    movers = [s for s in samples if s.stance != 0]
    frame = pack.horizon_frame.get(seed.horizon, _DEFAULT_FRAME)
    if not movers:
        return f"- 在{frame}情境下各型態普遍無感,無明顯二階反應鏈(情境偏中性)。"
    # Stable, deterministic base order: the persona's fixed roster position, so a
    # different pack can never reorder ambiguously and ties always break the same way.
    order = {pid: i for i, pid in enumerate(pack.persona_ids)}
    movers.sort(key=lambda s: order.get(s.archetype_id, 0))
    strategy = _HORIZON_ORDER.get(seed.horizon, "roster")
    if strategy == "herding_desc":
        movers.sort(key=lambda s: pack.herding.get(s.archetype_id, 0.5), reverse=True)
    elif strategy == "herding_asc":
        movers.sort(key=lambda s: pack.herding.get(s.archetype_id, 0.5))
    # strategy == "roster": leave the roster-order sort in place (swing middle ground).
    anchors = [s for s in samples if s.stance == 0]
    severe = seed.intensity == "severe"

    def _line(n: int, s: PersonaReaction, verb: str) -> str:
        name = pack.display_name.get(s.archetype_id, s.archetype_id)
        voice = _pick_voice(pack, s.archetype_id, s.stance, seed.seed_hash)
        return f"{n}. **{name}** {verb} —— {voice}"

    steps = [_line(1, movers[0], f"在{frame}情境最先動作")]
    if len(movers) > 1:
        steps.append(_line(2, movers[1], "跟進"))
    tail = anchors[0] if anchors else movers[-1]
    # Severe shocks widen the middle of the chain: a third mover (when present, and not
    # already the tail) also gets dragged in before the tail. Mild keeps the original
    # 3-step shape exactly (zero drift).
    if severe and len(movers) > 2 and movers[2] is not tail:
        steps.append(_line(len(steps) + 1, movers[2], "也被帶動"))
    tail_verb = (
        "最終也跟隨"
        if (severe and tail.stance != 0)
        else ("不為所動" if tail.stance == 0 else "最後才反應")
    )
    steps.append(_line(len(steps) + 1, tail, tail_verb))
    return "\n".join(steps)


def run_scenario(
    seed: ScenarioSeed,
    pack: DomainPack = STOCK_TW,
    n_personas: int = 30,
    narrator: NarratorBackend | None = None,
    consensus_mode: str = "aggregate_neutral",
) -> CrowdNarrative:
    """Rehearse the crowd reaction for one already-decided event. Deterministic.

    The categorical facts — ``crowd_consensus`` (neutral vocabulary) and every persona
    ``stance`` — are decided HERE, firewalled, before any narrator runs. The narrator
    only turns those fixed facts into prose; it can never change a stance or a
    consensus. ``narrator`` defaults to ``DeterministicNarrator`` (offline, stdlib,
    byte-identical to the original output). Pass a ``FusionNarrator`` for LLM prose;
    the emitted ``crowd_consensus``/``persona_samples`` are unchanged regardless.

    ``consensus_mode`` picks how the crowd's *direction* is decided (all deterministic,
    all scalar-free):

    - ``"aggregate_neutral"`` (**default since 0.2.0**): personas react off a NEUTRAL
      baseline, then the emitted consensus is the net-sign of their stances. The direction
      is a pure function of the ordinal context + per-persona sensitivity — the seed hash
      never touches it. This is the most explainable and semantically consistent model
      (see the part-008 consensus evaluation).
    - ``"hashed"``: the direction comes from the seed hash — the original pre-0.2.0
      behaviour, kept as an explicit option.
    - ``"aggregate"``: the persona **majority**, but off a HASHED baseline (so the hash
      still tints the initial lean before the majority is taken).
    """
    if seed.domain_id != pack.domain_id:
        raise ContractError(
            f"seed domain {seed.domain_id!r} does not match pack domain {pack.domain_id!r}"
        )
    if consensus_mode not in CONSENSUS_MODES:
        raise ContractError(
            f"consensus_mode {consensus_mode!r} not in {CONSENSUS_MODES}"
        )
    narrator = narrator or DeterministicNarrator()
    hashed_consensus = _consensus(_internal_view(seed))
    label = seed.market_scenario_label
    ordinal = dict(seed.ordinal_context)

    # The persona baseline: hashed/aggregate lean on the seed-derived consensus;
    # aggregate_neutral deliberately starts from neutral so the hash never tints direction.
    persona_baseline = "neutral" if consensus_mode == "aggregate_neutral" else hashed_consensus

    def _sample(a: str) -> PersonaReaction:
        stance = _stance_for(a, persona_baseline, ordinal, pack)
        return PersonaReaction(
            archetype_id=a,
            stance=stance,
            register=pack.register,
            excerpt=_excerpt_for(a, stance, label, pack, seed.seed_hash),
        )

    samples = tuple(_sample(a) for a in pack.persona_ids)
    # Pick the emitted direction. hashed keeps the seed-derived baseline; the two
    # aggregate modes take the persona majority (samples already decided above, so this
    # never re-runs the stance logic).
    consensus = (
        _aggregate_consensus(tuple(s.stance for s in samples))
        if consensus_mode in ("aggregate", "aggregate_neutral")
        else hashed_consensus
    )
    chain = _reaction_chain(samples, seed, pack)
    frame = pack.horizon_frame.get(seed.horizon, _DEFAULT_FRAME)
    facts = EngineFacts(
        label=label,
        consensus=consensus,
        consensus_display=pack.consensus_display.get(consensus, consensus),
        frame=frame,
        intensity_zh=pack.intensity_display.get(seed.intensity, seed.intensity),
        personas=tuple(
            PersonaFact(
                persona_id=s.archetype_id,
                display_name=pack.display_name.get(s.archetype_id, s.archetype_id),
                stance=s.stance,
                voice_line=_pick_voice(pack, s.archetype_id, s.stance, seed.seed_hash),
            )
            for s in samples
        ),
        reaction_chain=chain,
    )
    result = narrator.render(facts)
    return CrowdNarrative(
        seed_id=seed.seed_id,
        rng_seed=seed.rng_seed,
        n_personas=n_personas,
        crowd_consensus=consensus,
        narrative_md=result.narrative_md,
        persona_samples=samples,
        narrator_backend=result.backend,
        narrator_notes=result.notes,
    )
