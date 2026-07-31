# Metatron — 個人排程 + 知識庫助理

> [繁體中文](README.md) | [English](README-en.md)

一個**無狀態**的個人 AI 助理：管理行程與待辦、把社群媒體存文（Threads / X / FB）
整理進 Obsidian 知識庫、追蹤 vibe-coding 專案進度。出門用 Discord 排事情與收提醒；
在家用 CLI 與 Obsidian。

**核心哲學：核心不累積對話狀態。** Discord 或 OpenCode 的 UI 可以維持長 session，
但每則訊息建立獨立 run：讀權威狀態 → 動作 → 經驗證寫入 → 結束。連續性來自結構化
的 DB1 / Beacon / vault / transcript 狀態與按需檢索，不是自動重播整段聊天。

## 架構總覽

```
User (CLI / Discord / Dashboard / MCP)
        │
        ▼
┌───────────────────────────────────────┐
│ Orchestrator (stateless, per-call)    │
│ read state → dispatch → synthesize   │
│ → write back → die                   │
└───────┬───────────────────────┬───────┘
        │ scoped tasks          │ structured proposals
        ▼                       ▼
   subagents ──proposals──→ writer.py (sole write gate: validate then land)
        │                       │
        ▼                       ▼
┌───────────────┐   ┌───────────────────────┐
│ DB1 state.db  │   │ DB2 Obsidian vault    │
│ SQLite        │   │ Markdown knowledge    │
│ System of     │   │ semantic/ episodic/   │
│ Record(11 tbl)│   │ agent/ (agent's own)  │
└───────┬───────┘   └──────────┬────────────┘
        │  nightly distillation │
        │  (health metabolism)  │
        └──────────┬────────────┘
                   ▼
   Cold-storage transcript (raw text, never deleted, rehydratable)
   Vector index index.db (derived, fully rebuildable)
```

四儲存層，各司其職：

| 儲存 | 角色 |
|---|---|
| **DB1** `state.db` (SQLite) | 系統記錄：行程、待辦、專案、事件、cursor、pending、agent_runs、directives、profile_facets、advices、watchlist |
| **DB2** Obsidian vault (Markdown) | 人類知識介面：你閱讀與編輯的筆記 |
| **冷儲存** transcript (JSONL + index) | 原始記錄層：蒸餾前文字，append-only，永不刪除 |
| **向量索引** index.db (FTS5 + sqlite-vec) | 衍生物：隨時刪除重建，不保存唯一資料 |

## 記憶系統（核心賣點）

記憶按性質分為四層，以**健康值代謝**管理生命週期（借鑑 memory-river / MemGPT /
Mem0 / Hermes；完整設計見 [ARCHITECTURE.md](ARCHITECTURE.md) §12）：

| 層 | 回答什麼 | 存哪 |
|---|---|---|
| Working State | 「做到哪了？」 | DB1 (tasks / cursors / projects) |
| Episodic | 「發生過什麼？」 | DB1 events → 蒸餾進 vault `episodic/` |
| Semantic | 「我知道什麼？」 | vault `semantic/`（貼文知識）+ `agent/`（偏好 / 教訓 / SOP） |
| Procedural | 「怎麼做？」 | `agents/*.md` 契約 + `skills/` 程式碼 |

**健康值代謝**：檢索命中 → 回血；久不用 → 衰減；歸零 → 進 trash（14 天保留、
被引用可復活）→ LLM 蒸餾進 vault。**遺忘 = 不再主動載入，永不刪除** — 原文永遠
在冷儲存，每份蒸餾筆記帶 `source_ids` 可隨時回水讀原文。

**檢索**（現行兩段 + dormant 向量段）：
```
① index-first  (INDEX 一行描述，零成本)
② FTS5         (CJK trigram 全文，零 embedding 成本)
③ vector KNN   (sqlite-vec，語意改述) ← dormant：程式已實作、production 未接線
④ rehydrate    (沿 source_ids 讀原文，用於精確數字/名字)
```

> 向量 KNN 程式碼存在（`core/vindex.py` vec0 表、`retrieve._stage_vec`），但無任何
> 呼叫端傳入 `embed_fn`，`upsert` 全不帶 vector，`rebuild` 僅建 FTS。現行有效檢索
> 為兩段（INDEX + FTS）+ rehydrate。詳見 [docs/MEMORY-zh.md](docs/MEMORY-zh.md) §4.1。

