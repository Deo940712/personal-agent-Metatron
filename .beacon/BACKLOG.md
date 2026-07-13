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
Status: triage

Summary: golden queries 回歸測試（20-30 條檢索測例）+ consolidation 的 ADD/UPDATE/SKIP 三態決策測試 + LLM 決策欄位級驗證測試 + rehydrate 回水路徑測試。隨 part-003 一起設計。

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

### backlog-008: VPS 遷移

Type: idea
Status: triage

Summary: 後期把 data/ + vault 遷上 VPS。空間需求約 5–10 GB（圖片附件為大宗）。前提：config.py 路徑抽象已就位（part-001 保證）。排程器屆時改 cron。
