"""The default narrator: deterministic, offline, stdlib-only table-lookup prose.

This is the reference backend. It builds the exact narrative the engine has always
built — a header, the rehearsal disclaimer, the crowd lean, and the deterministic
reaction chain — straight from the categorical ``EngineFacts``. No LLM, no network,
no randomness: same facts → byte-identical prose. It is also the fallback the fusion
narrator drops back to when no LLM candidate survives the firewall scan.
"""

from __future__ import annotations

from crowdscenario.narrator.base import EngineFacts, NarratorResult


class DeterministicNarrator:
    """Render ``EngineFacts`` into the canonical table-lookup narrative."""

    def render(self, facts: EngineFacts) -> NarratorResult:
        narrative = (
            f"## 群眾情境推演:{facts.label}"
            f"(時間尺度:{facts.frame}·強度:{facts.intensity_zh})\n\n"
            "*合成人格情境分布,不代表真實市場調查;非預測;未經回測。*\n\n"
            f"合成群眾傾向:**{facts.consensus_display}**。"
            f"以下為各型態的二階反應鏈(依{facts.frame}情境的跟風順序,條件式):\n\n"
            f"{facts.reaction_chain}\n\n"
            "> 本側軌只產敘事,不決定任何數字、不回寫決策層。"
        )
        return NarratorResult(narrative_md=narrative, backend="deterministic")
