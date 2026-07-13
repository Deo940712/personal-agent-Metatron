# MY AGENT — 個人行程 + 知識庫助理

> 繁體中文 | [English](README-en.md)

一個**無狀態**的個人 AI 助理:管理行程與待辦、把社交平台(Threads / X / FB)存的
貼文整理進 Obsidian 知識庫、追蹤 vibe coding 專案進度。出門用 Discord 排事情、
收提醒推播;在家用 CLI 與 Obsidian。

**核心哲學:拋棄上下文。** 沒有長對話 session——agent 每次呼叫:讀資料庫 → 執行 →
寫回 → 結束。連續性不靠聊天記錄,靠結構化記憶。

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

**已規劃的記憶強化(part-004.5,依 2026 論文實證)**:主題連續性蒸餾(Membox:
同主題跨天串成事件 trace,不再按天碎片化)、矛盾偵測 + supersede 執行(Mneme:
新舊偏好雙側保留、檢索並列、引用前查 superseded_by)、RRF 跨段融合檢索(Cognis)。
待訂(觸發條件制):cross-encoder rerank(golden queries 出排名問題時)、
per-category 衰減速率(真實使用 1-2 月有數據時)。

## 所有 Agent 的職能

**拓撲:Orchestrator + 無狀態子 agent**(2026 年 LangGraph / Claude Agent SDK /
OpenAI Agents SDK 收斂的生產標準)。子 agent 拿 scoped 輸入、回結構化提案、即棄。

### 寫入鐵律:Agent 提議,程式驗證,單一 writer 落地

子 agent **永不直接寫資料庫**。所有寫入走 `writer.py`:七條驗證(target 存在、
tags 在受控詞彙表、evidence 屬實、enum 合法…)+ 三層危險閘門(物理刪除永不可能 /
寫入需使用者確認 / 唯讀自動放行)。確認逾時一律拒絕(fail-closed)。

### 子 agent 一覽

| 子 Agent | 職能 | 輸入 | 輸出 | 狀態 |
|---|---|---|---|---|
| **schedule** | 自然語言 → 行程/待辦提案(「明天下午兩點開會提前30分提醒」);rrule 重複行程 | 使用者原句 + 現有行程 | `schedule_change` / `task_change` 提案 | ✅ |
| **consolidator** | 夜間蒸餾:到期事件 → 日誌摘要(episodic)/ 使用者偏好(agent/profile);每個決策過欄位級驗證,不得虛構來源 | 到期 events 批次 | 蒸餾組(kind/title/summary/tags/source_ids/confidence) | ✅ |
| **curator** | 貼文評分(0-10 閘門)、分類、跨源去重、入 vault、建連結;中文 FIRE 拆卡 | inbox 筆記批次 | `classify_note` 提案 | 📋 part-004 |
| **librarian** | vault 圖書管理員:孤兒/斷鏈/重複/tag 蔓延/INDEX 漂移維護;兩階段(確定性掃描 + opt-in LLM 整理)、快照可回滾、永不刪除 | vault.scan 確定性報告 | `vault_maintenance` 提案(dry-run 先行) | 📋 part-004+ |
| **coding_tracker** | vibe coding 進度:三個唯讀訊號源(git log + `.beacon/CURRENT.md` 解析 + OpenCode sessions)→ 綜合每專案 phase/blockers/next | 專案路徑清單 | `project_update` 提案 | 📋 part-005 |
| **recall** | 知識庫問答:四段級聯檢索,回答必附引用,無來源不得斷言 | 查詢字串 | 帶引用的答案 | 📋 part-004 |
| sync-{threads,x,fb} | 平台抓取管線(**非 LLM**,純 CLI:Capture→State→Transform→Output,idempotent 可續傳) | cursor | new_count, status | 📋 part-004 |

子 agent 分兩型:**純函數型**(單次 LLM 呼叫、無工具、可重放測試——schedule/
consolidator/curator/librarian/coding_tracker)與**代理型**(唯讀工具白名單、
迭代檢索——僅 recall)。全系統唯一能寫的工具是 `writer.apply`。

## 介面

| 介面 | 場景 | 讀/寫 | 狀態 |
|---|---|---|---|
| **CLI** | 開發、排程 job | 讀+寫 | ✅ |
| **Obsidian** | 知識庫閱讀/編輯(vault 就是 UI) | 讀+寫 | ✅(零成本) |
| **Discord bot** | 出門:排事情(預覽→✅按鈕→落地)+ 提醒 DM 推播;私人 server 鎖 user id | 讀+寫(走 writer+確認) | ✅ 程式面 |
| 網頁儀表板 | 在家總覽 + 系統健康(127.0.0.1 唯讀) | 唯讀 | 📋 part-003.5 |
| MCP server | 在 OpenCode/Claude Code 內直接問助理 | 唯讀優先 | 📋 part-006 |

介面 = 薄 adapter,零業務邏輯,共用 `invoke(text, trigger, reply_to)`。
設計詳見 [INTERFACES.md](INTERFACES.md)。

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
| 記憶幻覺 | 溯源硬規則:每筆記必帶來源;recall 無來源不得斷言;可回水讀原文 |
| LLM 決策污染 | 每個蒸餾決策過欄位級驗證(不得虛構 source_ids);不合格跳過並記 log |
| 子 agent 亂寫 | 提案制 + 單一 writer + 危險閘門;確認逾時 fail-closed |
| 資料遺失 | 原文 append-only 永不刪;蒸餾失敗事件留在垃圾桶下輪重試;索引可重建 |
| 靜默壞掉 | `agent_runs` 記錄每次執行 status;頂層防線保證 run 不卡 running |

## 開發

```bash
python -m pytest tests/ -q     # 210 tests
```

工作流:[Beacon](.beacon/PLAN.md)(plan → design → slice → execute → verify →
**adversarial audit** → archive)。每個 slice 歸檔後跑實證稽核(探針腳本真執行
可疑路徑),發現全記錄在 [KNOWN_ISSUES.md](KNOWN_ISSUES.md) 並轉 regression test。

| 文件 | 內容 |
|---|---|
| [ARCHITECTURE.md](ARCHITECTURE.md) | 系統設計權威(schema、流程圖、設計依據) |
| [INTERFACES.md](INTERFACES.md) | 介面層設計(CLI/Discord/儀表板/MCP) |
| [docs/MEMORY-zh.md](docs/MEMORY-zh.md) | 記憶系統實作規格(API、不變量、故障恢復) |
| [KNOWN_ISSUES.md](KNOWN_ISSUES.md) | 稽核發現與修復記錄 |

## 進度

- ✅ part-001 基礎層(schema + CRUD CLI)
- ✅ part-002 Orchestrator + writer + schedule agent + remind
- ✅ part-002.5 Discord bot(兩階段確認 + DM 推播)
- ✅ part-003 記憶核心(冷儲存/代謝/蒸餾/四段檢索)
- 📋 part-004 sync skills(threads/x/fb → vault)+ curator + recall
- 📋 part-004.5 記憶強化(主題 trace / supersede / RRF)
- 📋 part-005 coding_tracker(git + beacon + opencode 三源)
- 📋 part-003.5 儀表板 / part-006 MCP server

前身專案:[threads-sync](https://github.com/Deo940712/threads-sync)(Threads
已存貼文 → Obsidian,本專案沿用其管線模式並將整合為第一個 sync skill)。
