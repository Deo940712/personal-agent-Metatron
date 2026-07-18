"""Compute crowd-vs-external divergence at report time (no write-back).

The engine never knows your own posture — it is firewalled from it. So the
divergence between the synthetic crowd and your own read is computed *here*, at
report time, from the crowd narrative plus a posture you supply. It emits a
categorical bucket + intensity, never a scalar that could tilt a decision.
"""

from __future__ import annotations

from crowdscenario.contracts import CONSENSUS, ContractError, CrowdNarrative, NarrativeDivergence

_ORDER = {"negative": -1, "neutral": 0, "positive": 1}
_BUCKETS = ("LOW", "MEDIUM", "HIGH")

# Conditional, scalar-free framing per posture (rehearsal wording, never advice).
_CROWD_LEAN = {
    "negative": "合成群眾偏保守",
    "neutral": "合成群眾態度分歧",
    "positive": "合成群眾偏樂觀",
}
_YOUR_LEAN = {
    "negative": "你的判讀偏保守",
    "neutral": "你的判讀中性",
    "positive": "你的判讀偏樂觀",
}


def _storylines_for(crowd: str, external: str, bucket: str) -> tuple[str, ...]:
    """Counterfactual, conditional storylines for a crowd-vs-your-own divergence.

    Deterministic and scalar-free: a pure function of the two categorical postures and
    the divergence bucket. All lines are conditional ("若…可能…") rehearsal framing —
    never a forecast, never a number, never an instruction. This is the only place the
    divergence turns into prose; it decides nothing and writes back nowhere.
    """
    crowd_lean = _CROWD_LEAN[crowd]
    your_lean = _YOUR_LEAN[external]
    if bucket == "LOW":
        return (
            f"{crowd_lean}，{your_lean}，兩者方向大致一致，無明顯分歧劇本。",
            "一致不代表正確：同向也可能同時看錯，這只是排練，不構成任何判斷依據。",
        )
    if bucket == "MEDIUM":
        return (
            f"{crowd_lean}，而{your_lean}，兩者存在部分分歧。",
            "若群眾這一側較貼近後續發展，你這類判讀可能低估了某些面向（條件式推演）。",
            "反過來，若你這側較貼近，群眾這類反應可能正被情境情緒帶動（條件式推演）。",
        )
    # HIGH
    return (
        f"{crowd_lean}，而{your_lean}，兩者顯著相反。",
        "若群眾這一側較貼近後續，你這類判讀可能忽略了群體會如何反應（條件式推演）。",
        "若你這一側較貼近，群眾這類反應可能是在追逐雜訊而非訊號（條件式推演）。",
        "顯著分歧本身就是值得留意的排練訊號，但它不決定任何動作。",
    )


def posture_from_score(score: float) -> str:
    """Turn any numeric read in roughly [-1, +1] into a categorical posture.

    Convenience so callers with their own composite/score can get a posture to
    diff against the crowd. The number stops here — only the label goes forward.
    Returns the domain-neutral vocabulary (negative | neutral | positive).
    """
    if score > 0.1:
        return "positive"
    if score < -0.1:
        return "negative"
    return "neutral"


def compose_divergence(narrative: CrowdNarrative, external_posture: str) -> NarrativeDivergence:
    """Diff the synthetic crowd stance against your own categorical posture."""
    if external_posture not in CONSENSUS:
        raise ContractError("external_posture out of vocabulary")
    gap = abs(_ORDER[narrative.crowd_consensus] - _ORDER[external_posture])  # 0 | 1 | 2
    bucket = _BUCKETS[gap]
    return NarrativeDivergence(
        seed_id=narrative.seed_id,
        crowd_consensus=narrative.crowd_consensus,
        external_posture=external_posture,
        divergence_bucket=bucket,
        narrative_intensity=gap + 1,
        storylines=_storylines_for(narrative.crowd_consensus, external_posture, bucket),
    )
