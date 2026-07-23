# Beacon Plan

## Project Goal

個人行程 + 知識庫助理 agent：無狀態核心（拋棄上下文）、四儲存層記憶
（DB1 SQLite = System of Record / DB2 Obsidian vault = 人類知識介面 /
冷儲存 transcript = 原始記錄 / 向量索引 = 可重建衍生物）、記憶生命週期
用健康值代謝、技能為獨立 idempotent CLI 管線。
架構決策記錄：`ARCHITECTURE.md`（根目錄，設計權威）。

## Non-goals

- 不做長 session / 對話歷史累積（核心必須無狀態）
- 多層記憶尚未定案：保留現有儲存分工與級聯檢索；Task Capsule、task-scoped
  warm set、LLM 自主 paging 必須分開以真實任務評估。不得把候選方案寫成已採用。
- 不做 DB2 刪除（append-only；原始記錄 transcript 層永不刪）
- 不做反偵測規避（社交平台抓取沿用低頻 + jitter）
- 不做知識圖譜三元組 / hooks 聯想網 / GWM（memory-river 的重子系統，個人量級過度工程）
- LLM 子 agent 不持有 raw SQL／DB connection／任意檔案寫入權；可依靜態
  allowlist 呼叫 scoped read/propose/auto-apply capability。共享狀態的 commit
  仍由 deterministic writer boundary 驗證，不要求 orchestrator 逐筆代轉。
- **不接 OpenHuman 程式碼**（GPL-3.0 + 自帶 SQLite/vault/orchestrator/workflow/channels，與本專案核心全面重複；只 clean-room 借「learning facets / subconscious world-diff / advice-first」概念，用 Python 自寫，見 backlog-027）
- **不做常駐 agent graph / 三層 subagent / 背景無限自我思考**（OpenHuman 式持久 orchestration 與無狀態核心衝突）——「活」= 定期醒來看 world-diff、產可過期建議、真實行動仍走確認，不是自主改狀態
- **模擬層不得改真實狀態**：crowd-scenario / MiroFish 只讀 bucket 化 seed、只回 advisory 報告；永不讀寫 DB1/vault/transcript 原文，也不得繞過 writer

## PARTs

