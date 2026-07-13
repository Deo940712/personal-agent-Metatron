# CURRENT

Part: part-004
Slice: slice-002
Status: active
Design authority: `.beacon/parts/part-004/DESIGN.md`
TODO source: `.beacon/parts/part-004/TODO.md#part-004-slice-002-curator前處理--llm-契約--管線`

## Goal

inbox 筆記 → 確定性前處理（hash/去重/欄位補齊）→ LLM 評分+分類 → writer 驗證
→ 正式入庫（registry + vindex）；低分只留 metadata。

## Allowed Scope

- [ ] `core/curator_pre.py`：inbox 掃描、content_hash、跨源去重、§5.2 欄位補齊
- [ ] `agents/curator.md`：評分+分類契約（閾值 4.0、配額、evidence 規則）
- [ ] `core/curate.py`：pre → LLM 批次（≤10 篇）→ 驗證 → 落地 → 統計
- [ ] writer：classify_note 落地（frontmatter 更新 + manual_tags 守衛 + registry + vindex）
- [ ] INDEX 詞彙表擴充（threads-sync 14 類 + low-score）
- [ ] `core/agent.py` 加 `--job curate`
- [ ] pytest（mock LLM）：閘門/配額/去重/manual_tags/驗證攔截 + boundary

## Forbidden Scope

- FIRE 拆卡完整版（backlog-019；先 summary+tags 起步）
- recall（slice-003）

## Files-scope

core/curator_pre.py, core/curate.py, core/writer.py, core/proposals.py, agents/curator.md, core/agent.py, core/ltm.py, tests/test_curate.py

## Expected Output

假貼文丟 inbox → `--job curate` → 高分入 registry 可檢索、低分標 low-score；
重複貼文合併；手動 tag 不被覆蓋。

## Verification Plan

- Unit: `python -m pytest tests/test_curate.py -q`
- Regression: `python -m pytest tests/ -q`（223 不壞）
- Manual QA: 假貼文 3 篇（高/低分/重複）端到端目檢

## Current Blockers

None

## Recovery Incident

None
