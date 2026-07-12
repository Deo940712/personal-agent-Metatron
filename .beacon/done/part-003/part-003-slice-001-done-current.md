# DONE: part-003-slice-001 transcript 冷儲存 + health 代謝

Completed: 2026-07-13
Design authority: `.beacon/parts/part-003/DESIGN.md`;技術規格 docs/MEMORY-zh.md §2/§3

## 交付物

- `core/transcript.py` — append(先 JSONL flush 再 .idx)、read_by_ids(O(1) seek,
  缺 id 回報不拋錯,保持輸入順序)、read_by_time(跨月)、read_by_keyword(新→舊 +
  limit)、rebuild_idx(自癒;壞 JSONL 行跳過)、按月輪替;讀取不產生副作用
- `core/health.py` — decay(**絕對閒置時間重算 → 冪等**;immune 跳過;floor 0)、
  to_trash(**先落地 transcript 成功才轉狀態**——寧可晚進 trash,不可有 trash 無
  原文;source_ids 設回水指標)、on_hit(回血+復活;archived 不復活)、
  due_for_distill(保留期)、mark_archived(只准 trash→archived)
- config:HEALTH_DECAY_PER_DAY / TRASH_RETENTION_DAYS / DISTILL_MIN_CONFIDENCE /
  EMBED_MODEL / EMBED_DIM / EMBED_BASE_URL_ENV
- 測試:test_transcript.py(10)+ test_health.py(13)

## Verification Evidence

Automated commands:
- `python -m pytest tests/test_transcript.py tests/test_health.py -q` → **23 passed**
- `python -m pytest tests/ -q` → **116 passed**(93 既有迴歸不壞)

覆蓋:三模式 roundtrip、月輪替、.idx 一致性、**rebuild_idx 自癒(毀 idx →
讀不到 → 重建 → 讀回)**、壞行跳過、不存在目錄 boundary(讀取零副作用)、
decay 數學(線性/冪等/floor/immune/last_accessed 基準)、**to_trash 落地驗證
(transcript 有原文 + source_ids 指標)**、復活/不復活 archived、保留期邊界、
**整條生命週期(alive→trash→archived,「遺忘≠刪除」斷言)**。

Manual QA: 無(依 TODO 規劃)

Incidents: none

## 設計筆記(移交 slice-002)

- to_trash 的落地失敗策略:跳過該筆維持 alive,下輪重試(測試未覆蓋 OSError
  注入,行為由 code review 保證——slice-002 蒸餾管線整合測試時可補)
- events 表在 decay 用 SQL 端計算(單 UPDATE 全表),個人量級無效能問題
