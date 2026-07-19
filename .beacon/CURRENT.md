# CURRENT

Status: active
Part: part-012（對話式 orchestrator）
Slice: part-012-slice-001 — 接線 chat/application + schedule_query + Discord 開 recall

## Context

part-012-slice-000 已完成歸檔（`.beacon/done/part-012/`）：router 分類器
（872 tests；真 LLM 六句全對，「明天」正確分成 schedule_query + 時間窗）。

## Goal

慢徑改走 router 分派；schedule_query 確定性讀取器；Discord 開 recall；
unclear 友善追問。快徑（today/done/todo/查）保留零 LLM。寫入紀律不變。

Design authority: `.beacon/parts/part-012/DESIGN.md`
Slice map: `.beacon/parts/part-012/TODO.md`

## Allowed scope

- [ ] `core/chat.py`：未命中快徑 → router.classify → 七 intent 分派
      （schedule_write→現 propose / schedule_query→range 讀取器 / knowledge→recall /
      advice→advices / status→proj+advices / smalltalk→模板+今日行程數 /
      unclear→帶猜測追問 / fallback→現行 propose）
- [ ] `core/tools/schedule.py`：`range_view(start, end)` 確定性查詢
- [ ] Discord 開 recall：allow_recall 預設 True；INTERFACES.md 內容分級標過時
- [ ] `core/application.py`：route/outcome 對齊（agent_runs 記 intent）
- [ ] tests：「明天」回行程、knowledge 進 recall、advice/status/smalltalk/unclear、
      快徑零 LLM 斷言、寫入仍 preview→confirm、fallback 不中斷

Files-scope: core/chat.py, core/application.py, core/tools/schedule.py,
channels/discord_bot.py, INTERFACES.md, tests/test_chat.py,
tests/test_application.py, tests/test_router_wiring.py,
.beacon/parts/part-012/**, .beacon/CURRENT.md

## Forbidden scope

- 第二次 LLM 潤稿呼叫；寫入繞過確認；多輪對話狀態

## Verification target

- Unit: `python -m pytest tests/test_router_wiring.py tests/test_chat.py tests/test_application.py -q`
- Regression: `python -m pytest tests/ -q`（基線 872）
- Manual QA: Discord 真機五句 + 排程寫入流程不變

## Done gate

DESIGN Verification Targets 七條全對應；真機 QA 通過；全綠。