**KB 2.0（part-018）**：Topic / Evidence 雙層——Topic 是精煉知識與預設檢索入口；
Evidence 保留原文供追溯。一般查詢只搜 Topic；明確「搜原文 <關鍵字>」才搜 Evidence。

完整記憶契約：[docs/MEMORY-zh.md](docs/MEMORY-zh.md) / [docs/MEMORY-en.md](docs/MEMORY-en.md)

### 多層記憶：仍在評估中

儲存分層、檢索段落、跨 run 任務 checkpoint、LLM 自主 paging 是不同機制。目前只有
**A：無狀態重建 + 按需檢索** 已實作。**B：Task Capsule**、**C：task-scoped warm set**、
**D：LLM paging** 仍為候選，依 A→B→C→D 順序在真實長任務上評估；前者夠用就不往後走。

## 所有 Agent 與職責

**拓撲：Orchestrator + 無狀態子 agent**（2026 LangGraph / Claude Agent SDK / OpenAI
Agents SDK 收斂的生產拓撲）。子 agent 收到 scoped input，回結構化提案，消亡。

### 寫入鐵律：scoped 工具、程式驗證、單一 commit boundary

子 agent 可直接呼叫被授權的 read/propose/auto-apply 能力；LLM 永遠拿不到 raw SQL、
DB connection、任意檔案寫入或裸 `writer.apply`。寫入 proposal 經 writer 欄位級驗證；
高風險操作 preview→confirm，逾時視同拒絕。

### 子 Agent 名冊

**代號 Metatron**（天庭書記官）— orchestrator 本體。子 agent 冠天使名；code
identifier 不動以維持 API 穩定。完整對照表見 [AGENTS.md](AGENTS.md) §Angel naming registry。

| 天使 / 子 agent | 職責 | 狀態 |
|---|---|---|
| **Sandalphon** — `schedule` | 自然語言 → 行程/待辦提案；rrule 重複行程 | ✅ |
| **Raziel** — `consolidator` | 夜間蒸餾：過期事件 → 日誌摘要 / 偏好 facets；欄位級驗證 | ✅ |
| **Jophiel** — `curator` | 貼文評分(0-10 閘門)、分類、去重、入庫、連結；中文 FIRE 拆卡 | ✅ |
| **Zerachiel** — `recall` | 知識庫問答：RRF 融合 + rehydrate；引用程式面驗證；found/not_found 硬規則 | ✅ |
| **Uriel** — `coding_tracker` | 三源讀取(git + beacon + opencode) → 專案進度 | ✅ |
| **Cassiel** — `advisor` | 主動建議：world-diff 反思 → 可過期 advice → Discord 推播 | ✅ |
| **Anael** — `librarian` | vault 維護（orphan / broken links / dedupe） | ⏸ backlog-017 |
| sync-{threads,x,fb} | 平台抓取管線（非 LLM、純 CLI） | threads ✅ / x,fb ⏸ probe done |

## 介面

| 介面 | 場景 | 讀/寫 | 狀態 |
|---|---|---|---|
| **CLI** | 開發、排程 job | 讀+寫 | ✅ |
| **Obsidian** | 知識庫閱讀/編輯 | 讀+寫 | ✅ 免費 |
| **Discord bot** | 出門：排程 + 提醒 DM + 快查；私人 server，鎖 user-id | 讀+寫(via writer + confirm) | ✅ |
| **網頁儀表板** | 在家：總覽 + 受限操作（done / confirm）；127.0.0.1:7777 | 受限互動 | ✅ |
| **MCP server** (stdio + Tailscale HTTP) | OpenCode / Claude Code 查詢/排程/遠端開發迴圈 | 讀+寫(寫走 pending confirm) | ✅ |

介面 = 薄 adapter，零業務邏輯。能力層：`core/tools/`；權限矩陣：[docs/TOOLS.md](docs/TOOLS.md)；
設計權威：[INTERFACES.md](INTERFACES.md)。

## 使用

```bash
# 初始化（冪等）
python -m core.stm init

# 行程 / 待辦 / 專案 CRUD
python -m core.stm schedule add "開會" --start 2026-07-15T14:00 --remind 2026-07-15T13:30
python -m core.stm schedule list
python -m core.stm tasks add "買貓砂" --due 2026-07-16T20:00
python -m core.stm projects set my-agent --phase "part-019" --next "Evidence 批次 Topic 化"

# 自然語言（需 LLM key）
python -m core.agent "明天下午兩點跟阿明開會 提前30分提醒"

# 排程 job（Windows Task Scheduler / cron）
python -m core.agent --job remind        # 到期提醒（+ 掃逾時確認）
python -m core.agent --job consolidate   # 夜間記憶蒸餾

# Discord bot（需 token）
python -m channels.discord_bot
```

