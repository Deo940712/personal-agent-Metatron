# Metatron 系統架構導讀

> 本檔是一頁式入門導讀；細節權威仍為：
> - [ARCHITECTURE.md](../ARCHITECTURE.md) — 系統設計（schema、流程圖、設計依據）
> - [docs/MEMORY-zh.md](MEMORY-zh.md) — 記憶契約（API、不變量、故障恢復）
> - [docs/TOOLS.md](TOOLS.md) — 能力/agent/介面/權限/儲存配對矩陣
> - [INTERFACES.md](../INTERFACES.md) — 介面層設計

---

## 系統定位

Metatron 是一個**無狀態核心**的個人 AI 助理（行程 + 知識庫 + 專案追蹤）。
每則訊息建立獨立 run（read → act → validated write → die）；連續性靠四儲存層
的權威狀態與按需檢索，不靠重播整段對話。

---

## 架構圖

```
Channels (CLI / Discord / Dashboard / MCP)
    │  薄 adapter，零業務邏輯
    ▼
application.invoke()  ─── 統一入口（part-006）
    │
    ├─→ Router（意圖分類）
    │       │
    │       ▼
    │   Subagents（天使名冊，見下方）
    │       │ 結構化 Proposal
    │       ▼
    └─→ Writer commit boundary
            │  唯一寫入閘門：validate → confirm → commit
            ▼
    ┌────────────────────────────────────────────┐
    │              四儲存層                        │
    │  DB1 state.db │ Vault │ Transcript │ Index │
    └────────────────────────────────────────────┘
```

---

## 四儲存層

| 儲存 | 角色 | 可否重建 |
|---|---|---|
| **DB1** `state.db` (SQLite, 11 表) | 系統記錄（行程/待辦/專案/事件/pending/agent_runs/directives/profile_facets/advices/watchlist/cursors） | 不可由 index 取代 |
| **DB2** Obsidian vault (Markdown) | 人類知識介面；`semantic/`(Topic+Evidence)、`episodic/`、`agent/`(profile/ops/sop)、`scenarios/` | 人工內容可能唯一 |
| **冷儲存** transcript (JSONL + `.idx`) | 原始證據，append-only，永不刪除 | JSONL 是真相；`.idx` 可重建 |
| **向量索引** index.db (FTS5 + sqlite-vec) | 衍生物：隨時刪除 `vindex.rebuild` 重建 | 不保存唯一資料 |

---

## Agent 名冊（天使名 ↔ code identifier）

### 現役

| 天使 | 角色 | Code id | Job flag |
|---|---|---|---|
| **Metatron** | Orchestrator（本 repo 整體） | `core/agent.py` | — |
| **Sandalphon** | 行程/待辦解析 | `agents/schedule.md` | — |
| **Raziel** | 蒸餾（MEM 寫入側） | `agents/consolidator.md` | `--job consolidate` |
| **Jophiel** | Curator（入庫評分/分類） | `agents/curator.md` | `--job curate` |
| **Zerachiel** | Recall（MEM 讀取側） | `agents/recall.md` | — |
| **Uriel** | Coding tracker | `agents/coding_tracker.md` | `--job track` |
| **Cassiel** | 主動建議 Advisor | `agents/advisor.md` | `--job advise` |

### Backlog

| 天使 | 未來角色 | Backlog |
|---|---|---|
| **Anael** | Vault 維護（orphan/dedupe） | backlog-017 |

---

## 核心資料流

### 1. 寫入鏈（preview → confirm → writer）

```
使用者輸入 → LLM 子 agent → 結構化 Proposal
    → writer precheck（欄位級驗證）
    → 預覽呈現（Discord 按鈕 / CLI y/n / Dashboard confirm）
    → 使用者確認（逾時 = deny）
    → writer.apply → DB1/vault 落地 + events 記錄
```

### 2. 蒸餾鏈（decay → trash → distill → source_ids）

