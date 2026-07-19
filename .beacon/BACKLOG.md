# Beacon Backlog

Backlog is non-executable. Promote work through PLAN, PART DESIGN, PART TODO, and CURRENT before implementation.

## Items

### backlog-001: 向量索引選型

Type: question
Status: resolved (2026-07-13)

Summary: 已定案——**sqlite-vec v0.1.9**（本機實測通過：enable_load_extension 可用、vec0 虛擬表 KNN OK）。獨立檔 index.db（§5.4，可整檔重建）。檢索層補強：**FTS5 全文檢索**（同機實測 OK）排在向量之前——index-first → FTS5 → 向量 → rehydrate。embedding 走同一 OpenAI 相容端點（/v1/embeddings，text-embedding-3-small，dim 1536；Ollama 亦相容）。

### backlog-002: LLM 供應商與 key 管理

Type: question
Status: resolved (2026-07-13)

Summary: 已定案——**OpenAI 相容 API**：官方 `openai` 套件 + 可配置 base_url（OpenAI/OpenRouter/Groq/DeepSeek/本地 Ollama 同一介面）。config.py 走環境變數：MY_AGENT_LLM_BASE_URL / MY_AGENT_LLM_API_KEY / 模型名。支援兩檔模型分級（cheap/strong）。

### backlog-003: 排程器選型

Type: question
Status: triage

Summary: Windows Task Scheduler（傾向，符合無狀態哲學）vs 常駐 daemon。影響 part-003 夜間 job 觸發方式。

### backlog-004: x-sync / fb-sync 抓取策略

Type: idea
Status: triage

Summary: X 官方 API 付費且 ~800 則封頂、archive 不含書籤。起步用 xarchive Chrome 擴充匯出 JSON + 自寫轉換器入 vault；要自動化再複製 threads-sync GraphQL 攔截模式（X query ID 每 2-4 週輪換，需 probe 工具）。FB 反爬最強，最後做。

### backlog-006: 子 agent 執行框架選型

Type: question
Status: resolved (2026-07-13)