| PART | Status | Goal | Design | TODO |
| --- | --- | --- | --- | --- |
| part-001 | **done** (2026-07-13) | 基礎層：config.py + DB1 schema（六表）+ stm.py CRUD CLI；28 tests 綠、Phase 1 gate 通過 | `.beacon/parts/part-001/DESIGN.md` | `.beacon/done/part-001/` |
| part-002 | **done** (2026-07-13) | Orchestrator + writer + LLM 薄層 + schedule 子 agent + remind job；93 tests 綠、Phase 2 gate 程式面通過（真 LLM QA 待 key） | `.beacon/parts/part-002/DESIGN.md` | `.beacon/done/part-002/` |
| part-002.5 | **done** (2026-07-13) | Discord bot：兩階段確認 + 提醒 DM + 白名單；210 tests 綠，真連線 QA blocked（等使用者環境） | `.beacon/parts/part-002.5/DESIGN.md` | `.beacon/done/part-002.5/` |
| part-003 | **done** (2026-07-13) | 記憶核心完成：transcript+health+consolidate+vindex+retrieve；162 tests 綠、Phase 3 gate 通過（端到端實跑） | `.beacon/parts/part-003/DESIGN.md` | `.beacon/parts/part-003/TODO.md` |
| part-003.1 | **done** (2026-07-15) | 記憶架構文件契約：雙語規格、目前實作與候選多層方案分界、A/B/C/D 評估框架、agent capability／writer 權限邊界；無 runtime/schema 變更；326 tests 綠、文件驗證器 + 負向探針通過 | `.beacon/parts/part-003.1/DESIGN.md` | `.beacon/done/part-003.1/` |
| part-003.2 | **done** (2026-07-16) | ECC 技術評估 + 隔離 Task Capsule A/B 實驗：可丟棄 SQLite 原型、七 workload 公平比較 A vs B、預註冊門檻、deterministic scoring；**判定 retain_a**（0/7 qualify，B p95 超預算，成本 proxy 無改善）；未採用 B/C/D、未改正式 schema/runtime；531 tests 綠、6 對抗探針通過 | `.beacon/parts/part-003.2/DESIGN.md` | `.beacon/done/part-003.2/` |
| part-003.5 | **done** (2026-07-16) | 唯讀儀表板：**stdlib http.server**（零依賴，非 FastAPI）單頁、127.0.0.1:7777、三層唯讀保證（GET-only/mode=ro/無寫入呼叫）、七版塊含 directives；608 tests 綠、端到端 HTTP smoke + 5 對抗探針通過 | `.beacon/parts/part-003.5/DESIGN.md` | `.beacon/done/part-003.5/` |
| part-004 | **done** (2026-07-13) | sync skills + curator + recall；254 tests、Phase 4 gate（mock 端到端）通過；真同步/LLM QA blocked | `.beacon/parts/part-004/DESIGN.md` | `.beacon/done/part-004/` |
| part-004.5 | **done** (2026-07-13) | 記憶強化：Membox 主題trace + Mneme supersede + Cognis RRF；280 tests、Phase 4.5 gate 通過 | `.beacon/parts/part-004.5/DESIGN.md` | `.beacon/done/part-004.5/` |
| part-005 | **done** (2026-07-13) | coding_tracker 三源掃描；314 tests、Phase 5 gate（真三源端到端）通過 | `.beacon/parts/part-005/DESIGN.md` | `.beacon/done/part-005/` |
| part-006 | code done, VPS QA blocked | MCP server：能力工具基座 + 互動硬化 + 本機 stdio MCP + 遠程 HTTP JSON-RPC（bind guard fail-closed，只允 loopback/RFC1918/Tailscale）全部**程式面完成**；630 tests 綠、端到端 smoke + 對抗探針通過；讀寫皆走 capability policy + writer/確認邊界。剩 slice-003 的 VPS + Tailscale 真機手動 QA（backlog-008） | `.beacon/parts/part-006/DESIGN.md` | `.beacon/parts/part-006/TODO.md` |
| part-007 | **done** (2026-07-19) | **Personal Model**（個人模型）：DB1 `profile_facets` 第九表——證據驅動 stability facets、生命週期（provisional→stable→pinned→superseded/forgotten）、stability detector 純函數、profile_facet 提案走 writer（evidence 溯源 transcript、Mneme supersede）、routine 抽取器、consolidate 掛鉤、vault/agent/profile 投影 + recall 可見；688 tests 綠、三 slice 端到端 QA 通過 | `.beacon/parts/part-007/DESIGN.md` | `.beacon/done/part-007/` |
| part-008 | **done** (2026-07-19) | **Knowledge Scout**（網路知識取得）：DB1 `watchlist` 第十一表 + allowlist（fail-closed，防子字串攻擊）+ web fetch skill（RSS/Atom，stdlib）+ `external_untrusted` 污染標籤（web = 資料非指令）+ curator 注入隔離框 + 抓取零 writer 寫入 + `--job scout` 觸發（watchlist 到期 / goal 知識缺口且有信任來源）；保存 URL/author/captured_at/content_hash → inbox → curator → writer → vault；778 tests 綠、三 slice 端到端 QA 通過（真網路抓取 QA 待來源） | `.beacon/parts/part-008/DESIGN.md` | `.beacon/done/part-008/` |
| part-009 | **done** (2026-07-19) | **Proactive Advisor / Subconscious**（主動建議）：DB1 `advices` 第十表 + baseline checkpoint + 確定性 world-diff（quiet-tick 無變化零 LLM）+ reflect 產可過期 advice（四重防疲勞：配額/去重/過期/優先級）+ Discord 推播 + action→confirm（走 writer）+ 校準回饋成 part-007 facet（越用越準）；`--job advise` cron 接線；永不靜默改狀態；735 tests 綠、三 slice 端到端 QA 通過（真 Discord 連線待 token） | `.beacon/parts/part-009/DESIGN.md` | `.beacon/done/part-009/` |
| part-010 | designed | **crowd-scenario integration**（情境演練）：vendored 釘版（第二個 vendored 黑箱，同 threads-sync）+ subprocess CLI 呼叫；Metatron 產去識別化 bucket seed → 子行程演練 → advisory 報告存 vault，標 non-authoritative；新增個人 domain packs（personal_schedule / habit_change / project_portfolio） | `.beacon/parts/part-010/DESIGN.md` | 待 slice |
| part-011 | **done** (2026-07-19) | **收尾接線**（closing-loop，非 backlog MiroFish）：作息 completed 事件 → routine facet → advisor 偏離（死程式碼 extract_routine 復活）+ advisor 校準降頻 + world-diff new_knowledge 訊號 + golden queries 回歸（backlog-007）+ 文件全同步；852 tests 綠、三 slice QA 通過 | `.beacon/parts/part-011/DESIGN.md` | `.beacon/done/part-011/` |
| part-012 | **done** (2026-07-19) | **對話式 orchestrator**（backlog-033）：LLM-first 意圖路由（router 子 agent，七 intent；快徑保留零 LLM）；Discord 聽懂「明天有什麼/我存過哪些 X/最近怎樣/哈囉」+ 開放 recall + unclear 友善追問；寫入鐵律不變；附帶修 recall 空回應 fallback；886 tests、真機 QA 五句全通 | `.beacon/parts/part-012/DESIGN.md` | `.beacon/done/part-012/` |
| part-013 | **done** (2026-07-19) | **對話層補兩意圖**：router 加 directive（Discord 留開發指令入佇列）+ knowledge_list（知識庫瀏覽總覽,tag 分布走索引零檔案 I/O,808 篇 0.15s）；移除過廣「知識」快徑前綴；895 tests、真機 QA 通過 | `.beacon/parts/part-013/DESIGN.md` | `.beacon/done/part-013/` |
| part-014 | **done** (2026-07-19) | **MCP dev_plan + 儀表板常駐**：dev_plan 工具（第 11 MCP 工具，讀 OpenCode session 的 plan/todo 進度）+ 儀表板設 ONSTART 常駐（127.0.0.1:7777，內網反代對外）；899 tests、dev_plan 真機讀到 part-011 session 7/7 todo | `.beacon/parts/part-014/DESIGN.md` | `.beacon/done/part-014/` |
| part-011 | backlog | **MiroFish optional adapter**（大型社會模擬，有實際需求才做）：opt-in 外部隔離 sandbox；Metatron 只輸出去識別化 scenario package（問題/角色/公開背景，不含私人原文）；MiroFish 永不讀寫 DB1/vault/transcript；報告回來標「模擬/非事實/非預測」；AGPL + Zep Cloud 依賴 → 隔離不入核心 | 見 backlog-028 | — |
| part-012 | **done** (2026-07-19) | **對話式 orchestrator**（backlog-033）：LLM-first 意圖路由（router 子 agent，七 intent；快徑保留零 LLM）；Discord 聽懂「明天有什麼/我存過哪些 X/最近怎樣/哈囉」+ 開放 recall + unclear 友善追問；寫入鐵律不變；附帶修 recall 空回應 fallback；886 tests、真機 QA 五句全通 | `.beacon/parts/part-012/DESIGN.md` | `.beacon/done/part-012/` |
| part-013 | **done** (2026-07-19) | **對話層補兩意圖**：router 加 directive（Discord 留開發指令入佇列）+ knowledge_list（知識庫瀏覽總覽,tag 分布走索引零檔案 I/O,808 篇 0.15s）；移除過廣「知識」快徑前綴；895 tests、真機 QA 通過 | `.beacon/parts/part-013/DESIGN.md` | `.beacon/done/part-013/` |
| part-014 | **done** (2026-07-19) | **MCP dev_plan + 儀表板常駐**：dev_plan 工具（第 11 MCP 工具，讀 OpenCode session 的 plan/todo 進度）+ 儀表板設 ONSTART 常駐（127.0.0.1:7777，內網反代對外）；899 tests、dev_plan 真機讀到 part-011 session 7/7 todo | `.beacon/parts/part-014/DESIGN.md` | `.beacon/done/part-014/` |
| part-015 | **done** (2026-07-20) | **知識庫 CRUD + 三層下鑽 + INDEX 中文化**：note_write proposal、browse/open、快徑；931 tests 級 | `.beacon/done/part-015/DESIGN.md` | `.beacon/done/part-015/` |
| part-016 | **done** (2026-07-21) | **能力速查 + 互動儀表板**：CHEATSHEET、B1 人話唯讀、B2 confirm/done（writer 路徑）、timeline、INTERFACES §5 修訂；939 tests、真瀏覽器 confirm/done、1280/768/375 雙 reviewer 視覺 QA 通過 | `.beacon/done/part-016/DESIGN.md` | `.beacon/done/part-016/` |
| part-017 | **done** (2026-07-21) | **LLM transient model failover hotfix**：429/5xx/網路錯誤/空內容依序切換 distinct 候選；永久性 4xx fail-fast；Discord-facing 注入 cooldown QA 與 943 tests 通過 | `.beacon/done/part-017/DESIGN.md` | `.beacon/done/part-017/` |
| part-018 | **design** | **Knowledge Base 2.0**：Topic/Evidence 雙層架構——修正 KB 1.0「單篇貼文=單篇筆記」設計缺陷，建立 topic（精煉知識）與 evidence（原始證據）分層，檢索預設只回傳 topic；以 21 篇待整理貼文為 seed migration | `.beacon/parts/part-018/DESIGN.md` | `.beacon/parts/part-018/TODO.md` |

