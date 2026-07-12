"""子 agent 執行器(自寫薄層;ARCHITECTURE §3 Clean Summary Discipline)。

純函數型子 agent:讀 agents/<name>.md 契約 → 組 prompt(最小輸入)→
單次 LLM 呼叫 → 解析提案 dict。不碰 DB 寫入(那是 writer 的事)。

契約檔格式:markdown,`## System Prompt` 之後到下一個 `## ` 前是系統 prompt;
`## Few-shot` 區塊原樣附在系統 prompt 後(提供範例)。
"""

from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path

from core import llm

AGENTS_DIR = Path(__file__).resolve().parents[1] / "agents"


class SubagentError(RuntimeError):
    """契約檔缺失或 LLM 輸出無法用(已含重試)。"""


def load_contract(name: str) -> str:
    """回傳完整系統 prompt(System Prompt + Few-shot 區塊)。"""
    path = AGENTS_DIR / f"{name}.md"
    if not path.exists():
        raise SubagentError(f"contract not found: {path}")
    text = path.read_text(encoding="utf-8")
    marker = "## System Prompt"
    if marker not in text:
        raise SubagentError(f"contract missing '{marker}' section: {path}")
    return text[text.index(marker) + len(marker):].strip()


def _now_line(now_epoch: int | None) -> str:
    epoch = now_epoch or int(time.time())
    local = datetime.fromtimestamp(epoch)
    # 時區偏移(prompt 需知道本地時區才能換算「明天下午兩點」)
    offset_min = -time.timezone // 60 if not time.daylight else -time.altzone // 60
    sign = "+" if offset_min >= 0 else "-"
    tz = f"UTC{sign}{abs(offset_min) // 60}"
    return f"NOW={local.strftime('%Y-%m-%dT%H:%M')} (epoch {epoch}, {tz})"


def run_schedule(text: str, *, now_epoch: int | None = None,
                 active_items: list[dict] | None = None,
                 db: Path | None = None, _api=None) -> dict:
    """schedule 子 agent:自然語言 → 提案 dict(未經 writer 驗證)。

    回傳 {"error": ...} 表示 LLM 判定不是行程/待辦。
    LLMError/SubagentError 由呼叫端(orchestrator)處理。
    """
    system = load_contract("schedule")
    lines = [_now_line(now_epoch)]
    if active_items:
        listing = "; ".join(
            f"#{r['id']} {r['title']} @{r.get('start_at', r.get('due_at'))}"
            for r in active_items[:20])
        lines.append(f"現有項目: {listing}")
    lines.append(text)
    user = "\n".join(lines)

    proposal = llm.complete_json(system, user, db=db, purpose="schedule-parse", _api=_api)

    # 防禦:LLM 忘了帶 evidence 時補上原句(evidence 定義=使用者原句)
    if "error" not in proposal and not proposal.get("evidence"):
        proposal["evidence"] = [text]
    return proposal
