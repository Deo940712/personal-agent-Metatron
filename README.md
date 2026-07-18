# Metatron  — 個人行程 + 知識庫助理

> 繁體中文 | [English](README-en.md)

一個**無狀態**的個人 AI 助理:管理行程與待辦、把社交平台(Threads / X / FB)存的
貼文整理進 Obsidian 知識庫、追蹤 vibe coding 專案進度。出門用 Discord 排事情、
收提醒推播;在家用 CLI 與 Obsidian。

**核心哲學:核心不累積對話狀態。** Discord/OpenCode 等 UI 可以維持長 session，
但每則訊息都是獨立 run：讀權威資料 → 執行 → 經驗證寫回 → 結束。連續性不靠
自動重播整段聊天，而靠 DB1/Beacon/vault/transcript 的結構化狀態與按需檢索。

## 架構總覽

```
使用者(CLI / Discord / 儀表板 / MCP)
        │
        ▼
┌────────────────────────────────────┐
│ Orchestrator(無狀態,一次呼叫即結束)│
│ 讀狀態 → 派工子 agent → 綜合 → 寫回 │
└──────┬─────────────────────┬───────┘
       │ scoped 任務          │ 結構化提案
       ▼                     ▼
   子 agents ──提案──▶ writer.py(唯一寫入口:驗證後落地)
       │                     │
       ▼                     ▼
┌──────────────┐   ┌───────────────────────┐
│ DB1 state.db  │   │ DB2 Obsidian vault     │
│ SQLite        │   │ Markdown 知識庫         │
│ System of     │   │ semantic/ episodic/    │
│ Record(7 表) │   │ agent/(給 agent 的知識)│
└──────┬────────┘   └──────────▲────────────┘
       │  夜間蒸餾(健康值代謝)  │
       └──────────┬────────────┘
                  ▼
   冷儲存 transcript(原文永不刪,可回水)
   向量索引 index.db(衍生物,可整檔重建)
```

四個儲存層,各司其職:

| 儲存 | 角色 |
|---|---|
| **DB1** `state.db`(SQLite) | System of Record:行程、待辦、專案、事件、游標、待確認提案 |
| **DB2** Obsidian vault(Markdown) | 人類知識介面:你在 Obsidian 讀寫的筆記 |
| **冷儲存** transcript(JSONL + 索引) | 原始記錄層:蒸餾前的原文,append-only 永不刪 |
| **向量索引** index.db(sqlite-vec + FTS5) | 衍生物:壞了刪掉重建,不存唯一資料 |

## 記憶系統(核心賣點)

記憶按性質分四層、按生命週期用「健康值代謝」管理(借鑑 memory-river / MemGPT /
Mem0 / Hermes 等,設計依據見 [ARCHITECTURE.md](ARCHITECTURE.md) §12):

| 層 | 回答的問題 | 存哪 |
|---|---|---|
| Working State | 「做到哪了?」 | DB1(tasks / cursors / projects) |
| Episodic 情節 | 「發生過什麼?」 | DB1 events → 蒸餾進 vault `episodic/` |
| Semantic 語義 | 「我知道什麼?」 | vault `semantic/`(貼文知識)+ `agent/`(給 agent 的偏好/教訓/SOP) |
| Procedural 程序 | 「怎麼做?」 | `agents/*.md` 契約 + `skills/` 程式碼 |

**健康值代謝**:記憶被檢索命中就回血、久不用就衰減;歸零進垃圾桶(保留 14 天,
期內被引用可復活)→ 到期由 LLM 蒸餾成 vault 筆記。**遺忘 = 不再主動載入,
不等於刪除**——原文永在冷儲存,蒸餾筆記帶 `source_ids` 隨時可「回水」讀回原文。

**四段級聯檢索**:
```
① index-first(INDEX 一行描述,零成本)
② FTS5 全文(中文 trigram,零 embedding 成本)
③ 向量 KNN(sqlite-vec,語意檢索)
④ rehydrate(沿 source_ids 讀回原文,要確切數字/名字時)
```

