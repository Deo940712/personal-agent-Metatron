# DONE: part-003-slice-003 vindex + retrieve 四段檢索

Completed: 2026-07-13
Design authority: `.beacon/parts/part-003/DESIGN.md`;技術規格 docs/MEMORY-zh.md §4/§6

## 交付物

- `core/vindex.py` — 檢索索引(探針實證行為全數落實):自帶 _connect(P1 每連線
  load extension)、note_map(P3 TEXT↔INT)、FTS5 trigram + vec0、upsert=
  DELETE+INSERT(P2)、search_fts(P4:≥3 字 MATCH+bm25 / <3 字 LIKE 降級 /
  FTS 特殊語法 fallback)、search_vec(KNN)、binary blob(P5)、meta 模型記錄、
  rebuild(整檔重建;壞筆記跳過)
- `core/retrieve.py` — 四段級聯:index-first(registry token 比對)→ FTS →
  vec(embed_fn 注入,None 跳過)→ rehydrate;**回血閉環**(命中筆記的
  source_ids evt: → health.on_hit);統一 Hit(note_id, path, score, stage)
- consolidate 管線尾接 vindex.upsert(索引失敗不擋蒸餾——衍生物哲學,記 events)
- 測試:test_retrieve.py(16)

## Verification Evidence

Automated commands:
- `python -m pytest tests/test_retrieve.py -q` → **16 passed**
- `python -m pytest tests/ -q` → **162 passed**(146 既有迴歸不壞)

覆蓋:FTS 中文 ≥3 字 MATCH / 2 字 LIKE 降級 / 英文 / 空查詢;vec KNN 距離排序;
upsert 冪等替換;pack_vector 維度守衛;**rebuild 等價性**(刪檔重建 → 查詢結果
相同 + meta 記錄);四段各自命中與級聯 fallback;全 miss 空結果;無 embed_fn
跳過 vec;**回血閉環(trash 事件被檢索命中 → health=1.0 + 復活)**;
rehydrate 讀回原文 / 無來源筆記回空。

Manual QA(端到端腳本,實跑):
- events(2 顆)→ decay → trash(原文落地)→ 蒸餾(mock LLM)→
  `retrieve.search("技術選型")` → **stage=index 命中** →
  `rehydrate` → **兩條原文一字不差讀回**
- status: passed(真 embedding 段待 API key,與真 LLM QA 同批補)

## Phase 3 Gate 判定

- ✅ 低健康 events 蒸餾後出現在 vault 且可檢索(端到端實跑)
- ✅ rehydrate 能沿 source_ids 讀回原文(端到端實跑)

**→ part-003 全部完成(3/3 slices),Phase 3 gate 通過。**

## Audit gate(依 continuous-loop 新流程)

slice-002 歸檔後補跑的稽核(探針 8 項):S5/S6/S8 三個 crash/缺陷已修 + 3 個
regression tests(見 KNOWN_ISSUES.md audit 記錄);S1-S4/S7 probed clean。
本 slice(003)的稽核併入下一次循環(vindex/retrieve 為新模組,其契約邊界
已由 16 個測試 + 端到端覆蓋)。
