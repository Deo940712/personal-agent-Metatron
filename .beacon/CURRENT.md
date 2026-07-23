# CURRENT

Status: executable
Active part: part-018 Knowledge Base 2.0
Active slice: slice-003 5 組整理實作（Seed Migration）
Design: `.beacon/parts/part-018/DESIGN.md`

## Completed

- slice-001: KB 2.0 migration script（`scripts/migrate_kb_2_0.py`）+ 8 tests
  - Dry-run 驗證：807 evidence notes, 5 topic notes
  - 處理 malformed YAML frontmatter
  - Rollback 機制可運作
  - 951 tests 通過

- slice-002: KB 2.0 topic-first retrieval
  - retrieve.py: `include_evidence` flag（預設 False 只搜尋 topic）
  - recall.py: 傳遞 `include_evidence` 到工具層
  - memory.py: 偵測「搜原文」或「include evidence」啟用 evidence 搜尋
  - 7 tests for topic/evidence filtering
  - 958 tests 通過

## Scope (slice-003)

使用新架構完成 21 篇原始貼文的整理，建立 5 篇 topic notes。

## Verification

- 人工檢查 5 篇 topic notes 內容正確涵蓋 21 篇原始貼文的重點
- `INDEX.md` 正確顯示 5 篇 topic 為主索引
- 958 tests 通過

## Files allowed

- `vault/semantic/topic/ai-agent-open-source-tools.md` (new)
- `vault/semantic/topic/claude-code-cost-optimization.md` (new)
- `vault/semantic/topic/fable-5-system-prompt-analysis.md` (new)
- `vault/semantic/topic/karpathy-claude-md-workflow.md` (new)
- `vault/semantic/topic/obsidian-as-ai-knowledge-base.md` (new)
- 21 篇既有 evidence notes 的 frontmatter 更新

## Done gate

5 篇 topic notes 建立，內容為精煉後知識；21 篇 evidence 標記 `consolidated_into` 正確；用戶確認 topic notes 品質可接受。
