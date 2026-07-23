# part-018: Knowledge Base 2.0 — Topic/Evidence 雙層架構

> Status: design
> Created: 2026-07-21
> Parent: ARCHITECTURE.md §4 (Memory Model), docs/MEMORY-zh.md

## 1. 問題陳述 (Problem Statement)

KB 1.0 的核心設計缺陷：**假設「一篇 Threads 貼文 = 一篇知識筆記」**。這導致：

- **資料孤島化**：807 篇筆記各自獨立，同質內容（如 9 篇「AI 開源工具學習」）無法聚合
- **分類僵化**：硬編碼英文標籤（`ai-agents`, `dev-frontend`...）無法描述多維度知識，misc 累積 59 篇
- **檢索噪音**：Zerachiel 回傳單篇貼文，而非整理後的主題知識；原始貼文與精煉知識混雜
- **無演化機制**：知識庫只會累積，不會消化；沒有主動整理（Anael）的落腳點

## 2. 設計目標 (Goals)

1. **雙層資料結構**：區分「精煉知識」（Topic Notes）與「原始證據」（Evidence Notes）
2. **檢索降級**：預設只搜尋 Topic Notes；Evidence Notes 僅作為來源佐證，不進主索引
3. **無損遷移**：現有 807 篇筆記不刪除、不移動，透過 metadata 標記降級
4. **可累積知識**：Topic Notes 支援「持續更新」（append-only log of insights），而非一次性寫死
5. **為 Anael 鋪路**：建立 Evidence 的「待整理」狀態，讓 Librarian 可以主動提議合併

## 3. 非目標 (Non-Goals)

- **不物理刪除任何筆記**：原始貼文保留在 `semantic/` 或 `semantic/evidence/`，永不刪除
- **不修改現有 807 篇的檔案路徑**：避免破壞現有連結與 INDEX；透過 frontmatter 標記新狀態
- **不實作動態分類系統**（part-019）：本 part 先解決 Topic/Evidence 分層，分類法仍用現有標籤
- **不實作 GUI 編輯器**（part-021）：合併流程先透過 CLI/Discord 確認，不碰 Dashboard

## 4. 架構設計 (Architecture)

### 4.1 目錄結構

```
vault/
  semantic/
    topic/           # 新增：精煉主題筆記（KB 2.0 主要入口）
      ai-agent-workflow.md
      claude-code-cost-optimization.md
      ...
    evidence/        # 新增：原始貼文降級存放（可選，或保留原位僅標記）
      ...
    20260614-ai-開源工具學習.md   # 既有：保留原位，但標記為 evidence
    ...
```

**決策**：為了避免 807 次檔案移動，**不遷移現有檔案**。改為：
- 現有 `semantic/*.md` 在 frontmatter 加入 `note_type: evidence`（預設遷移時批次標記）
- 新建立的整理筆記放入 `semantic/topic/*.md`，標記 `note_type: topic`
- `semantic/evidence/` 目錄預留給未來「新匯入的原始貼文」直接落地

### 4.2 Frontmatter Schema 擴充

**Evidence Note（原始貼文）**:
```yaml
---
id: 20260614-ai-開源工具學習
title: AI 開源工具學習
note_type: evidence           # 新增：標記為原始證據
evidence_status: raw          # raw | linked | archived
consolidated_into: []         # list of topic note ids，反向連結
source: threads
url: "..."
# ... 其餘既有欄位保留
---
```

**Topic Note（主題筆記）**:
```yaml
---
id: ai-agent-workflow-tools-202607
title: AI Agent 工作流工具目錄
note_type: topic              # 新增：標記為主題筆記
topic_status: active          # active | stale | merged
source_evidence:              # 新增：正向連結到原始證據
  - 20260614-ai-開源工具學習
  - 20260615-ai-開源工具學習
  - ...
last_consolidated: "2026-07-21"
consolidation_version: 1      # 每次合併新 evidence 時 +1
tags: [ai-agents, automation]  # 繼承並精煉自 evidence
summary: 精煉後的知識摘要...
---
```