Summary: 已定案——**自寫薄層**：單次 chat.completions 呼叫 + agents/*.md prompt 契約 + JSON 提案解析。不用 LangGraph/Agent SDK（session/循環/checkpointer 皆與無狀態架構重複）。

### backlog-007: 記憶可靠性測試基建

Type: test-gap
Status: in-progress (2026-07-19，part-011 todo 8)

Summary: golden queries 回歸測試（20-30 條檢索測例）+ consolidation 的 ADD/UPDATE/SKIP 三態決策測試 + LLM 決策欄位級驗證測試 + rehydrate 回水路徑測試。隨 part-003 一起設計。

**進度（part-011 todo 8）**：golden queries harness 已落地——`tests/test_golden_queries.py`（15 筆種子筆記跨主題 + 24 條 query→expected-hit 斷言 + 負向鑑別力測試，確定性、零 LLM/網路，測 `retrieve.search` index+FTS 層）。改索引/檢索邏輯必跑。consolidation ADD/UPDATE/SKIP、欄位級驗證、rehydrate 路徑測試已散在 test_consolidate/test_facets_writer/test_retrieve（既有）。cross-encoder rerank（backlog-025）觸發條件 = 此 harness 出現排名問題。

### backlog-009: 冷儲存 transcript 層

Type: design-debt
Status: triage

Summary: 原始記錄（events 原文、sync raw dumps）轉 append-only JSONL + byte-offset 索引（借鑑 memory-river transcript 層）。目前 raw dumps 已落地 data/raw/，正式化為可尋址冷儲存在 part-003 設計。

### backlog-010: vault INDEX 規範化

Type: idea
Status: triage

Summary: 借鑑 DesktopCommanderMCP knowledge-base skill：穩定 ID（YYYYMMDD-slug）、受控 tag 詞彙表、INDEX registry 一行描述、孤兒/斷鏈/tag 蔓延維護 SOP。讓 recall 走 index-first。隨 part-003/part-004 落地。

### backlog-017: librarian 子 agent（vault 圖書管理員）

Type: idea
Status: triage

Summary: ARCHITECTURE §4.3——vault 維護子 agent。Phase A 確定性掃描（vault.scan：孤兒/斷鏈/content_hash 重複/tag 蔓延/INDEX 漂移/stale + **附件孤兒 + raw dumps 老化報告**，零 LLM）+ Phase B LLM 整理（預設關）。借鑑 Hermes Curator：快照先行（git commit）、永不刪除（.archive/ 可還原）、pinned 豁免、dry-run 先行、per-run 報告。管轄 = vault + data/ 附屬掃描；vault 外本機檔案不管。vault_maintenance 提案走 writer。落地時機：part-004 之後（vault 有量才需要維護）。

### backlog-018: 危險操作閘門

Type: idea
Status: triage

Summary: ARCHITECTURE §3.2——三層閘門（硬底線永不執行 / 需確認 / 自動放行）+ 確認逾時 fail-closed。借鑑 Hermes approval 分層。writer.py 實作時（part-002）內建。

### backlog-016: Agent 知識庫（vault/agent/）

Type: idea
Status: triage

Summary: ARCHITECTURE §4.2——vault 加 agent/ 三子目錄（profile 偏好/ops 營運教訓/sop 學到的流程）。同 frontmatter schema（source=agent_knowledge）、全部免疫衰減、漸進揭露載入（只注入 INDEX 一行描述）、sop 只顯式保存。orchestrator 上下文組裝掛鉤在 part-002；consolidation 蒸餾偏好進 profile/ 在 part-003。

### backlog-014: Discord bot（part-002.5）

Type: idea
Status: triage

Summary: `channels/discord_bot.py`（discord.py）：私人 server + 鎖 user ID、訊息指令（today/todo/done/proj/自然語言排程）、寫入走 writer 預覽+✅按鈕確認、提醒 DM（解掉通知管道決策）、待確認提案持久化 DB1。深度知識查詢不走 Discord。設計權威 INTERFACES.md §4。

### backlog-015: 唯讀網頁儀表板（part-003.5）

Type: idea
Status: triage

Summary: `channels/dashboard.py`：FastAPI + 一頁 htmx、綁 127.0.0.1:7777 無登入、SQLite `mode=ro` 物理唯讀。七個 GET API + 五版塊（今日/專案/管線健康/記憶狀態/事件流）。遷 VPS 後要遠端看再加 Tailscale/basic auth。設計權威 INTERFACES.md §5。

### backlog-012: MCP server（Phase 6）

Type: idea
Status: triage

Summary: 把 recall_query / schedule_list / project_status 包成 MCP server（借鑑 Horizon MCP 模式），在 OpenCode/Claude Code 內直接問助理。唯讀優先；寫入類必仍走 writer.apply + 使用者確認。對應 PLAN part-006。

### backlog-013: OpenCode session 掃描器

Type: idea
Status: triage

Summary: `core/tools/opencode.sessions`：讀 `C:\Users\tcart\.local\share\opencode` 的 session JSON（唯讀），取每專案最後 session 時間與摘要，作為 coding_tracker 第三訊號源。實作前先確認 storage 格式與路徑（版本可能變）。隨 part-005 落地。

### backlog-011: curator 評分閘門

Type: idea
Status: triage

Summary: 借鑑 Horizon：AI 評分 0-10 + 閾值過濾 + 分類配額（category_groups limit）+ 跨源同文合併（URL/內容 hash）。隨 part-004 curator 設計落地。

### backlog-022: 主題連續性蒸餾（part-004.5）

Type: idea
Status: triage

Summary: 借鑑 [Membox](https://arxiv.org/abs/2601.03785)（2026，temporal F1 +68% vs Mem0/A-MEM）：蒸餾分組從「按天」改「按天+LLM 標主題」；consolidator 輸出加 topic 欄位；跨天同主題筆記自動 related 連結串成事件 trace。解「同主題散多天=碎片筆記」問題。輕量版——不引入整套 Topic Loom（我們的 events 粒度本來就粗）。

### backlog-023: 矛盾偵測 + supersede 執行（part-004.5）

Type: design-debt
Status: triage

Summary: supersede 鏈設計在 ARCHITECTURE §5.2 但無程式碼執行。借鑑 [Mneme](https://mingllm.com/prehistoric/paper.pdf)（矛盾解析 0.66 vs Mem0 0.22，關鍵=雙側保留+co-surface+contradiction-first read）：①consolidator 蒸餾 preference 前注入既有 agent/profile INDEX 描述 → 可輸出 supersedes 決策（過欄位級驗證）→ writer 給舊筆記補 superseded_by；②recall 契約加「引用前查 superseded_by；同主題矛盾必須並列詢問使用者」。

### backlog-024: RRF 跨段融合檢索（part-004.5）

Type: idea
Status: triage

Summary: 借鑑 Cognis/Mneme 標配：retrieve.search 從「前段命中即返回」改「index/FTS/vec 三段並行取候選 → Reciprocal Rank Fusion 合分 → top-k」；保留 index-first 強命中（多 token）短路以維持零成本路徑。約 20 行核心邏輯。

### backlog-025: 檢索後 cross-encoder rerank（待訂）

Type: idea
Status: triage

Summary: Cognis 用 BGE 類 cross-encoder rerank 收尾。個人量級（<1 萬筆記）暫不需要；**觸發條件：golden queries（backlog-007）出現排名問題時再做**。

### backlog-026: per-category 衰減速率（待訂）

Type: idea
Status: triage

Summary: 現在全表統一 0.05/day。daily-log 類可快衰、coding 決策類慢衰。**觸發條件：真實使用 1-2 個月後，有 events 存取數據再調**——現在調是憑空猜參數。同時記錄 known limitation：Obsidian 手動開筆記不回血（無 hook；可能解法=librarian 掃 workspace 記錄，侵入性高暫不做）。

### backlog-019: FIRE 拆卡方法論進 curator

Type: idea
Status: triage

Summary: 借鑑 [twhsi/skills](https://github.com/twhsi/skills) fire-analysis-card：中文筆記語意檢索前處理（Full-D 全維展開 / Index / Route / Evolution 四層結構）。寫進 agents/curator.md 契約（part-004 設計時）——結構化拆卡補 FTS5 中文 trigram 弱點，提升中文貼文檢索命中率。方法論進 prompt 契約，不改 core。

### backlog-020: 週回顧蒸餾模式

Type: idea
Status: triage

Summary: 借鑑 twhsi/skills weekly-reverse-review：consolidation 加「週回顧」模式——讀 episodic/ 週摘要 + schedule/tasks → 產週計畫草稿（提案，走 writer+確認）。工作流存 vault/agent/sop/（顯式保存）。時機：part-005 後（episodic 有足夠累積才有料可回顧）。

### backlog-021: 日計畫九宮格模板

Type: idea
Status: triage

Summary: 借鑑 twhsi/skills todays-daily-plan：vault 日記/日計畫的九宮格時段模板（Mandala Grid）。口述→行程已由 schedule 子 agent 覆蓋；此項僅為 vault 輸出格式模板，隨使用者實際需要再加（低優先）。

**評估記錄（2026-07-13）**：twhsi/skills 全集 15 個已逐一評估。不採用：auto-luhmann-numberer（魯曼編號與 YYYYMMDD-slug 穩定 ID 衝突，雙編號系統 = librarian 維護惡夢）、epub/摺頁書/卡片渲染系列（輸出格式類，與助理核心無關，要用時在 Claude Code 直接裝）、thebrain-bird-address（綁 TheBrain，我們用 Obsidian）、graph-view（Obsidian 內建覆蓋）。

### backlog-005: data/ 移出 OneDrive

Type: risk
Status: resolved

Summary: 已定案——DATA_DIR = `C:\Users\tcart\my-agent-data`（本地、OneDrive 外）。後期遷 VPS 只改 config.py。

### backlog-027: OpenHuman 概念借鑑(不接程式碼)

Type: decision
Status: resolved (2026-07-14)

Summary: 評估 [tinyhumansai/openhuman](https://github.com/tinyhumansai/openhuman)(GPL-3.0、Rust、Early Beta、大型桌面 Agent OS)。**決定:只 clean-room 借概念,不接程式碼、不接核心。** 理由:①它自帶 SQLite memory / Obsidian wiki / tinyagents graph / tinyflows workflow / channels / MCP / subconscious,與 Metatron 核心全面重複,直接接會出現「哪邊才是真實資料」的 SoR 崩壞;②執行模型相反(它是常駐 checkpointed graph + 三層 subagent + 背景 heartbeat,Metatron 是無狀態單次呼叫、單層即棄);③GPL-3.0,搬程式或連結會產生衍生作品限制。**借的概念**(用 Python 自寫):learning facets(證據/穩定度/pin/forget → part-007)、subconscious world-diff + quiet-tick(→ part-009)、advice-first proactivity。**不借**:persistent agent graph、三層 subagent、它的 SQLite/vault、workflow engine、channels、x402/wallet、Rust runtime。

### backlog-028: MiroFish 未來隔離 adapter

Type: idea
Status: triage (gate: 有實際大型模擬需求才做 → part-011)

Summary: 評估 [666ghj/MiroFish](https://github.com/666ghj/MiroFish)(AGPL-3.0、Python、Flask+Vue、依賴 Zep Cloud + OASIS + CAMEL-AI)。它是大型多人社會模擬/輿論預測器(輸入文件 → GraphRAG → 生成大量 OASIS persona → 模擬 Twitter/Reddit → 預測報告),**不是個人助理記憶系統**。**決定:不進核心;未來做 opt-in 外部隔離 adapter(part-011)。** 只有真的需要大型社會型模擬(產品上市反應、輿論演化、政策連鎖)時才用;Metatron 只輸出去識別化 scenario package(問題/角色/公開背景,不含私人原文),MiroFish 永不讀寫 DB1/vault/transcript,報告回來硬標「模擬/非事實/非預測」。AGPL + Zep Cloud 依賴 → 隔離不入核心。日常小型演練用 crowd-scenario(part-010)即可,不需要 MiroFish。

### backlog-029: AgentSpec / model 分級 registry

Type: idea
Status: triage (gate: part-007+ 有多個新 agent 型別時)

Summary: 架構審查發現子 agent 契約頂部的 `type/model/tools` 只是文件、程式沒讀(`LLM_MODEL_STRONG` 實際未用)。建議建一個**靜態** `AGENT_SPECS` registry(display_name/contract/execution/output_kind/model_tier/tools),用於啟動時驗證契約存在、確認 output kind、文件與程式對照。但**工具權限仍由程式碼硬白名單控制**(不因 markdown 寫了 tools 就授權)。不做動態 plugin framework。時機:part-007+ 出現多個新 agent 型別(Personal Model / Advisor / Scout)時一起建,不預先造抽象。

### backlog-008: VPS 遷移

Type: idea
Status: triage

Summary: 後期把 data/ + vault 遷上 VPS。空間需求約 5–10 GB（圖片附件為大宗）。前提：config.py 路徑抽象已就位（part-001 保證）。排程器屆時改 cron。

VPS 遷移 checklist（part-006-slice-003 MCP HTTP 就位後）：
1. 裝 Tailscale，取得本機 Tailscale IP（`100.64.0.0/10` CGNAT range）。
2. 設環境變數 `MY_AGENT_MCP_BIND_HOST=<Tailscale IP>`（未設 = 127.0.0.1 僅本機）。
3. 啟動 `python -m channels.mcp_http`（綁 config.MCP_HTTP_PORT=7788）。bind guard
   fail-closed：綁公網 IP 或 0.0.0.0 → 拒絕啟動（Tailscale 已是 WireGuard 加密私網，
   不需 token/TLS）。
4. 筆電 OpenCode 設 MCP server URL 指向 `http://<Tailscale IP>:7788` → 遠端問答/排程/確認。
5. 排程 job（remind/consolidate/curate/track）改 cron；DATA_DIR 改 VPS 路徑（只改 config.py）。
6. 手動 QA：筆電 OpenCode 遠端連 → dev_status/排行程→確認→落地端到端。

### backlog-030: 強命中短路擴大覆蓋（Engram「查表先於計算」實證支持）

Type: idea
Status: triage

Summary: DeepSeek Engram 論文（arXiv 2601.07372）證明：確定性、便宜的 O(1) 查表若設計得好，是一等元件、不是雜項優化——命中就繞過昂貴計算。對應本專案 `core/retrieve.py` §4.1 的**強 index 命中短路**（≥2 token 命中同筆記 title/summary → 零 embedding/FTS 直接回）。此項是**純省成本、零風險**方向：讓短路更常命中、更廣覆蓋。

觸發條件：real workload 觀察到 recall 頻繁走到向量 KNN（step 3）而其實答案在 INDEX registry 就有 → 才動工。
可能做法（待觸發後評估，不預先實作）：更多筆記進 INDEX、改善 distilled title/summary 品質、單 token 查詢也允許短路的條件放寬。量測基準：短路命中率、平均省下的 embedding 呼叫數。
**MEM 對齊**：不改權威、不改 A/B/C/D 決策；純檢索層優化，屬 §4.1 既有機制的調校。

### backlog-031: Task Capsule（方案 B）評估指標改寫——量「LLM 認知負荷」而非「IO reads」

Type: question
Status: triage

Summary: part-003.2 A/B 實驗測出 `retain_a`，因 B 為安全 stale-by-default 照樣重讀權威、沒省到 authority reads。**但 Engram 論文指出 B 的真正收益不在 IO**——在於 LLM 不必每次「重新拼湊出任務狀態」（論文：記憶模組讓推理任務提升**更大**，BBH +5.0、NIAH 84.2→97.0，因為釋放了早期層的重建負荷）。

決策問題：若未來重測 B，指標應從「開了幾個檔案 / 省了幾次 read」改為「**LLM 要花多少 token / 多少推理步驟才重建出正確任務狀態**」。這需要真實 LLM 迴圈（part-003.2 報告的 threats-to-validity 已誠實標註「無 LLM = proxy」）。
觸發條件：出現 A（無狀態重建）在真實長任務上**可重現的失敗**（對齊 MEM-17：A 沒失敗就維持 A）→ 才重啟 B 實驗，並套用新指標。
**MEM 對齊**：不改 B/C/D 候選狀態；只更新未來實驗的量測方法。報告見 `docs/ECC-TASK-CAPSULE-REPORT-zh.md`，證據見 `.omo/evidence/task-13-ecc-task-capsule-experiment-summary.{json,csv}`。

### backlog-032: U 型曲線紀律——記錄「克制規則」的外部實證

Type: idea
Status: triage

Summary: Engram 論文的 U 型曲線（最佳約 75-80% 計算 / 20-25% 記憶）證明**記憶太多會傷推理**。這直接用數據支持本專案既有的「克制」規則：MEM-08（Capsule 最小化）、MEM-09（warm set 可丟棄）、MEM-10（paging 需證據門檻）、MEM-17（問題觸發才升級）。

行動（低成本、文件層）：在 `docs/MEMORY-zh.md` §5 候選方案處，補一條外部實證註記——「塞更多記憶進 context 會傷推理」有 27B 模型實驗背書，作為未來抗拒『把整個任務歷史全塞進 context』的引用證據。**（註記已落地 2026-07-19，MEMORY-zh.md §5 + MEMORY-en.md §5，CheckMemoryDocs 驗證通過）**
觸發條件：下次有人（或自己）提議放寬 MEM-08/09/10、或提議自動 paging（方案 D）時 → 引用此項作為反對的實證依據。
**MEM 對齊**：純文件補強，不改任何契約狀態或實作。
**注意**：U 型的「75-80/20-25」比例是模型參數預算的分配，**不可直接套用**到本專案（外部記憶無此預算概念）；只借「太多記憶傷推理」的定性結論。

### backlog-033: 對話式 orchestrator(LLM-first 路由,「聰明且人性化」)

Type: idea
Status: triage (priority: HIGH — 使用者真機使用後的第一個體感回饋)

Summary: 真機 QA 後使用者回饋:「想要的 agent 是很聰明且人性化的,現在感覺是固定
程序」。根因:①chat.py 路由是關鍵字表(今天/todo/done),未命中全部丟給單一用途
的排程解析 →「明天」得到蠢回應;②recall 在 Discord 被關(內容分級決策已因
Tailscale/內網反代過時);③LLM 只解析不對話——沒有意圖分類→能力選擇→自然語言
回覆的對話層。升級方向(part-012 候選):LLM-first router(單次呼叫分類意圖:
查詢/排程/知識問答/建議/演練/閒聊)→ 分派既有 capability → 自然語言組裝回覆;
Discord 開 recall;失敗/不明意圖友善追問而非「這不是行程/待辦」。**寫入鐵律不變**
(提案→writer→確認);變的只是理解與表達層。成本:每則訊息多一次 cheap LLM 呼叫。
