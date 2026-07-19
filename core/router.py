"""意圖路由（part-012；backlog-033 對話式 orchestrator 的理解層）。

單次 cheap LLM 呼叫把訊息分類成七 intent 之一；欄位級驗證（enum / date_range
ISO 格式 + 擋幻覺日期）；LLM 失敗或非法輸出 → Route(intent='fallback')——
呼叫端退回現行 schedule 解析路徑，**降級不斷服務**。

只分類，不執行：寫入紀律（提案→writer→確認）由下游能力層維持，不在此。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path

from core import stm

INTENTS = ("schedule_write", "schedule_query", "knowledge", "knowledge_list",
           "advice", "status", "directive", "smalltalk", "unclear")

# date_range 合理界限：過去/未來各一年內（擋 LLM 幻覺日期如 1970/2099）
_RANGE_LIMIT_DAYS = 366


@dataclass(frozen=True, slots=True)
class Route:
    """分類結果。intent='fallback' = 分類失敗，呼叫端走現行路徑。"""

    intent: str
    argument: str = ""
    date_range: tuple[str, str] | None = None   # ISO (start, end)，只在 schedule_query
    guess: tuple[str, ...] = field(default_factory=tuple)  # 只在 unclear


FALLBACK = Route(intent="fallback")


def _valid_date_range(raw, today: date) -> tuple[str, str] | None:
    """驗證 LLM 給的 date_range：list[2] ISO、起 ≤ 迄、界限內。非法 → None。"""
    if not isinstance(raw, list) or len(raw) != 2:
        return None
    try:
        start = date.fromisoformat(str(raw[0]))
        end = date.fromisoformat(str(raw[1]))
    except (ValueError, TypeError):
        return None
    if start > end:
        return None
    limit = timedelta(days=_RANGE_LIMIT_DAYS)
    if abs(start - today) > limit or abs(end - today) > limit:
        return None                              # 幻覺日期（過遠過去/未來）
    return (start.isoformat(), end.isoformat())


def _parse(result: dict, today: date) -> Route:
    """LLM 輸出 → Route。任何欄位非法 → FALLBACK（不猜、不修）。"""
    if not isinstance(result, dict):
        return FALLBACK
    intent = result.get("intent")
    if intent not in INTENTS:
        return FALLBACK
    argument = result.get("argument", "")
    if not isinstance(argument, str):
        return FALLBACK

    date_range = None
    if intent == "schedule_query":
        date_range = _valid_date_range(result.get("date_range"), today)
        if date_range is None:
            # 查詢意圖但時間窗算不出/非法 → unclear(讓系統追問,不亂查)
            return Route(intent="unclear", argument=argument,
                         guess=("schedule_query",))

    guess: tuple[str, ...] = ()
    if intent == "unclear":
        raw_guess = result.get("guess", [])
        if isinstance(raw_guess, list):
            guess = tuple(g for g in raw_guess if g in INTENTS)[:2]

    return Route(intent=intent, argument=argument.strip(),
                 date_range=date_range, guess=guess)


def classify(text: str, db: Path | None = None, *,
             now_ts: int | None = None, _api=None) -> Route:
    """訊息 → Route。LLM 失敗（LLMError/壞 JSON）→ FALLBACK，永不拋出。"""
    from core import llm, subagents

    today = datetime.fromtimestamp(now_ts if now_ts is not None
                                   else stm.now()).date()
    system = subagents.load_contract("router")
    user = f"今天日期:{today.isoformat()}\n訊息:{text.strip()}"
    try:
        result = llm.complete_json(system, user, db=db, purpose="route", _api=_api)
    except llm.LLMError:
        return FALLBACK
    return _parse(result, today)
