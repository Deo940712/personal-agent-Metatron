# CURRENT

Status: executing
Part: part-015（知識庫 CRUD + 三層下鑽 + INDEX 中文化）
Slice: part-015-slice-000（INDEX 中文化 + ltm.delete_note 原語）

Design authority: `.beacon/parts/part-015/DESIGN.md`
Slice map: `.beacon/parts/part-015/TODO.md`
Baseline: 899 tests green

## slice-000 scope（in progress）

- INDEX.md `_INDEX_TEMPLATE` 說明中文化（tag 保持英文）+ 既有 vault INDEX 遷移
- `ltm.delete_note(vault, note_id, idx_db)` 原語（三處刪 + 回 content_hash）；
  `tools/delete_note.py` 改呼叫它
- tests：INDEX 中文斷言、delete_note 三處刪 + 回 hash、既有 delete 工具仍過

## Context

part-014（MCP dev_plan + 儀表板常駐）完成歸檔（`.beacon/done/part-014/`）：
- dev_plan MCP 工具（第 11 工具）——讀 OpenCode session 的 plan/todo 進度；
  真機實測讀到 part-011 session 的 7/7 completed
- 儀表板設常駐（MyAgent-dashboard ONSTART，127.0.0.1:7777；內網反代對外）

## 環境就緒（全綠）

- ✅ LLM / Discord（對話式/recall/directive/knowledge_list）/ 知識庫 808 篇
- ✅ 排程 7 tasks（6 job + dashboard 常駐）
- ✅ MCP 11 工具（dev_status 三源 + dev_plan todo + schedule/task/directive…）
- ✅ 899 tests

## Next candidate (NOT promoted — awaits user gate)

- 對話層續調 / 儀表板加版塊（plan/todo、知識庫主題、facets）
- gate-locked backlog（rerank/decay/librarian/MiroFish/AgentSpec）觸發未到

## Blocked（等使用者環境）

- 無