技術細節(完整 API、不變量、故障恢復):[docs/MEMORY-zh.md](docs/MEMORY-zh.md)

### 多層記憶：目前仍在評估

不要混淆「儲存分層」「檢索階段」「跨 run 任務 checkpoint」與「LLM 自主
STM→MTM→LPM paging」。目前只有 **A：無狀態重建 + 按需檢索**已實作；
**B：Task Capsule**、**C：task-scoped warm set**、**D：LLM 自主 paging**均是
候選方案，按 A→B→C→D 以真實長任務比較，前一級足夠就不增加複雜度。

**記憶強化(part-004.5,已完成,依 2026 論文實證)**:主題連續性蒸餾(Membox:
同主題跨天雙向 related 串連)、矛盾偵測 + supersede 執行(Mneme:新舊偏好雙側
保留、recall 讀到被取代筆記會提示新版)、RRF 跨段融合檢索(Cognis:k=60,
強命中保留零成本短路)。待訂(觸發條件制):cross-encoder rerank(golden
queries 出排名問題時)、per-category 衰減速率(真實使用 1-2 月有數據時)。

## 所有 Agent 的職能

**專案代號:Metatron**(天界書記官)——orchestrator 本人。子 agent 從
Metatron 麾下天使名挑選(顯示層命名;程式碼識別符維持技術名以保 API 穩定,
完整映射見 [AGENTS.md](AGENTS.md) §Angel naming registry)。

**拓撲:Orchestrator + 無狀態子 agent**(2026 年 LangGraph / Claude Agent SDK /
OpenAI Agents SDK 收斂的生產標準)。子 agent 拿 scoped 輸入、回結構化提案、即棄。

### 寫入鐵律：Agent 可用 scoped tools，程式驗證，單一 commit boundary

子 agent 可依 allowlist 自主呼叫 read/propose/低風險 auto-apply capability，不需要
Metatron 代辦每次 tool call；但 LLM 永不取得 raw SQL、DB connection、任意檔案寫入
或裸 `writer.apply`。agent/使用者發起的 proposal mutation 走 `writer.apply` 驗證；
受信任的內部 job pipeline（如夜間蒸餾）走各自的 deterministic validated write path；
兩者皆不繞過驗證。高風險操作 preview→confirm，逾時一律拒絕。Metatron 是 control
plane，不是所有工具的同步 data-plane proxy。

### 子 agent 一覽

| 天使 / 子 Agent | 職能 | 輸入 | 輸出 | 狀態 |
|---|---|---|---|---|
| **Sandalphon** — `schedule` | 自然語言 → 行程/待辦提案(「明天下午兩點開會提前30分提醒」);rrule 重複行程 | 使用者原句 + 現有行程 | `schedule_change` / `task_change` 提案 | ✅ |
| **Raziel** — `consolidator` | 夜間蒸餾:到期事件 → 日誌摘要(episodic)/ 使用者偏好(agent/profile);每個決策過欄位級驗證,不得虛構來源 | 到期 events 批次 | 蒸餾組(kind/title/summary/tags/source_ids/confidence) | ✅ |
| **Jophiel** — `curator` | 貼文評分(0-10 閘門 4.0)、分類、依日期去重、入 vault;manual_tags 永不覆蓋 | inbox 筆記批次 | `classify_note` 提案 | ✅ |
| **Zerachiel** — `recall` | 知識庫問答:index→FTS→向量 RRF 融合 + rehydrate;非空引用逐一驗證真實性(假引用整答丟棄);superseded_by 提示;嚴格 found/not_found(found 必附 ≥1 驗證過引用,空引用一律 not_found,part-006 已實作) | 查詢字串 | 帶引用的答案 | ✅ |
| **Uriel** — `coding_tracker` | vibe coding 進度:三源唯讀掃描(git + `.beacon/CURRENT` + OpenCode sessions,beacon 最高權威)→ 每專案 phase/blockers/next | 已註冊專案 | `project_update` 提案 | ✅ |
| **Anael** — `librarian` | vault 圖書管理員:孤兒/斷鏈/重複/tag 蔓延維護;兩階段、快照可回滾、永不刪除 | vault.scan 確定性報告 | `vault_maintenance` 提案(dry-run 先行) | 📋 backlog-017 |
| sync-{threads,x,fb} | 平台抓取管線(**非 LLM**,純 CLI,idempotent 可續傳) | cursor | new_count, status | threads ✅ / x,fb 🔨 phase-0 probe 完成 |

