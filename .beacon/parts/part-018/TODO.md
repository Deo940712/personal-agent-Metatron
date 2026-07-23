# part-018 TODO — Knowledge Base 2.0: Topic/Evidence 雙層架構

> Status: ready
> DESIGN: `.beacon/parts/part-018/DESIGN.md`
> Parent: ARCHITECTURE.md §4

## Slices

### slice-001: Schema 定義與 Migration Script
**Goal**: 建立 `note_type` schema 與 deterministic migration script，可將現有 807 篇筆記標記為 evidence，並建立 5 篇 topic notes 的 seed 檔案。

**Files**:
- `scripts/migrate_kb_2_0.py` (new)
- `core/ltm.py` (extend frontmatter schema)
- `tests/test_migrate_kb_2_0.py` (new)

**Verification**:
- `python scripts/migrate_kb_2_0.py --dry-run` 輸出預覽無誤
- `python -m pytest tests/test_migrate_kb_2_0.py -v` 通過
- 943 existing tests 仍通過

**Acceptance**:
- [ ] `note_type` 欄位定義明確（topic/evidence）
- [ ] Migration script 可標記 807 篇為 evidence（不更動檔案路徑）
- [ ] 5 篇 topic notes 建立於 `semantic/topic/` 且 frontmatter 正確
- [ ] Rollback 機制（backup）可運作

---

### slice-002: 檢索邏輯降級（Zerachiel/Retrieve）
**Goal**: 修改檢索邏輯，預設只搜尋 topic notes，evidence 降級為佐證連結。

**Files**:
- `core/retrieve.py` (modify)
- `core/vindex.py` (modify rebuild/upsert to filter note_type)
- `core/tools/memory.py` (add include_evidence flag)
- `tests/test_retrieve_topic_first.py` (new)

**Verification**:
- `python -m pytest tests/test_retrieve_topic_first.py -v` 通過
- 手動驗證：搜尋「AI 開源工具」只回傳 topic note，不回傳 9 篇原始貼文
- 943 existing tests 仍通過

**Acceptance**:
- [ ] `vindex.rebuild()` 預設排除 evidence
- [ ] `retrieve.py` 預設只回傳 topic notes
- [ ] `include_evidence=True` 時可搜尋原始貼文（向後相容）
- [ ] Topic note 的 `source_evidence` 連結可正確讀取原始貼文內容

---

### slice-003: 5 組整理實作（Seed Migration）
**Goal**: 使用新架構完成 21 篇原始貼文的整理，建立 5 篇 topic notes。

**Files**:
- `vault/semantic/topic/ai-agent-open-source-tools.md` (new)
- `vault/semantic/topic/claude-code-cost-optimization.md` (new)
- `vault/semantic/topic/fable-5-system-prompt-analysis.md` (new)
- `vault/semantic/topic/karpathy-claude-md-workflow.md` (new)
- `vault/semantic/topic/obsidian-as-ai-knowledge-base.md` (new)
- 21 篇既有 evidence notes 的 frontmatter 更新

**Verification**:
- 人工檢查 5 篇 topic notes 內容正確涵蓋 21 篇原始貼文的重點
- `INDEX.md` 正確顯示 5 篇 topic 為主索引
- 943 tests 通過

**Acceptance**:
- [ ] 5 篇 topic notes 建立，內容為精煉後知識（非單純複製貼文）
- [ ] 21 篇 evidence 標記 `consolidated_into` 正確
- [ ] 用戶確認 topic notes 品質可接受

---

### slice-004: INDEX.md 雙層化與文件更新
**Goal**: 更新 INDEX.md 格式，明確區分 Topic（主索引）與 Evidence（附錄），並更新相關文件。

**Files**:
- `vault/INDEX.md` (modify structure)
- `docs/MEMORY-zh.md` (update retrieval logic)
- `docs/USER-GUIDE-zh.md` (add KB 2.0 usage)

**Verification**:
- INDEX.md 自動生成腳本（若有）或手動更新後格式正確
- 文件無矛盾

**Acceptance**:
- [ ] INDEX.md 區分「主題筆記」與「原始素材」兩個章節
- [ ] MEMORY-zh.md 記載新的檢索優先級
- [ ] USER-GUIDE 說明如何區分 topic 與 evidence

---

## Dependencies

- slice-001 → slice-002（schema 先建立，才能改檢索）
- slice-001 → slice-003（migration script 先建立，才能執行整理）
- slice-002 → slice-003（檢索邏輯先正確，才能驗證整理結果）
- slice-003 → slice-004（實作完成後更新文件）

## Open Questions

- Q: Evidence notes 是否應該從 `semantic/` 移到 `semantic/evidence/`？
  A: 暫時不動（避免 807 次檔案移動），僅用 metadata 標記。未來新匯入的貼文直接進 `evidence/`。

- Q: 如何處理「部分整理」的狀態（例如 21 篇中只有 15 篇被整理）？
  A: `evidence_status: raw` vs `linked`。raw = 未整理；linked = 已連結到 topic。

- Q: 那 786 篇未合併的筆記怎麼辦？
  A: 全部標記為 `note_type: evidence`, `evidence_status: raw`。等待 part-020 Anael 主動整理提議。
