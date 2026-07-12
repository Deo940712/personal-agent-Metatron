"""LLM 薄層(OpenAI 相容 API;backlog-002/006 定案)。

自寫薄層,無框架:一個 complete() 函式。base_url/key 走環境變數
(config.LLM_BASE_URL_ENV / LLM_API_KEY_ENV),可切 OpenAI/OpenRouter/Groq/Ollama。

設計(part-002 DESIGN):
- 重試 1 次(網路/5xx 類錯誤)
- json_mode:優先用 response_format={"type":"json_object"};端點不支援時
  降級為 prompt 已內嵌 schema、直接 parse 回應
- 呼叫記錄寫 events(actor=llm,只記 model+用途,不含全文)
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Callable

import config
from core import stm

# 延遲 import openai:測試全程 mock,不裝 openai 也能跑測試
_client = None


def _get_client():
    global _client
    if _client is None:
        from openai import OpenAI
        _client = OpenAI(
            api_key=os.environ.get(config.LLM_API_KEY_ENV) or "missing-key",
            base_url=os.environ.get(config.LLM_BASE_URL_ENV) or None,
        )
    return _client


class LLMError(RuntimeError):
    """呼叫失敗(已含 1 次重試)或回應無法解析。"""


def _is_retryable(e: Exception) -> bool:
    """B8:只重試暫時性錯誤(網路/timeout/5xx/429);4xx 設定錯誤直接拋。"""
    status = getattr(e, "status_code", None)
    if status is not None:
        return status == 429 or status >= 500
    return isinstance(e, (ConnectionError, TimeoutError, OSError))


def _call_api(system: str, user: str, model: str, json_mode: bool) -> str:
    client = _get_client()
    kwargs = {}
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": user}],
            **kwargs)
    except Exception as e:
        # 端點不支援 response_format → 降級重打一次(schema 已在 prompt 內)
        if json_mode and "response_format" in str(e):
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "system", "content": system},
                          {"role": "user", "content": user}])
        else:
            raise
    return resp.choices[0].message.content or ""


def complete(system: str, user: str, *, model: str | None = None,
             json_mode: bool = False, db: Path | None = None,
             purpose: str = "", _api=None) -> str:
    """單次補全。_api 供測試注入 fake;失敗重試 1 次後拋 LLMError。"""
    model = model or config.LLM_MODEL_CHEAP
    api: Callable = _api or _call_api

    last_err: Exception | None = None
    for attempt in range(2):                       # 首打 + 重試 1(僅暫時性錯誤)
        try:
            text = api(system, user, model, json_mode)
            stm.event_append(db, "llm", "completed",
                             f"model={model} purpose={purpose or '-'} chars={len(text)}")
            return text
        except Exception as e:                     # noqa: BLE001 — 邊界層集中攔
            last_err = e
            if attempt == 0 and not _is_retryable(e):
                break                              # B8:4xx 類不重試,直接失敗
    stm.event_append(db, "llm", "failed",
                     f"model={model} purpose={purpose or '-'} err={type(last_err).__name__}")
    raise LLMError(f"LLM call failed: {last_err}") from last_err


def complete_json(system: str, user: str, **kw) -> dict:
    """complete + JSON 解析。壞 JSON 再重試 1 次(帶錯誤提示),仍壞 → LLMError。"""
    text = complete(system, user, json_mode=True, **kw)
    try:
        return _parse_json(text)
    except ValueError:
        retry_user = (f"{user}\n\n前次回應不是合法 JSON,請只輸出一個 JSON object,"
                      f"不要任何其他文字。前次回應開頭:{text[:120]!r}")
        text = complete(system, retry_user, json_mode=True, **kw)
        try:
            return _parse_json(text)
        except ValueError as e:
            raise LLMError(f"invalid JSON after retry: {text[:200]!r}") from e


def _parse_json(text: str) -> dict:
    """容忍 ```json 圍欄與前後雜訊:取第一個 { 到最後一個 }。"""
    s = text.strip()
    if s.startswith("```"):
        s = s.split("```")[1]
        s = s.removeprefix("json").strip()
    start, end = s.find("{"), s.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("no JSON object found")
    obj = json.loads(s[start:end + 1])
    if not isinstance(obj, dict):
        raise ValueError("top-level JSON is not an object")
    return obj
