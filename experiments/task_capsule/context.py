"""bounded historical context assembly + authority revalidation(Todo 8)。

只 exact task_id match;全部內容標 historical/non-authoritative;可設 byte budget;
固定欄位優先序;field-item 邊界截斷並回 omitted 計數。動作前對比每個 capsule 引用的
authority version/hash 與 current bundle;缺失或不符 → stale,排除並標記重讀,
且 actionable=False。永不以 session/topic/free-text 合併。
"""

from __future__ import annotations

from dataclasses import dataclass

from experiments.task_capsule import models as m

# 固定欄位優先序(work plan Todo 8)
_PRIORITY: tuple[tuple[str, str], ...] = (
    ("goal", "single"),
    ("constraints", "list"),
    ("decisions", "list"),
    ("completed", "list"),
    ("failed_attempts", "list"),
    ("open_loops", "list"),
    ("next_action", "single"),
)

_HISTORICAL_HEADER = "[historical / 非權威 — 動作前需核對權威]"


@dataclass(frozen=True, slots=True)
class Assembly:
    task_id: str
    text: str
    historical: bool
    actionable: bool
    omitted_count: int
    stale_sources: tuple[str, ...]


def _items_for(capsule: m.Capsule, field: str, kind: str) -> list[str]:
    val = getattr(capsule, field)
    if kind == "single":
        return [f"{field}: {val}"]
    return [f"{field}: {item}" for item in val]


def _revalidate(capsule: m.Capsule, current: dict[str, str]) -> tuple[str, ...]:
    """對比 capsule.authority_versions 與 current bundle。回 stale source keys。

    缺失(current 沒有該 source)或版本不符 → stale。無 authority_versions →
    全體不可行動(以特殊 sentinel 表示,呼叫端據此設 actionable=False)。
    """
    stale: list[str] = []
    for key, ver in capsule.authority_versions:
        cur = current.get(key)
        if cur is None or cur != ver:
            stale.append(key)
    return tuple(stale)


def assemble(capsule: m.Capsule, *, current_authority: dict[str, str],
             max_bytes: int = 4096) -> Assembly:
    """組裝 bounded historical context 並核對權威。"""
    stale = _revalidate(capsule, current_authority)
    # 無可核對的權威版本 → 不可行動(無法確認 capsule 仍反映現況)
    has_authority = len(capsule.authority_versions) > 0
    actionable = has_authority and len(stale) == 0

    # 依優先序展開所有 field items
    ordered_items: list[str] = []
    for field, kind in _PRIORITY:
        ordered_items.extend(_items_for(capsule, field, kind))

    # budget:只計內容 items 的 UTF-8 bytes(header 是固定框架,不佔 budget)。
    # 逐 item 加入,超出即停(field-item 邊界截斷)。max_bytes=0 → 全略。
    kept: list[str] = []
    used = 0
    omitted = 0
    for item in ordered_items:
        cost = len(item.encode("utf-8"))
        if kept:
            cost += 1                                     # 換行分隔
        if used + cost <= max_bytes:
            kept.append(item)
            used += cost
        else:
            omitted += 1

    text = ""
    if kept:
        text = _HISTORICAL_HEADER + "\n" + "\n".join(kept)

    return Assembly(
        task_id=capsule.task_id,
        text=text,
        historical=True,
        actionable=actionable,
        omitted_count=omitted,
        stale_sources=stale,
    )
