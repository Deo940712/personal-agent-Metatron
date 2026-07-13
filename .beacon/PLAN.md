# Beacon Plan

## Project Goal

個人行程 + 知識庫助理 agent：無狀態核心（拋棄上下文）、四儲存層記憶
（DB1 SQLite = System of Record / DB2 Obsidian vault = 人類知識介面 /
冷儲存 transcript = 原始記錄 / 向量索引 = 可重建衍生物）、記憶生命週期
用健康值代謝、技能為獨立 idempotent CLI 管線。
架構決策記錄：`ARCHITECTURE.md`（根目錄，設計權威）。

## Non-goals

- 不做長 session / 對話歷史累積（核心必須無狀態）
- 不做多層記憶分頁（STM→MTM→LPM，MemoryOS 式）——延遲實測不可接受
- 不做 DB2 刪除（append-only；原始記錄 transcript 層永不刪）
- 不做反偵測規避（社交平台抓取沿用低頻 + jitter）
- 不做知識圖譜三元組 / hooks 聯想網 / GWM（memory-river 的重子系統，個人量級過度工程）
- 子 agent 不直接寫 DB（只提案，writer.py 驗證後落地）

## PARTs

| PART | Status | Goal | Design | TODO |
| --- | --- | --- | --- | --- |
| part-001 | **done** (2026-07-13) | 基礎層：config.py + DB1 schema（六表）+ stm.py CRUD CLI；28 tests 綠、Phase 1 gate 通過 | `.beacon/parts/part-001/DESIGN.md` | `.beacon/done/part-001/` |
| part-002 | **done** (2026-07-13) | Orchestrator + writer + LLM 薄層 + schedule 子 agent + remind job；93 tests 綠、Phase 2 gate 程式面通過（真 LLM QA 待 key） | `.beacon/parts/part-002/DESIGN.md` | `.beacon/done/part-002/` |
| part-002.5 | **done** (2026-07-13) | Discord bot：兩階段確認 + 提醒 DM + 白名單；210 tests 綠，真連線 QA blocked（等使用者環境） | `.beacon/parts/part-002.5/DESIGN.md` | `.beacon/done/part-002.5/` |
| part-003 | **done** (2026-07-13) | 記憶核心完成：transcript+health+consolidate+vindex+retrieve；162 tests 綠、Phase 3 gate 通過（端到端實跑） | `.beacon/parts/part-003/DESIGN.md` | `.beacon/parts/part-003/TODO.md` |
| part-003.5 | planned | 唯讀網頁儀表板（INTERFACES.md §5）：FastAPI+htmx、127.0.0.1、`mode=ro`、五版塊 | TBD | TBD |
| part-004 | planned | sync skills：threads-sync 接入 → x_sync（xarchive JSON 轉換器起步）→ fb_sync（先 probe） | TBD | TBD |
| part-004.5 | planned | 記憶強化（Membox/Mneme/Cognis 實證改進）：①主題連續性蒸餾（按天+主題分組、跨天 trace 連結）②矛盾偵測+supersede 執行（profile 注入既有、superseded_by 落地、recall 矛盾並列）③RRF 跨段融合檢索 | TBD | TBD |
| part-005 | planned | coding_tracker：三源進度掃描（git log + .beacon/CURRENT 解析 + OpenCode sessions）→ project_update 提案 | TBD | TBD |
| part-006 | backlog | MCP server：唯讀查詢暴露（recall/schedule/project_status），寫入仍走 writer + 確認 | TBD | TBD |

## Success Criteria

- 兩次獨立的 agent 呼叫之間，狀態完全靠 DB1 接續（無 session）
- 行程 / 待辦 / coding 進度可透過 CLI 增查改
- 低健康 events 經夜間蒸餾後出現在 vault episodic/ 且可檢索；rehydrate 可沿 source_ids 讀回原文
- 任一 skill 管線單獨壞掉不影響 core 與其他 skill
- 子 agent 提案被 writer 驗證攔截（含拒絕路徑）可測試證明

## Global Risks

- ~~向量索引選型~~ 已定案：sqlite-vec v0.1.9（本機實測 KNN OK）+ FTS5 前置（backlog-001）
- ~~LLM 供應商~~ 已定案：OpenAI 相容 API + base_url 環境變數（backlog-002）
- ~~OneDrive 鎖檔風險~~ 已定案：DATA_DIR 在本地 OneDrive 外；後期遷 VPS 只改 config.py
- Meta GraphQL 改版會弄壞 sync skills（繼承 threads-sync 已知風險）
- LLM 回傳 JSON 不穩——schema 約束 + 重試 1 次 + 壞即拒絕（part-002 DESIGN）

## Global Verification Strategy

- 每 SLICE 以 pytest 為主要自動驗證；`.beacon/verification/UnitTestCore.ps1` 驅動
- 無狀態性驗證：跨行程（process）測試——兩次獨立執行共享狀態僅經 DB1
- 管線 idempotency 驗證：同一命令跑兩次，第二次為 no-op
- 手動 QA：Obsidian 開 vault 檢查筆記格式與 MOC