> Michael / Camael / Raphael / Ophanim / Cassiel / Azrael 是使用者提名但**目前無對應 agent** 的天使名,
> 已在 [AGENTS.md](AGENTS.md) §Angel naming registry 「Archived」段封存。日後若真的獨立成 agent 才啟用,不預先佔位。

子 agent 分兩型:**純函數型**(單次 LLM 呼叫、無工具、可重放測試——schedule/
consolidator/curator/librarian/coding_tracker)與**代理型**(目前 recall 使用迭代唯讀
工具)。未來是否給更多 agent 工具，依「下一步是否真的依賴前一步結果」決定，並受
scope/budget/timeout 控制；shared-state commit 仍只有 deterministic writer boundary。

## 介面

| 介面 | 場景 | 讀/寫 | 狀態 |
|---|---|---|---|
| **CLI** | 開發、排程 job | 讀+寫 | ✅ |
| **Obsidian** | 知識庫閱讀/編輯(vault 就是 UI) | 讀+寫 | ✅(零成本) |
| **Discord bot** | 出門:排事情(預覽→✅按鈕→落地)+ 提醒 DM 推播;私人 server 鎖 user id | 讀+寫(走 writer+確認) | ✅ 程式面 |
| 網頁儀表板 | 在家總覽 + 系統健康(127.0.0.1:7777;GET-only + mode=ro 三層唯讀) | 唯讀 | ✅ |
| MCP server(stdio + Tailscale HTTP) | 在 OpenCode/Claude Code 內問助理/排程/遠端開發迴圈 | 讀+寫(寫走 pending 確認) | ✅ 程式面(VPS 真機 QA 待環境) |

介面 = 薄 adapter,零業務邏輯；today/week/proj/todo/done/recall 已共用 typed
`core/tools/` 能力層。功能／agent／interface／permission／storage 權威矩陣見
[docs/TOOLS.md](docs/TOOLS.md)，介面設計見 [INTERFACES.md](INTERFACES.md)。

## 使用

```bash
# 初始化(idempotent)
python -m core.stm init

# 行程/待辦/專案 CRUD
python -m core.stm schedule add "開會" --start 2026-07-15T14:00 --remind 2026-07-15T13:30
python -m core.stm schedule list
python -m core.stm tasks add "買貓砂" --due 2026-07-16T20:00
python -m core.stm projects set my-agent --phase "part-004" --next "curator"

# 自然語言(需 LLM key)
python -m core.agent "明天下午兩點跟阿明開會 提前30分提醒"   # 預覽 → y → 落地

# 排程 job(Windows Task Scheduler / cron)
python -m core.agent --job remind        # 到期提醒(+ 順掃逾時待確認)
python -m core.agent --job consolidate   # 夜間蒸餾

# Discord bot(需 token,見下)
python -m channels.discord_bot
```

### 環境變數

| 變數 | 用途 |
|---|---|
| `MY_AGENT_LLM_API_KEY` | LLM(OpenAI 相容:OpenAI / OpenRouter / Groq / Ollama) |
| `MY_AGENT_LLM_BASE_URL` | 選配:非 OpenAI 官方端點 |
| `MY_AGENT_EMBED_BASE_URL` | 選配:embedding 獨立端點 |
| `MY_AGENT_DISCORD_TOKEN` | Discord bot token |
| `MY_AGENT_DISCORD_ALLOWED_USER_ID` | Discord 白名單(逗號分隔;空 = 全拒) |

