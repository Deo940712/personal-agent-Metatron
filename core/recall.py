"""recall 執行器(part-004;唯一的代理型子 agent,ARCHITECTURE §3.2)。

工具迴圈:LLM 每輪回一個 JSON 工具呼叫 → 執行(全唯讀)→ 結果回饋 → 直到
answer 或步數上限。工具白名單寫死在本模組——LLM 要求白名單外的工具一律拒絕。

引用硬規則的程式面保障:answer 的 citations 逐一驗證存在於 registry;
含不存在 id → 整個回答降級為「引用驗證失敗」(不信任 LLM 自律)。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import config
from core import llm, ltm, retrieve, subagents

MAX_STEPS = 6
_ANSWER_MAX = 500


@dataclass
class RecallResult:
    text: str
    citations: list[str] = field(default_factory=list)
    steps: int = 0
    ok: bool = True          # False = 執行異常(LLM 壞/步數爆/引用驗證失敗)
    outcome: str = "not_found"  # found(必附有效引用)/ not_found(才可空引用)
    # 裂縫3(part-006-slice-001):found 必須 ≥1 有效 citation;LLM 回「有主張但
    # citations=[]」一律降級 not_found——不信 LLM 自律,程式面保障『無來源不得斷言』。


def _tool_search(args: dict, vault: Path, idx_db: Path, db: Path | None) -> str:
    query = str(args.get("query", ""))[:200]
    hits = retrieve.search(vault, idx_db, query, db=db)     # 命中即回血(§6.4)
    return json.dumps(
        [{"id": h.note_id, "path": h.path, "stage": h.stage} for h in hits[:5]],
        ensure_ascii=False)


def _tool_read_note(args: dict, vault: Path, *_ignored) -> str:
    path = str(args.get("path", ""))
    if path.startswith(("/", "\\")) or ".." in path or ":" in path:
        return json.dumps({"error": "illegal path"})
    note = ltm.read_note(vault, path)
    if note is None:
        return json.dumps({"error": f"note not found: {path}"})
    result = {"frontmatter": note["frontmatter"], "body": note["body"][:3000]}
    # part-004.5(Mneme):被取代的筆記顯式標明,LLM 依契約優先讀新版
    superseded_by = note["frontmatter"].get("superseded_by")
    if superseded_by:
        result["_superseded_by_note"] = (
            f"此筆記已被 {superseded_by} 取代;請優先讀取新版再回答")
    # part-010:情境演練是非權威模擬,引用時必須明確標記(不得當事實/預測)
    fm = note["frontmatter"]
    if (fm.get("source") == "scenario_rehearsal"
            or str(fm.get("non_authoritative", "")).lower() == "true"):
        result["_non_authoritative_note"] = (
            "此筆記是**模擬演練**產物(合成 persona),非事實、非預測;"
            "引用時必須明確標示「這是模擬演練,非事實/非預測」")
    return json.dumps(result, ensure_ascii=False)


def _tool_rehydrate(args: dict, vault: Path, idx_db: Path, db: Path | None,
                    transcript_dir: Path | None = None) -> str:
    path = str(args.get("path", ""))
    entries = retrieve.rehydrate(vault, path, transcript_dir=transcript_dir)
    return json.dumps([e.get("payload", {}) for e in entries[:10]], ensure_ascii=False)


def _verify_citations(citations: list, vault: Path) -> list[str]:
    """回傳不存在於 registry 的引用(空 list = 全部驗證通過)。"""
    known = {e["id"] for e in ltm.registry_entries(vault)}
    return [str(c) for c in citations if str(c) not in known]


def ask(query: str, *, vault: Path | None = None, idx_db: Path | None = None,
        db: Path | None = None, transcript_dir: Path | None = None,
        _api=None) -> RecallResult:
    """問答主迴圈。永不拋例外——一切異常化為 ok=False 的誠實結果。"""
    vault = vault or config.VAULT_PATH
    idx_db = idx_db or config.INDEX_DB
    system = subagents.load_contract("recall")

    transcript_log = [query]
    search_count = 0

    for step in range(1, MAX_STEPS + 1):
        try:
            move = llm.complete_json(system, "\n".join(transcript_log),
                                     db=db, purpose="recall", _api=_api)
        except llm.LLMError as e:
            return RecallResult(f"檢索失敗:{e}", ok=False, steps=step)

        tool = move.get("tool") if isinstance(move, dict) else None
        if tool == "answer":
            citations = move.get("citations", [])
            # audit R2:citations 非 list = 格式壞 → 拒答(不靜默轉空放行)
            if not isinstance(citations, list):
                return RecallResult(
                    "回答格式錯誤(citations 非陣列);原回答已丟棄。",
                    ok=False, steps=step)
            text = str(move.get("text", ""))[:_ANSWER_MAX]
            # 裂縫3:found 必須附有效引用。空引用 = not_found(不得斷言無來源)。
            if not citations:
                return RecallResult(text, citations=[], steps=step,
                                    outcome="not_found")
            # 引用硬規則:引用必須真實存在;含假引用 → 整答丟棄(不信 LLM 自律)
            bogus = _verify_citations(citations, vault)
            if bogus:
                return RecallResult(
                    f"引用驗證失敗(不存在的筆記 id:{bogus[:3]});原回答已丟棄。",
                    ok=False, steps=step)
            return RecallResult(text, citations=[str(c) for c in citations],
                                steps=step, outcome="found")

        if tool == "search":
            if search_count >= 3:
                transcript_log.append('[工具結果] {"error": "search 次數已達上限,請 answer"}')
                continue
            search_count += 1
            result = _tool_search(move, vault, idx_db, db)
        elif tool == "read_note":
            result = _tool_read_note(move, vault)
        elif tool == "rehydrate":
            result = _tool_rehydrate(move, vault, idx_db, db, transcript_dir)
        else:
            result = json.dumps({"error": f"unknown tool: {tool!r} (whitelist: "
                                          f"search/read_note/rehydrate/answer)"})
        transcript_log.append(f"ASSISTANT: {json.dumps(move, ensure_ascii=False)}")
        transcript_log.append(f"[工具結果] {result}")

    return RecallResult("檢索步數達上限仍無答案;請換個問法。", ok=False, steps=MAX_STEPS)
