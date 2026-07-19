# part-012-slice-001 — router 接線 + Discord recall + 空回應 fallback(done 2026-07-19)

Snapshot of CURRENT at completion.

## Goal(達成)

慢徑改走 router 分派;schedule_query 確定性讀取器;Discord 開 recall;unclear
友善追問。快徑保留零 LLM。寫入紀律不變。「感覺是固定程序」的體感問題解決。

## Delivered

- `core/chat.py`:快徑未命中 → `_dispatch_routed`(router.classify → 七 intent):
  schedule_query→`range_view`、knowledge→recall、advice→`_advices_digest`、
  status→proj+advices、smalltalk→自然語+今日行程數、unclear→帶猜測追問、
  fallback/schedule_write→現行 propose。allow_recall 預設改 True。
- `core/tools/schedule.py`:`range_view(start, end, label)` 確定性時間窗查詢
  (router 給已驗證 ISO range;本地時區含頭尾)——「明天有什麼」可答。
- `channels/discord_bot.py`:allow_recall=True(舊內容分級決策過時)。
- `core/application.py`:`_classify_route` 慢徑回 'routed';outcome 對齊。
- `INTERFACES.md` §4.1:內容分級「知識不經 Discord」標已解除。
- `core/llm.py`:**空回應視為可重試 + fallback 模型**(真機 QA:gpt-5.5 對 recall
  契約穩定回 content=null;重試改打 LLM_MODEL_FALLBACK=gemini-3-flash)。
- `config.py`:LLM_MODEL_FALLBACK。
- tests:test_router_wiring.py(14)+ test_chat/test_application 過時期望更新。

## Verification

- Unit: `python -m pytest tests/test_router_wiring.py tests/test_chat.py tests/test_application.py -q` → 全綠
- Regression: `python -m pytest tests/ -q` → **886 passed**(基線 872 + 14)
- **Discord 真機 QA(gpt-5.5 內網 proxy)**:
  - 「明天有什麼」→ 列明天行程(#2 跟阿明開會)✓
  - 「最近有什麼建議」→ 誠實「沒有待處理」✓
  - 「哈囉」→ 「嗨!今天有 2 件事排著…」✓
  - 「那個先用上次的方式弄一下」→ 友善追問帶猜測 ✓
  - 「我存過哪些 RAG」→ 修 fallback 後:空庫誠實 not_found;種一筆後 found +
    正確引用 [20270115-rag-…] ✓
  - 排程寫入流程不變(預覽+按鈕→✅ 落地)✓

## DESIGN Verification Targets 對照(七條全對應)

- [x] 「明天」→ 列明天行程(不再「這不是行程/待辦」)
- [x] 知識問答 Discord → recall 帶引用
- [x] 「最近有什麼建議」→ 列 advices
- [x] 「哈囉」→ 自然回應;不明 → 友善追問
- [x] 快徑不變:today/done N 零 LLM(mock 斷言)
- [x] router LLM 失敗 → fallback 排程解析,不中斷
- [x] 寫入仍 preview→confirm

## Notes

- recall 空回應 bug 是 proxy×模型怪癖(gpt-5.5 content=null),非程式錯——
  fallback 機制通用,任何主模型對特定契約失能都能繞開。
- 知識庫目前空(0 筆)——recall not_found 是正確行為;threads 同步/scout 抓過後有料。