## Success Criteria

- 兩次獨立的 agent 呼叫之間，狀態完全靠 DB1 接續（無 session）
- 行程 / 待辦 / coding 進度可透過 CLI 增查改
- 低健康 events 經夜間蒸餾後出現在 vault episodic/ 且可檢索；rehydrate 可沿 source_ids 讀回原文
- 任一 skill 管線單獨壞掉不影響 core 與其他 skill
- 子 agent 提案被 writer 驗證攔截（含拒絕路徑）可測試證明
- （part-006 slice-001，[PLANNED]）CLI / Discord / MCP 共用單一 invocation 入口回 `InvocationResult`；pending 確認為原子認領（併發雙確認只落地一次）；recall found 答案無有效引用即拒絕
- （part-007）同一偏好重複出現才升 stable；使用者 pin/forget 硬覆蓋評分；profile facets 可投影成 vault 可讀且可 recall
- （part-008）網路研究結果帶來源與 `external_untrusted` 標記，經 curator+writer 才進 semantic/；web 內容中的指令注入不被執行
- （part-009）world-diff 無重要變化 → 不呼叫 LLM；建議帶 expires_at；建議的 action 落地仍走確認
- （part-010）crowd-scenario 產出標 non-authoritative；輸入只吃 bucket，不含原始數字；子行程壞掉不影響 core

