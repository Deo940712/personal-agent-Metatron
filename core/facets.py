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

from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
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


# ── routine 抽取器(part-007-slice-002:確定性 producer,無 LLM)──────────

# 一天分四個時段桶;完成時間落在哪桶即該桶 +1。routine facet 記錄使用者
# 「通常在哪個時段完成事情」——純確定性,不猜、不推斷。
_TIME_BUCKETS = (
    ("early_morning", range(5, 9)),    # 05:00-08:59
    ("morning", range(9, 12)),         # 09:00-11:59
    ("afternoon", range(12, 18)),      # 12:00-17:59
    ("evening", range(18, 23)),        # 18:00-22:59
    ("night", list(range(23, 24)) + list(range(0, 5))),  # 23:00-04:59
)


def _bucket_of(hour: int) -> str:
    for name, hours in _TIME_BUCKETS:
        if hour in hours:
            return name
    return "night"


@dataclass(frozen=True, slots=True)
class RoutineObservation:
    """routine 抽取結果:某時段的活躍度 + 支撐它的 source_ids(可回水)。"""

    facet_key: str        # 'active_bucket'
    value: str            # 主時段桶名
    evidence_ids: list[str]
    distinct_days: int


def extract_routine(completions: list[dict]) -> RoutineObservation | None:
    """從已完成的 schedule/tasks 記錄抽 routine 訊號(純函數)。

    輸入每筆需含 `done_at`(epoch)與 `source_id`(冷儲存 entry id,如 'evt:12')。
    回傳最活躍時段桶 + 支撐證據;證據不足(<MIN_EVIDENCE 或未跨 MIN_DAYS 天)→ None。
    不建 facet、不寫 DB——只回觀察,升級與落地走 detector + writer。
    """
    valid = [c for c in completions
             if isinstance(c.get("done_at"), int) and c.get("source_id")]
    if len(valid) < config.FACET_STABLE_MIN_EVIDENCE:
        return None
    buckets = Counter(_bucket_of(datetime.fromtimestamp(c["done_at"]).hour)
                      for c in valid)
    top_bucket, _ = buckets.most_common(1)[0]
    in_bucket = [c for c in valid
                 if _bucket_of(datetime.fromtimestamp(c["done_at"]).hour) == top_bucket]
    days = {datetime.fromtimestamp(c["done_at"]).strftime("%Y-%m-%d") for c in in_bucket}
    if len(days) < config.FACET_STABLE_MIN_DAYS:
        return None
    return RoutineObservation(
        facet_key="active_bucket",
        value=top_bucket,
        evidence_ids=[c["source_id"] for c in in_bucket],
        distinct_days=len(days),
    )


# ── vault 投影(part-007-slice-002:facets 是真相,筆記是可重建衍生物)──

def _projection_body(row: dict) -> str:
    return (f"{row['value']}\n\n"
            f"（class={row['facet_class']} key={row['facet_key']} "
            f"state={row['state']} confidence={row['confidence']} "
            f"evidence={row['evidence_count']}）")


def project_to_vault(db: Path | None, vault: Path, *,
                     min_confidence: float = 0.0) -> dict:
    """把 active facets 投影成 vault/agent/profile/ 可讀筆記(source_ids 溯源）。

    投影是衍生物:facets 是真相,壞了可整批重投影(idempotent by facet_class+key
    ——同 key 既有投影筆記先標 superseded 再寫新版,避免重複)。低 confidence 不投影。
    回傳統計 dict。
    """
    from core import ltm, stm

    ltm.init_vault(vault)
    existing = {}  # (class,key) -> registry entry(既有投影)
    for entry in ltm.registry_entries(vault):
        if not entry["path"].startswith("agent/profile/"):
            continue
        note = ltm.read_note(vault, entry["path"])
        if note is None or note["frontmatter"].get("superseded_by"):
            continue
        fm = note["frontmatter"]
        key = (fm.get("facet_class"), fm.get("facet_key"))
        if key != (None, None):
            existing[key] = entry["id"]

    written, skipped, superseded = 0, 0, 0
    for row in stm.facet_list(db):
        if row["confidence"] < min_confidence:
            skipped += 1
            continue
        evidence_ids = _load_json_list(row["evidence_ids"])
        frontmatter = {
            "source": "agent_knowledge",
            "facet_class": row["facet_class"],
            "facet_key": row["facet_key"],
            "facet_state": row["state"],
            "user_state": row["user_state"],
            "source_ids": evidence_ids,
            "tags": ["preference"] if row["facet_class"] == "preference" else ["profile"],
            "summary": f"{row['facet_class']}/{row['facet_key']} = {row['value']}",
        }
        title = f"{row['facet_class']}:{row['facet_key']}"
        new_id = ltm.write_note(vault, "agent/profile",
                                title=title, body=_projection_body(row),
                                frontmatter=frontmatter, ts=stm.now())
        old_id = existing.get((row["facet_class"], row["facet_key"]))
        if old_id and old_id != new_id:
            if ltm.mark_superseded(vault, old_id, new_id):
                superseded += 1
        written += 1
    return {"projected": written, "skipped_low_confidence": skipped,
            "resupersede": superseded}


def _load_json_list(raw: str | None) -> list[str]:
    import json
    if not raw:
        return []
    try:
        val = json.loads(raw)
        return val if isinstance(val, list) else []
    except (ValueError, TypeError):
        return []
