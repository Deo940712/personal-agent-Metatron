"""FusionNarrator — 2 writer LLMs + 1 judge LLM, every output firewall-screened.

The categorical decision is ALREADY made by the engine before a narrator ever runs;
fusion only competes to write the best *prose* over those fixed facts. The flow:

    writer_a(prompt) -> text_a ─┐
                                 ├─ firewall.scan_violations → drop any dirty candidate
    writer_b(prompt) -> text_b ─┘
                                 │
              surviving candidates → judge(prompt) picks/merges the best
                                 │
                    judge output → firewall.scan_violations again
                                 │
        clean → use it;  nothing clean anywhere → fall back to DeterministicNarrator

Guarantees:
- The emitted consensus and every persona stance come from the engine, never the LLMs.
- Every LLM output (both writers AND the judge) passes the deterministic firewall
  scanner before it can enter a CrowdNarrative. A numeric leak or an order phrase means
  that candidate is discarded, not sanitised.
- There is ALWAYS a safe output: if no candidate survives (or a model raises), the
  deterministic table-lookup narrator is used. Fusion never crashes the pipeline and
  never emits un-screened text.

The three ``ModelFn`` callables are INJECTED (text-in / text-out), so the core stays
zero-dependency and the whole thing is offline-testable with fakes.
"""

from __future__ import annotations

from crowdscenario.narrator import firewall
from crowdscenario.narrator.base import EngineFacts, ModelFn, NarratorResult
from crowdscenario.narrator.deterministic import DeterministicNarrator

# Textual stance labels for the prompt. The engine's internal stance is an ordinal
# (-1|0|+1), but we never hand a bare number to an LLM: a model could echo "stance=-1"
# verbatim and surface an engine-internal signal in prose. Words carry the same meaning
# with nothing a downstream reader could mistake for a metric.
_STANCE_LABEL = {-1: "偏空", 0: "中性", 1: "偏多"}


def _facts_block(facts: EngineFacts) -> str:
    """Render the already-decided facts a writer must stay faithful to (no numbers)."""
    lines = [
        f"情境標籤:{facts.label}",
        f"時間尺度:{facts.frame}|強度:{facts.intensity_zh}",
        f"合成群眾傾向(已定,不可更改):{facts.consensus_display}",
        "各人格立場(已定,不可更改;偏空/中性/偏多):",
    ]
    for p in facts.personas:
        label = _STANCE_LABEL.get(p.stance, "中性")
        lines.append(f"- {p.display_name}(立場:{label}):{p.voice_line}")
    return "\n".join(lines)


_WRITER_INSTRUCTION = (
    "你是合成群眾情境的敘事撰稿。根據以下【已定事實】改寫成流暢的繁體中文敘事,"
    "遵守:①立場與各人格 stance 已定,不可更改;②全程條件式語氣(『若…這類人格可能…』),"
    "不得預測真實標的走勢;③絕不出現任何數字/價格/百分比/貨幣;④不得出現買進賣出、加碼減碼、"
    "委託單等下單語;⑤研究/教育框架,非投資建議。只輸出敘事本文。\n\n【已定事實】\n"
)

_JUDGE_INSTRUCTION = (
    "你是敘事裁判。以下有數個候選敘事,它們的立場與人格 stance 都相同且已定。"
    "請挑出(或融合成)最忠實、最流暢、最無 AI 腔、最符合條件式研究框架的一版,"
    "同樣不得出現任何數字或下單語。只輸出最終敘事本文。\n\n"
)


class FusionNarrator:
    """Two writers propose, one judge decides; the firewall screens every output."""

    def __init__(
        self,
        writer_a: ModelFn,
        writer_b: ModelFn,
        judge: ModelFn,
        fallback: DeterministicNarrator | None = None,
    ) -> None:
        self._writer_a = writer_a
        self._writer_b = writer_b
        self._judge = judge
        self._fallback = fallback or DeterministicNarrator()

    def _run_clean(self, model: ModelFn, prompt: str) -> str | None:
        """Call a model and return its text only if it passes the firewall scan."""
        try:
            text = model(prompt)
        except Exception:  # noqa: BLE001 — any model failure degrades to fallback, never crashes
            return None
        if not text or not text.strip():
            return None
        return text if firewall.is_clean(text) else None

    def render(self, facts: EngineFacts) -> NarratorResult:
        notes: list[str] = []
        writer_prompt = _WRITER_INSTRUCTION + _facts_block(facts)

        candidates: list[str] = []
        for tag, writer in (("writer_a", self._writer_a), ("writer_b", self._writer_b)):
            text = self._run_clean(writer, writer_prompt)
            if text is None:
                notes.append(f"{tag}:rejected")
            else:
                candidates.append(text)
                notes.append(f"{tag}:accepted")

        if not candidates:
            fb = self._fallback.render(facts)
            return NarratorResult(
                narrative_md=fb.narrative_md,
                backend="fusion:fallback",
                notes=(*notes, "no_writer_survived"),
            )

        judge_prompt = _JUDGE_INSTRUCTION + "\n\n---\n\n".join(
            f"候選 {i + 1}:\n{c}" for i, c in enumerate(candidates)
        )
        chosen = self._run_clean(self._judge, judge_prompt)
        if chosen is not None:
            return NarratorResult(
                narrative_md=chosen, backend="fusion:judge", notes=(*notes, "judge:accepted")
            )

        # Judge failed or produced a dirty output: fall back to the first clean writer
        # candidate, which already passed the scanner.
        notes.append("judge:rejected")
        return NarratorResult(
            narrative_md=candidates[0], backend="fusion:writer", notes=tuple(notes)
        )
