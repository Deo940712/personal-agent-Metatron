# part-012 TODO

Design authority: `.beacon/parts/part-012/DESIGN.md`

Open question 定案（slice 設計時）：
- schedule_query 時間窗：**LLM 給 ISO date range、程式驗證後查 DB**（覆蓋
  「明天/下週三/月底」等自然說法；驗證擋幻覺日期）。
- smalltalk 個人化：slice-001 先模板 + 當日行程數；facets 個人化留後續調校。

## SLICE Map

### part-012-slice-000: router 子 agent + 意圖分類 + fallback

Status: done (2026-07-19; snapshot: `.beacon/done/part-012/part-012-slice-000-done-current.md`)
872 tests 綠(基線 852 + 20);真 LLM sanity 六句全對(含「明天」→ schedule_query)。

Candidate scope:
- [x] `agents/router.md`:七 intent 契約(few-shot 各 ≥1 例;寧可 unclear 不亂猜寫入)
- [x] `core/router.py`:Route + classify(enum/argument/date_range ±366 天驗證;
      query 無合法時間窗 → unclear 追問;LLMError/壞輸出 → FALLBACK 永不拋)
- [x] tests:七 intent 重放、五類非法 fallback、五類壞 date_range、契約存在(20 tests)

Files-scope: agents/router.md, core/router.py, tests/test_router.py,
.beacon/parts/part-012/**, .beacon/CURRENT.md

Forbidden scope:
- 接線 chat/application（slice-001）
- 改寫入紀律；多輪對話狀態

Verification target:
- Unit: `python -m pytest tests/test_router.py -q`
- Regression: `python -m pytest tests/ -q`（基線 852）

Done gate: 七 intent + fallback 測綠；現有行為零改變；全綠

### part-012-slice-001: 接線 chat/application + schedule_query + Discord 開 recall

Status: done (2026-07-19; snapshot: `.beacon/done/part-012/part-012-slice-001-done-current.md`)
886 tests 綠(基線 872 + 14);Discord 真機 QA 五句全通;DESIGN 七條 targets 全對應。
part-012 兩 slice 完成。附帶修 recall 空回應 bug(gpt-5.5 content=null → gemini fallback)。

Goal: 慢徑改走 router 分派；schedule_query 確定性讀取器；Discord 開 recall；
unclear 友善追問。快徑（today/done/todo/查）保留零 LLM。

Candidate scope:
- [x] `core/chat.py`：`_dispatch_routed` router.classify → 七 intent 分派
- [x] `core/tools/schedule.py`：`range_view(start, end, label)` 確定性時間窗查詢
- [x] Discord 開 recall：allow_recall 預設 True；INTERFACES.md §4.1 標已解除
- [x] `core/application.py`：慢徑 route='routed'；outcome 對齊
- [x] tests：14 wiring tests（明天/knowledge/advice/status/smalltalk/unclear/快徑零
      LLM/寫入確認/router fallback）+ 過時期望更新
- [x] 附帶：`core/llm.py` 空回應 fallback（真機 QA 發現 gpt-5.5 content=null）

Files-scope: core/chat.py, core/application.py, core/tools/schedule.py,
channels/discord_bot.py, INTERFACES.md, tests/test_chat.py,
tests/test_application.py, tests/test_router_wiring.py

Forbidden scope:
- 第二次 LLM 潤稿呼叫（模板組裝即可）
- 寫入繞過確認

Verification target:
- Unit: `python -m pytest tests/test_router_wiring.py tests/test_chat.py tests/test_application.py -q`
- Regression: 全綠
- Manual QA: Discord 真機五句（明天/知識/建議/哈囉/亂碼)+ 排程寫入流程不變

Done gate: DESIGN Verification Targets 七條全對應；真機 QA 通過;全綠
