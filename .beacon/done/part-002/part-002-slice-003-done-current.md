# DONE: part-002-slice-003 agent.py orchestrator + remind job(+ KNOWN_ISSUES 修復)

Completed: 2026-07-13(自動驗證全綠;真 LLM 手動 QA 待 API key,見下)
Design authority: `.beacon/parts/part-002/DESIGN.md`

## 交付物

### KNOWN_ISSUES 修復(先於新功能)

- B1 update 空 fields → validator 拒絕(曾 SQL crash)
- B2 NOT NULL 欄位 None → 拒絕;nullable 欄位 None=清除(合法)
- B3 界外 epoch → 雙層:validator 範圍檢查(2000‥2100)+ fmt_when 防禦回 `?invalid`
- B4 bool 偽裝 int → 顯式排除
- B5 CLI 壞時間 → 友善訊息 + exit 2
- B8 4xx 不重試(僅 timeout/connection/5xx/429 重試)
- B11 拒絕記錄不再污染 events.target
- B6 緩解:`_enforce_target_whitelist` — done/cancel 只接受本次 active 清單 id
- `tests/test_known_issues.py` — 18 個 regression tests(重現式逐條轉)

### 新功能

- `core/agent.py`:
  - `invoke()`:§6.1 全流程 — agent_runs 記錄 → DB1 組上下文(active 行程+待辦
    注入)→ schedule 子 agent → B6 白名單 → writer → 回覆;
    **頂層防線:任何例外都 finish run(不卡 running)**
  - `job_remind()`:§6.6 確定性提醒 — partial index 查詢、通知、
    單次標記 reminded_at / 重複行程 rrule 前推 + 重新武裝(reminded_at=NULL)
  - `rrule_next()`:確定性前推(DAILY / WEEKLY;BYDAY 子集)
  - CLI:`python -m core.agent "<text>"`(stdin y/N 確認;--yes 跳過)、`--job remind`
- `pyproject.toml` 加 openai>=1.40;本機已裝(openai 2.45.0)
- `tests/test_agent.py` — 13 個測試

## Verification Evidence

Automated commands:
- command: `python -m pytest tests/ -q` → **93 passed**
  (62 既有 + 18 known-issues regression + 13 agent)

覆蓋:invoke 全流程(落地/拒絕/不可解析/LLM 失敗仍 finish run)、
**無狀態 gate:兩次獨立呼叫,第二次的 LLM 上下文含第一次寫入(僅經 DB1)**、
B6 白名單(越界拒絕+記 events/界內放行)、remind(單次標記+idempotent、
重複前推+重新武裝、無到期 no-op)、rrule_next 三型。

Manual QA:
- item: 真 LLM 排程 + remind 觸發
- status: **blocked** — openai 套件已裝,但 MY_AGENT_LLM_API_KEY 未設(需使用者提供)
- 補做:設 key 後跑 `python -m core.agent "明天下午兩點開會 提前30分提醒"` → y →
  `python -m core.stm schedule list`;再把 remind_at 改過去 → `--job remind`

Incidents: none

## Phase 2 Gate 判定

- ✅ 兩次獨立呼叫之間狀態完全靠 DB1 接續(test_stateless_two_invocations)
- ✅ 子 agent 提案被 writer 驗證攔截(21+18 個測試)
- ⏳ 真 LLM 手動 QA 待 key(不影響 gate 的程式面判定)

**→ part-002 程式面完成;真 LLM QA 為使用者環境動作。**
