"""個人模型 stability detector(part-007-slice-000)。

純函數:輸入證據事實 → 輸出升級決策。不碰 DB、不呼叫 LLM,完全可重放測試。
狀態機(DESIGN §生命週期):

    observed → provisional → stable → pinned(user)/superseded/forgotten(user)

硬規則:
- 一次證據永不直接 stable(FACET_STABLE_MIN_EVIDENCE 次 + 跨 FACET_STABLE_MIN_DAYS 天)
- pinned ⇒ 評分無效化(使用者硬贏,detector 一律 hold)
- forgotten ⇒ 阻止再升級(detector 一律 block)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import config

_DAY_SECONDS = 86400

Decision = Literal["hold", "promote", "block"]


@dataclass(frozen=True, slots=True)
class FacetEvidence:
    """detector 的最小輸入:facet 目前狀態 + 證據統計(呼叫端從 DB 列組出)。"""

    state: str            # provisional|stable|superseded|forgotten
    user_state: str       # auto|pinned|forgotten
    evidence_count: int
    first_seen_at: int    # UTC epoch 秒
    last_seen_at: int     # UTC epoch 秒


@dataclass(frozen=True, slots=True)
class Assessment:
    decision: Decision
    stability: float      # promote 時建議寫入的 stability;其餘為 0.0
    reason: str


def _span_days(first_seen_at: int, last_seen_at: int) -> float:
    return max(0, last_seen_at - first_seen_at) / _DAY_SECONDS


def stability_score(evidence_count: int, span_days: float) -> float:
    """保守遞增評分:證據次數與時間跨度各佔一半,飽和於 1.0。

    到達雙門檻恰好 0.5+;之後隨證據緩增。常數在 config,真數據再調(backlog-026)。
    """
    count_part = min(1.0, evidence_count / (config.FACET_STABLE_MIN_EVIDENCE * 2))
    span_part = min(1.0, span_days / (config.FACET_STABLE_MIN_DAYS * 2))
    return round(0.5 * count_part + 0.5 * span_part, 4)


def assess(evidence: FacetEvidence) -> Assessment:
    """升級判定。純函數;同輸入必同輸出。

    決策表:
    - user_state=forgotten 或 state ∈ {forgotten, superseded} → block
    - user_state=pinned → hold(使用者已裁決,評分無效化)
    - state=stable → hold(已穩定,無事可做)
    - state=provisional 且 evidence_count ≥ MIN_EVIDENCE 且跨天 ≥ MIN_DAYS → promote
    - 其餘 provisional → hold(繼續累積)
    """
    if evidence.user_state == "forgotten" or evidence.state in ("forgotten", "superseded"):
        return Assessment("block", 0.0, f"inactive: state={evidence.state} "
                                        f"user_state={evidence.user_state}")
    if evidence.user_state == "pinned":
        return Assessment("hold", 0.0, "pinned: user decision overrides scoring")
    if evidence.state == "stable":
        return Assessment("hold", 0.0, "already stable")
    if evidence.state != "provisional":
        raise ValueError(f"unknown facet state: {evidence.state!r}")

    span = _span_days(evidence.first_seen_at, evidence.last_seen_at)
    if (evidence.evidence_count >= config.FACET_STABLE_MIN_EVIDENCE
            and span >= config.FACET_STABLE_MIN_DAYS):
        return Assessment("promote", stability_score(evidence.evidence_count, span),
                          f"threshold met: {evidence.evidence_count} evidence "
                          f"over {span:.1f} days")
    return Assessment("hold", 0.0,
                      f"accumulating: {evidence.evidence_count}/"
                      f"{config.FACET_STABLE_MIN_EVIDENCE} evidence, "
                      f"{span:.1f}/{config.FACET_STABLE_MIN_DAYS} days")


def assess_row(row: dict) -> Assessment:
    """便捷入口:直接吃 stm.facet_* 回傳的 DB 列 dict。"""
    return assess(FacetEvidence(
        state=row["state"],
        user_state=row["user_state"],
        evidence_count=row["evidence_count"],
        first_seen_at=row["first_seen_at"],
        last_seen_at=row["last_seen_at"],
    ))
