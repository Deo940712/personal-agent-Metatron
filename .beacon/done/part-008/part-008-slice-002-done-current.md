# part-008-slice-002 — 觸發邏輯 + job 接線 + 端到端(done 2026-07-19)

Snapshot of CURRENT at completion.

## Goal(達成)

觸發條件 + `--job scout` cron 接線 + 端到端(fetch → inbox → curate → recall
可見)。整條 Knowledge Scout 鏈路打通。

## Delivered

- `core/scout.py`:
  - `has_knowledge_gap(db, topic, vault)`:確定性知識缺口判定(registry 無此主題
    → 缺口;保守,寧漏勿亂)
  - `collect_triggers(db, vault, now_ts)`:①watchlist 到期(主要)②goal facet
    有缺口 **且** 有對應 active watchlist 來源(不憑空造 URL)→ SCOUT_MAX_PER_RUN 上限
  - `run(db, vault, fetcher, now_ts)`:收集觸發 → 逐個 fetch_and_land → 標
    watchlist touched;無觸發零抓;預設 RSS fetcher(測試注入 mock)
- `core/agent.py`:`job_scout` + `--job scout`(延遲 import;記 agent_runs)
- `tests/test_scout_run.py`:9 tests(無觸發不抓、watchlist 到期觸發+touched 後不重抓、
  知識缺口觸發+無來源不觸發+已覆蓋不觸發、上限、job 接線+CLI、端到端
  fetch→curate→recall 可見帶 external_untrusted)

## Verification

- Unit: `python -m pytest tests/test_scout_run.py -q` → 9 passed
- Regression: `python -m pytest tests/ -q` → **778 passed**(基線 769 + 9)
- Manual QA(端到端實跑):watchlist RAG → `--job scout` → inbox
  (external_untrusted)→ curate 評分 8.5 → recall registry 可見帶 url 溯源 →
  watchlist 標 touched。含注入的內文未觸發任何寫入。

## DESIGN Verification Targets 對照(全五條)

- [x] allowlist 外網域 → 拒絕抓取(slice-000/001)
- [x] 抓取內容帶 url/author/captured_at/content_hash + external_untrusted(slice-001)
- [x] 含注入字串的外部內容 → 不觸發任何寫入,只落 inbox 待評分(slice-001)
- [x] 經 curator 評分 + writer 才進 semantic/;低分只留 metadata(本 slice 端到端)
- [x] 自動研究只在觸發條件成立時啟動;無缺口 → 不抓(本 slice)

## Notes

- 知識缺口觸發保守:**只研究已有信任來源訂閱的主題**——不讓 goal facet 憑空
  觸發任意 URL 抓取(防 LLM/facet 造 URL,符合 §防注入「query 過 allowlist」)。
- scout 只落 inbox;curate/writer 入庫是既有鏈(復用 part-004),端到端測證通。
- watchlist_add 的 source_url allowlist 驗證在 due/run 時(觸發前),CLI 加時不擋
  ——允許先建訂閱、之後調 allowlist;due_watchlist fail-closed 排除非白名單。