## Global Risks

- ~~向量索引選型~~ 已定案：sqlite-vec v0.1.9（本機實測 KNN OK）+ FTS5 前置（backlog-001）
- ~~LLM 供應商~~ 已定案：OpenAI 相容 API + base_url 環境變數（backlog-002）
- ~~OneDrive 鎖檔風險~~ 已定案：DATA_DIR 在本地 OneDrive 外；後期遷 VPS 只改 config.py
- Meta GraphQL 改版會弄壞 sync skills（繼承 threads-sync 已知風險）
- LLM 回傳 JSON 不穩——schema 約束 + 重試 1 次 + 壞即拒絕（part-002 DESIGN）
- **主動建議疲勞**（part-009）：advice 有每日配額 + 去重 + 靜默期；低價值建議不推播——避免變成噪音
- **敏感網路/帳號資料**（part-008）：allowlist + opt-in + 不自動抓私人帳號；抓到的內容不信任、不當指令
- **模擬被誤當事實**（part-010/011）：所有 scenario 輸出硬標 non-authoritative；不進 recall 事實層，只存 scenario 專區
- **crowd-scenario / MiroFish 授權**：crowd-scenario MIT（可 vendored）；MiroFish AGPL + Zep Cloud（隔離不入核心）；OpenHuman GPL（僅概念）

## Global Verification Strategy

- 每 SLICE 以 pytest 為主要自動驗證；`.beacon/verification/UnitTestCore.ps1` 驅動
- 無狀態性驗證：跨行程（process）測試——兩次獨立執行共享狀態僅經 DB1
- 管線 idempotency 驗證：同一命令跑兩次，第二次為 no-op
- 手動 QA：Obsidian 開 vault 檢查筆記格式與 MOC
