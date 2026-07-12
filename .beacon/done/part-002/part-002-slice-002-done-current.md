# DONE: part-002-slice-002 llm.py + subagents.py + schedule 契約

Completed: 2026-07-13(自動驗證全綠;手動真 LLM QA blocked,見下)
Design authority: `.beacon/parts/part-002/DESIGN.md`

## 交付物

- `core/llm.py` — OpenAI 相容薄層:
  - `complete()`:base_url/key 環境變數、失敗重試 1、呼叫記錄進 events
    (actor=llm,只記 model/purpose/長度,不含全文)
  - `complete_json()`:壞 JSON 帶錯誤提示重試 1,仍壞 → LLMError(不猜)
  - `_parse_json()`:容忍 ```json 圍欄與前後雜訊
  - response_format 不支援時降級(schema 已在 prompt 內)
  - openai 套件延遲 import:測試全 mock,不裝也能跑
- `agents/schedule.md` — 首個子 agent 契約:系統 prompt(規則含相對時間換算、
  remind 預設 30 分、rrule 子集、evidence=原句)+ 4 個 few-shot(含 rrule、
  task、非行程 error 例)
- `core/subagents.py` — 執行器:load_contract(讀 `## System Prompt` 後全文)+
  run_schedule(NOW/時區注入、active_items 注入、evidence 防禦性回填)
- `tests/test_subagents.py` — 13 個測試

## Verification Evidence

Automated commands:
- command: `python -m pytest tests/test_subagents.py -q` → **13 passed**
- command: `python -m pytest tests/ -q` → **62 passed**(49 既有迴歸不壞)

覆蓋:complete 記 events/重試後拋錯、complete_json 圍欄容忍/壞→好重試/
兩次壞拋錯、契約載入、schedule 上下文組裝(NOW+現有項目+原句)、evidence 回填、
error passthrough、**端到端:mock LLM → writer → DB1 落地**、
**兩層防禦獨立:LLM 產非法 action 被 writer 攔**。

Manual QA:
- item: 真 LLM 一次解析,檢查提案 JSON
- status: **blocked** — 本機未設 MY_AGENT_LLM_API_KEY 且未安裝 openai 套件
- 補做程序(併入 slice-003 手動 QA 一起做):
  1. `pip install openai`(或裝 uv 後 `uv add openai && uv sync`)
  2. 設 `MY_AGENT_LLM_API_KEY`(+ 選配 `MY_AGENT_LLM_BASE_URL`)
  3. slice-003 交付的 `python -m core.agent "明天下午兩點開會"` 即同時覆蓋本項

Incidents: none(blocked 屬環境前置,非設計/實作失敗;誠實記錄不虛報)

## 設計筆記

- pyproject 尚未加 openai 依賴——slice-003 實跑前補(目前測試不需要)