### 環境變數

| 變數 | 用途 |
|---|---|
| `MY_AGENT_LLM_API_KEY` | LLM（OpenAI 相容：OpenAI / OpenRouter / Groq / Ollama） |
| `MY_AGENT_LLM_BASE_URL` | 選配：非 OpenAI 端點 |
| `MY_AGENT_EMBED_BASE_URL` | 選配：獨立 embedding 端點 |
| `MY_AGENT_DISCORD_TOKEN` | Discord bot token |
| `MY_AGENT_DISCORD_ALLOWED_USER_ID` | Discord 白名單（逗號分隔；空 = 全拒） |

所有路徑在 `config.py`（`DATA_DIR` 等）— 換機器或遷 VPS 只改一個檔案。

## 可靠性設計

| 風險 | 機制 |
|---|---|
| 記憶幻覺 | 溯源硬規則：每篇帶 source；recall 引用程式面驗證（假引用整段丟棄）；found 必附 ≥1 驗證引用；空引用強制 not_found |
| LLM 決策污染 | 蒸餾每個決策過欄位級驗證（不合格跳過記 log） |
| 子 agent 亂寫 | Proposal + 單一 writer + danger gates；confirm 逾時 = deny |
| 資料遺失 | 原始記錄 append-only 永不刪；蒸餾失敗留 trash 等重試；index 可重建 |
| 靜默壞掉 | `agent_runs` 記每次執行；頂層防線保證不卡 running |

## 開發

```bash
python -m pytest tests/ -q     # 961 tests
```

工作流：[Beacon](.beacon/PLAN.md)（plan → design → slice → execute → verify →
**adversarial audit** → archive）。每個 slice 完成後跑證據式稽核（探針腳本實跑
疑似失敗路徑）；發現記 [KNOWN_ISSUES.md](KNOWN_ISSUES.md) 並轉為回歸測試。

| 文件 | 內容 |
|---|---|
| [ARCHITECTURE.md](ARCHITECTURE.md) | 系統設計權威（schema、流程圖、設計依據） |
| [INTERFACES.md](INTERFACES.md) | 介面層設計（CLI/Discord/Dashboard/MCP） |
| [docs/TOOLS.md](docs/TOOLS.md) | 能力、agent、介面、權限、儲存配對矩陣 |
| [docs/MEMORY-zh.md](docs/MEMORY-zh.md) | 記憶系統實作契約（API、不變量、故障恢復） |
| [docs/OVERVIEW-zh.md](docs/OVERVIEW-zh.md) | 一頁式架構導讀（本次新建） |
| [KNOWN_ISSUES.md](KNOWN_ISSUES.md) | 稽核發現與修復記錄 |
| [docs/USER-GUIDE-zh.md](docs/USER-GUIDE-zh.md) | 使用者手冊（怎麼用，不講技術） |

## 進度

完整時間線與各 part 設計見 [`.beacon/PLAN.md`](.beacon/PLAN.md)（進度唯一真相）。

摘要：parts 001-018 全數完成（961 tests green）；part-019（Evidence 批次 Topic 化）
slice-001 已可執行，閘門 A 已通過，Pilot 分群提案（原 786 筆，Pilot 49 筆：46 筆連結、3 筆保留，剩餘 737 筆）停在閘門 B 等待確認。自適應助理層完成（Personal Model / Advisor / Scout / Scenario Rehearsal；
跨 part 迴圈接線）。KB 2.0 Topic/Evidence 雙層上線。

未來方向：part-020 將專注於系統可靠性（錯誤恢復、重試機制、狀態一致性），為 part-021 的常駐 Supervisor 與 Watchdog 守護行程鋪路。

已知限制：向量 KNN 段 dormant（文件已標 dormant，接線待評估）；W1/W2 dashboard
安全問題 open（記錄於 KNOWN_ISSUES.md，程式修復待指示）。

前身專案：[threads-sync](https://github.com/Deo940712/threads-sync)
（Threads 存文 → Obsidian；本專案複用其管線模式並已整合為首個 sync skill）。
