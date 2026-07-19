# CURRENT

Status: part-015 三 slice 全綠,待歸檔 / 重啟 Discord bot 載入新意圖
Part: part-015（知識庫 CRUD + 三層下鑽 + INDEX 中文化）
Slice: all done

Design authority: `.beacon/parts/part-015/DESIGN.md`
Slice map: `.beacon/parts/part-015/TODO.md`
Baseline: 926 tests green（899 → +3 +5 +19 = +27）

## 進度

- ✅ slice-000：INDEX 中文化 + `ltm.delete_note` 原語（生產 vault 已遷移,807
  registry 保留）
- ✅ slice-001：三層下鑽（`browse_topic`/`open_note` + `vindex.notes_by_tag`
  + 快徑「看 <tag>」「看筆記 <id>」零 LLM）
- ✅ slice-002：CRUD note_write proposal + writer 三 action + note 能力層 +
  router note_create/edit/delete + 快徑「新增筆記/改筆記/刪筆記」,全走確認;
  端到端 smoke 通過（create→browse→open→edit→delete→黑名單）

## Next

- 重啟 Discord bot 載入 3 新意圖 + 快徑（kill python.exe *discord_bot* → 重啟）
- 歸檔 part-015 → `.beacon/done/part-015/`

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