### 4.3 檢索邏輯變更 (Zerachiel/Retrieve)

**現況**：`core/retrieve.py` 掃描 `semantic/*.md`（全部混合）

**新邏輯**：
1. **第一層**：只搜尋 `semantic/topic/*.md`（note_type == "topic"）
2. **第二層**：若 topic 命中，透過 `source_evidence` 連結讀取原始貼文內容作為佐證，但不獨立顯示 evidence 為搜尋結果
3. **強制過濾**：`vindex.rebuild()` 與 `ltm.registry_entries()` 預設排除 `note_type: evidence` 的筆記，除非明確指定 `include_evidence=True`

### 4.4 遷移流程（針對現有 807 篇）

**Deterministic Migration Script** (`scripts/migrate_kb_2_0.py`):
1. 掃描 `semantic/*.md`（不進子目錄）
2. 若 frontmatter 無 `note_type`，加入 `note_type: evidence`, `evidence_status: raw`
3. 若為那 21 篇待合併的貼文，同時加入 `consolidated_into: [對應 topic id]`
4. 更新 `INDEX.md`：只保留 topic notes 進入 registry；evidence 移入附錄或標記為 hidden
5. 重建 `index.db`：只索引 topic notes

**Rollback**：migration script 必須產生 backup（git commit 或 `.backup/`），允許還原 frontmatter 變更。

## 5. 那 5 組整理的標準流程（Seed Migration）

作為 part-018 的第一個實作案例，21 篇原始貼文將依以下流程處理：

1. **建立 Topic Notes**（5 篇新檔案，放 `semantic/topic/`）：
   - `ai-agent-open-source-tools.md`（目錄型：9 篇工具介紹）
   - `claude-code-cost-optimization.md`（程序型：3 篇 token 節省技巧）
   - `fable-5-system-prompt-analysis.md`（事件型：3 篇 prompt 外洩分析）
   - `karpathy-claude-md-workflow.md`（原則型：2 篇工程守則）
   - `obsidian-as-ai-knowledge-base.md`（比較型：4 篇知識庫設計）

2. **標記 Evidence**（21 篇既有檔案）：
   - 加入 `note_type: evidence`, `consolidated_into: [對應 topic id]`

3. **更新 INDEX**：5 篇 topic 進入 registry；21 篇 evidence 保留檔案但從主索引降級

4. **重建檢索**：`vindex.rebuild()` 只索引 5 篇 topic（以及之後的其他 topic）

## 6. 驗證標準 (Definition of Done)

- [ ] Migration script 可執行且可 rollback（有測試覆蓋）
- [ ] 5 篇 Topic Notes 建立完成，frontmatter 符合 schema
- [ ] 21 篇 Evidence Notes 標記完成，`consolidated_into` 正確
- [ ] `INDEX.md` 正確區分 topic/evidence（topic 可見，evidence 降級）
- [ ] `vindex.rebuild()` 只索引 topic notes；搜尋「AI 開源工具」只回傳 topic note，不回傳 9 篇原始貼文
- [ ] 既有 786 篇未合併筆記不受影響（仍標記為 evidence，但可透過 `include_evidence=True` 搜尋）
- [ ] 943 tests 全數通過（含新增的 schema 驗證測試）

## 7. 風險與緩解 (Risks)

| 風險 | 緩解 |
|------|------|
| 遷移腳本錯誤導致 807 篇 metadata 毀損 | 先跑 `--dry-run`；git commit 前置；backup 原始 frontmatter |
| 檢索遺漏（用戶找不到未合併的舊筆記） | 提供 `--include-evidence` flag；INDEX 保留附錄章節 |
| 雙層結構過度複雜，用戶混淆 | 明確文件說明「topic = 知識，evidence = 素材」；預設行為簡單（只搜 topic） |

## 8. 後續 Parts

- **part-019**: 動態分類系統（廢除硬編碼標籤，支援階層 taxonomy）
- **part-020**: Anael 主動整理（偵測同質 evidence，提議建立新 topic）
- **part-021**: 知識編輯介面（Dashboard 支援拖拉合併、預覽差異）
