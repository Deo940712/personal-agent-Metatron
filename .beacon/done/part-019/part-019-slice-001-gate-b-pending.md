# CURRENT

Status: executable ─ .omo plan approved (authorizes preparation only, NOT Gate B) — Gate A passed; drafting for Gate B
Active part: part-019 Evidence 全面整理（批次 Topic 化）
Active slice: slice-001 Pilot 整理（30–50 篇，端到端含兩道使用者閘門）
Design: `.beacon/parts/part-019/DESIGN.md`

## Completed

- part-018 KB 2.0 全數封存（`.beacon/done/part-018/`，961 tests 綠、真實探針全通過、使用者確認五篇 seed Topic Notes 品質）

## Scope (slice-001)

用 30–50 篇未整理 Evidence 跑完批次流程全流程並校準：

1. 掃描全部未整理 evidence（`note_type: evidence` 且無 `consolidated_into`）的 metadata 到暫存 JSON（TEMP，不入 repo）。
2. 產分群提案（群名/IDs/理由/類型）→ **閘門 A：已於 2026-07-25 取得使用者確認**。
3. 逐群讀全文產繁中 Topic Note 草稿（對齊 seed 五篇格式與語氣）→ **閘門 B：等待使用者確認草稿**（自然暫停）。
4. 寫 `scripts/consolidate_kb_batch.py`（idempotent + dry-run + backup + rollback）+ 測試，落地：Topic Notes、evidence `consolidated_into`、INDEX、重建索引。
5. 驗證六項（schema/連結/backup 比對/索引/topic-first 搜尋/pytest 全綠），記錄 pilot 校準結論。

## Verification

- 掃描同條件重跑同結果；分群提案檔案留存
- 新 Topic Notes schema 合格、source_evidence 與確認分群一致
- 入選 Evidence 反向連結正確、body/metadata 無損（backup 比對）
- `index.db` = 5 + 新增 topic 數；topic-first 搜尋命中新 topic
- `python -m pytest tests/ -q` 全綠

## Files allowed

- `.beacon/CURRENT.md`
- `.beacon/PLAN.md`（僅限修復重複 PART 與同步本 slice 狀態）
- `.beacon/parts/part-019/DESIGN.md`
- `.beacon/parts/part-019/TODO.md`
- `.beacon/parts/part-019/cluster-proposal-pilot.md` (new)
- `.beacon/parts/part-019/topic-drafts-pilot.md` (new；僅草稿審核包，不是正式 vault Topic Note)
- `ARCHITECTURE.md`（僅限同步 PART 時間線）
- `docs/OVERVIEW-zh.md`（僅限同步 PART 時間線與現況）
- `README.md`、`README-en.md`、`AGENTS.md`（僅限同步 part-019 現況）
- `scripts/consolidate_kb_batch.py` (new)
- `tests/test_consolidate_kb_batch.py` (new)
- 新 Topic Notes `vault/semantic/topic/*.md`（閘門 B 後才建立）
- 入選 Evidence 的 frontmatter 更新（閘門 B 後；落地前 `.backup/` 快照）
- `vault/INDEX.md`
- `KNOWN_ISSUES.md`

本次文件校正只消除既有 Beacon／架構文件矛盾，不擴張 slice 功能；閘門 A、B 與
vault 寫入限制維持不變。

## Done gate

- 閘門 A（分群）與閘門 B（草稿）皆取得使用者明確確認
- 落地驗證六項全過；孤立筆記有明示保留原因
- pilot 校準結論（群大小/文風/拆併規則）寫回 part-019 TODO
- 未經閘門 B 不得寫入任何 Topic Note 或修改 Evidence