路徑集中在 `config.py`(`DATA_DIR` 等)——換機器/遷 VPS 只改這個檔案。

## 可靠性設計

| 風險 | 機制 |
|---|---|
| 記憶幻覺 | 溯源硬規則:每筆記必帶來源;recall 提供的非空引用逐一驗證真實(假引用整答丟棄);found 必附 ≥1 驗證過引用,空引用一律 not_found(程式硬規則,不信 LLM 自報);可回水讀原文 |
| LLM 決策污染 | 每個蒸餾決策過欄位級驗證(不得虛構 source_ids);不合格跳過並記 log |
| 子 agent 亂寫 | 提案制 + 單一 writer + 危險閘門;確認逾時 fail-closed |
| 資料遺失 | 原文 append-only 永不刪;蒸餾失敗事件留在垃圾桶下輪重試;索引可重建 |
| 靜默壞掉 | `agent_runs` 記錄每次執行 status;頂層防線保證 run 不卡 running |

## 開發

```bash
python -m pytest tests/ -q     # 630 tests
```

工作流:[Beacon](.beacon/PLAN.md)(plan → design → slice → execute → verify →
**adversarial audit** → archive)。每個 slice 歸檔後跑實證稽核(探針腳本真執行
可疑路徑),發現全記錄在 [KNOWN_ISSUES.md](KNOWN_ISSUES.md) 並轉 regression test。

| 文件 | 內容 |
|---|---|
| [ARCHITECTURE.md](ARCHITECTURE.md) | 系統設計權威(schema、流程圖、設計依據) |
| [INTERFACES.md](INTERFACES.md) | 介面層設計(CLI/Discord/儀表板/MCP) |
| [docs/TOOLS.md](docs/TOOLS.md) | 能力工具、agent、介面、權限與儲存配對矩陣 |
| [docs/MEMORY-zh.md](docs/MEMORY-zh.md) | 記憶系統實作規格(API、不變量、故障恢復) |
| [KNOWN_ISSUES.md](KNOWN_ISSUES.md) | 稽核發現與修復記錄 |

## 進度

- ✅ part-001 基礎層(schema + CRUD CLI)
- ✅ part-002 Orchestrator + writer + schedule agent + remind
- ✅ part-002.5 Discord bot(兩階段確認 + DM 推播)
- ✅ part-003 記憶核心(冷儲存/代謝/蒸餾/檢索)
- ✅ part-003.1 記憶架構雙語契約(MEM-01..17 + A/B/C/D 評估框架)
- ✅ part-003.2 Task Capsule A/B 實驗(隔離原型;判定 retain_a,未改正式 schema)
- ✅ part-003.5 唯讀儀表板(stdlib http.server;127.0.0.1:7777;三層唯讀)
- ✅ part-004 sync skills(threads runner + curator + recall)
- ✅ part-004.5 記憶強化(主題 trace / supersede / RRF 融合)
- ✅ part-005 coding_tracker(git + beacon + opencode 三源,真三源 gate 通過)
- ✅ part-006 MCP server(能力工具基座/互動硬化/stdio/Tailscale HTTP;630 tests)
- 🔨 x/fb-sync phase-0 probe 完成(playwright GraphQL 攔截 + transform/store + tests)
- 📐 part-007 Personal Model / part-008 Knowledge Scout / part-009 Proactive
  Advisor / part-010 crowd-scenario → 已設計待 promote
- 📋 待使用者環境:四批真 QA(LLM key / Discord token / threads session)+
  part-006 VPS + Tailscale 真機 QA(backlog-008)

前身專案:[threads-sync](https://github.com/Deo940712/threads-sync)(Threads
已存貼文 → Obsidian,已 vendored 為第一個 sync skill)。
