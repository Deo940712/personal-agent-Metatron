"""知識庫 CRUD 能力層(part-015-slice-002)。

明確指令解析(零 LLM)→ 組 note_write proposal → 走 writer 確認(schedule.stage)。
自然語入口(router intent)可另呼 create_from_text 以 LLM 拆解(fallback)。

指令格式:
  新增:標題 | 內容 | tag1 tag2      (tags 選填,預設 misc)
  修改:<id> 標題 | 內容 | tag1 tag2
  刪除:<id>
"""

from __future__ import annotations

from core.tools import schedule
from core.tools.contracts import CapabilityContext, CapabilityResult

_CREATE_USAGE = "用法:新增筆記 標題 | 內容 | 主題(主題選填)。例:新增筆記 RAG 心得 | 用 sqlite-vec | rag-knowledge"
_EDIT_USAGE = "用法:改筆記 <id> 標題 | 內容 | 主題。id 從「看 <主題>」取得。"
_DEFAULT_TAG = "misc"


def _parse_fields(text: str) -> tuple[str, str, list[str]] | None:
    """「標題 | 內容 | tag tag」→ (title, body, tags)。缺內容 → None。"""
    parts = [seg.strip() for seg in text.split("|")]
    if len(parts) < 2 or not parts[0] or not parts[1]:
        return None
    title, body = parts[0], parts[1]
    tags = parts[2].split() if len(parts) >= 3 and parts[2] else [_DEFAULT_TAG]
    return title, body, tags


def _proposal(action: str, target: str, evidence: str, *,
              title: str = "", body: str = "", tags: list[str] | None = None) -> dict:
    payload: dict = {"action": action}
    if action != "delete":
        payload.update({"title": title, "body": body, "tags": tags or [_DEFAULT_TAG]})
    return {
        "agent": "orchestrator",
        "proposal_type": "note_write",
        "target": target,
        "payload": payload,
        "confidence": 1.0,
        "evidence": [evidence],
    }


def create(text: str, context: CapabilityContext) -> CapabilityResult:
    """明確指令新增筆記(零 LLM)。走 writer → 需確認。"""
    parsed = _parse_fields(text)
    if parsed is None:
        return CapabilityResult(_CREATE_USAGE)
    title, body, tags = parsed
    proposal = _proposal("create", "new", f"新增筆記:{text}",
                         title=title, body=body, tags=tags)
    return schedule.stage(proposal, context)


def edit(text: str, context: CapabilityContext) -> CapabilityResult:
    """明確指令修改筆記:「<id> 標題 | 內容 | 主題」。走 writer → 需確認。"""
    head, _, rest = text.strip().partition(" ")
    if not head or not rest.strip():
        return CapabilityResult(_EDIT_USAGE)
    parsed = _parse_fields(rest)
    if parsed is None:
        return CapabilityResult(_EDIT_USAGE)
    title, body, tags = parsed
    proposal = _proposal("edit", head, f"改筆記:{text}",
                         title=title, body=body, tags=tags)
    return schedule.stage(proposal, context)


def create_from_text(text: str, context: CapabilityContext) -> CapabilityResult:
    """自然語新增(router note_create fallback):LLM 拆 title/body/tags → 走確認。

    tags 限受控詞彙表(LLM 失敗/非法 → 降級明確指令提示,不亂寫)。
    """
    import config
    from core import llm, ltm

    vault = context.vault or config.VAULT_PATH
    allowed = sorted(ltm.controlled_tags(vault))
    system = (
        "你把一段內容整理成知識庫筆記。只輸出一個 JSON object:"
        '{"title": "簡短標題", "body": "整理後的內文", "tags": ["受控標籤"]}。'
        f"tags 只能從這個清單挑 1-3 個:{', '.join(allowed)}。"
        "title <=60 字;body 保留原意可略整理。不要任何其他文字。")
    try:
        obj = llm.complete_json(system, text, db=context.db,
                                purpose="note_create", _api=context.api)
    except llm.LLMError:
        return CapabilityResult(
            "我沒能自動整理成筆記。用明確指令:\n" + _CREATE_USAGE)

    title = str(obj.get("title", "")).strip()
    body = str(obj.get("body", "")).strip()
    raw_tags = obj.get("tags", [])
    tags = [t for t in raw_tags if isinstance(t, str) and t in allowed] or [_DEFAULT_TAG]
    if not title or not body:
        return CapabilityResult("內容太少或無法整理成筆記。用:" + _CREATE_USAGE)

    proposal = _proposal("create", "new", f"新增筆記(自然語):{text}",
                         title=title, body=body, tags=tags)
    return schedule.stage(proposal, context)


def delete(note_id: str, context: CapabilityContext) -> CapabilityResult:
    """明確指令刪除筆記:「<id>」。走 writer → 需確認(刪除尤其)。"""
    nid = note_id.strip()
    if not nid:
        return CapabilityResult("用法:刪筆記 <id>。id 從「看 <主題>」取得。")
    proposal = _proposal("delete", nid, f"刪筆記:{nid}")
    return schedule.stage(proposal, context)