```
events(health=1.0)
    → 每日衰減 0.05（~20 天歸零）
    → health=0 → to_trash（原文先 flush 進 transcript）
    → 14 天 trash 保留期（命中可復活）
    → due_for_distill → 按日分組(≤50) → LLM 蒸餾
    → 欄位級驗證 → vault note（必帶 source_ids）
    → mark_archived → vindex.upsert（FTS）
```

### 3. 檢索鏈（兩段現行 + dormant + rehydrate）

```
查詢 → 強 index 命中短路（≥2 token 命中 = 直接回傳）
    → 否則：INDEX registry + FTS5 trigram → RRF 融合(k=60)
    → [dormant: sqlite-vec KNN — production 未接線]
    → top-k 候選 → 開筆記（superseded_by 提示）
    → 精度不足 → rehydrate：沿 source_ids 讀原文
    → 命中觸發 health.on_hit 回血
```

### 4. 提醒鏈（確定性，不經 LLM）

```
Task Scheduler（每 15 分） → agent --job remind
    → SELECT remind_at <= now() AND reminded_at IS NULL
    → Discord DM 推播
    → 單次：標 reminded_at；重複：rrule 展開下次
```

---

## Part 時間線（001 → 019）

| Part | 重點 | 狀態 |
|---|---|---|
| 001 | Schema + CRUD CLI | ✅ |
| 002 | Orchestrator + writer + schedule agent + remind | ✅ |
| 002.5 | Discord bot（兩階段確認 + DM push） | ✅ |
| 003 | 記憶核心（冷儲存 / 代謝 / 蒸餾 / 檢索） | ✅ |
| 003.1 | 雙語記憶契約 MEM-01..17 | ✅ |
| 003.2 | Task Capsule A/B 實驗（verdict: retain_a） | ✅ |
| 003.5 | 儀表板（stdlib http.server） | ✅ |
| 004 | Sync skills（threads runner + curator + recall） | ✅ |
| 004.5 | 記憶強化（topic trace / supersede / RRF） | ✅ |
| 005 | coding_tracker（三源） | ✅ |
| 006 | MCP server（capability tools / stdio / HTTP） | ✅ |
| 007 | Personal Model（profile_facets） | ✅ |
| 008 | Knowledge Scout（allowlist + fetch） | ✅ |
| 009 | Proactive Advisor（world-diff + advice） | ✅ |
| 010 | Scenario Rehearsal（crowd-scenario vendored） | ✅ |
| 011 | 收尾接線（routine 迴圈 / 校準 / golden queries） | ✅ |
| 012 | Router（LLM-first 意圖分類） | ✅ |
| 013 | 對話層新增 directive + knowledge_list 意圖 | ✅ |
| 014 | MCP dev_plan（第 11 工具）+ 儀表板 ONSTART 常駐 | ✅ |
| 015 | 知識庫 CRUD + 三層下鑽 + INDEX 中文化 | ✅ |
| 016 | 能力速查 + 互動儀表板受限操作（done/confirm） | ✅ |
| 017 | LLM transient model failover hotfix | ✅ |
| 018 | KB 2.0 Topic/Evidence + migration | ✅ |
| 019 | Evidence 批次 Topic 化 | 🚧 slice-001 executable；閘門 A 已通過，閘門 B 待確認 |

完整設計與 gate 條件見 [`.beacon/PLAN.md`](../.beacon/PLAN.md)。

---

## 現況狀態（2026-07-31）

- **961 tests green**（`python -m pytest tests/ -q`）
- **活躍**：part-019 slice-001 executable；閘門 A 已通過，Pilot 分群提案（原 786 筆，Pilot 49 筆：46 筆連結、3 筆保留，剩餘 737 筆）停在閘門 B，等待使用者確認
- **未來方向**：part-020 系統可靠性（錯誤恢復、重試機制、狀態一致性） → part-021 常駐 Supervisor 與 Watchdog 守護行程
- **已知限制**：
  - 向量 KNN 段 dormant（程式存在、production 未接線）
  - W1/W2 dashboard 安全問題 open（KNOWN_ISSUES.md 已記錄）
  - retrieve 查詢期 vault I/O（backlog-034）
- **環境待確認**：VPS + Tailscale 真機 QA（backlog-008）
