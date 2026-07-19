# part-012-slice-000 — router 子 agent + 意圖分類 + fallback(done 2026-07-19)

Snapshot of CURRENT at completion.

## Goal(達成)

`agents/router.md` 契約 + `core/router.py` 分類器。純分類層不接線——現有行為
零改變。

## Delivered

- `agents/router.md`:七 intent 意圖分類契約(cheap/單次/JSON enum;few-shot
  各 intent ≥1 例含「明天」「我存過哪些 RAG」「哈囉」;「寧可 unclear 不亂猜
  schedule_write」防浪費確認)
- `core/router.py`:
  - `Route` dataclass(intent/argument/date_range/guess)+ `FALLBACK` 單例
  - `classify(text, db, now_ts, _api)`:注入今天日期 → LLM → `_parse` 欄位級驗證
  - 驗證:intent ∈ enum、argument 是 str、date_range ISO + 起≤迄 + ±366 天界限
    (擋幻覺日期);schedule_query 無合法時間窗 → 降為 unclear(追問,不亂查)
  - LLMError / 壞 JSON / 非法輸出 → FALLBACK(**永不拋出**;呼叫端退現行路徑,
    降級不斷服務)
- `tests/test_router.py`:20 tests(七 intent 重放/unclear guess 過濾/enum 外
  fallback/非 dict/壞 argument/LLMError/壞 JSON/五類壞 date_range → unclear/
  契約存在)

## Verification

- Unit: `python -m pytest tests/test_router.py -q` → 20 passed
- Regression: `python -m pytest tests/ -q` → **872 passed**(基線 852 + 20)
- **真 LLM sanity(gpt-5.5)**:六句全對——「明天有什麼」→ schedule_query
  (2026-07-20~20)、「我存過哪些 RAG」→ knowledge、「最近有什麼建議」→ advice、
  「哈囉」→ smalltalk、「明天下午兩點開會…」→ schedule_write、亂碼 → unclear。

## 安全設計

- 誤分類落安全側:寫入意圖誤成查詢 = 少做事;查詢誤成寫入仍有 preview→confirm
- date_range 由 LLM 理解語言、程式驗證數值(幻覺日期擋在 ±366 天)
- fallback 不斷服務:router 掛掉行為 = 今天的水準,不會更糟
