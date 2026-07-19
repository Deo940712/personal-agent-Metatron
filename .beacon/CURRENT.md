# CURRENT

Status: planning-only
Part: (none active)
Slice: (none promoted)

## Context

part-013（對話層補兩個意圖）完成並歸檔（`.beacon/done/part-013/`）：router 加
directive + knowledge_list 兩 intent（895 tests）。真機兩缺口已修：
- Discord 現在能「留個指令:修 X」→ 入開發指令佇列（下次 session 讀到）
- 「我知識庫有什麼」→ 列 tag 分布 + 最近幾篇（真庫 808 篇 0.15s，不再只回一則）

## 環境就緒（全綠）

- ✅ LLM / Discord（指令/確認/DM/對話式路由/recall/directive/knowledge_list）
- ✅ 知識庫 808 篇（threads 已匯入,recall + 列表都有料）
- ✅ 排程 6 jobs / Tailscale MCP / OpenCode MCP（dev_status 三源實測通）

## Next candidate (NOT promoted — awaits user gate)

- 對話層續調：directive「留給 X 專案:...」語法；smalltalk 帶 facets 個人化
- gate-locked backlog（rerank/decay/librarian/MiroFish/AgentSpec）觸發條件未到

## Blocked（等使用者環境）

- 無（VPS 已用內網反代/Tailscale 取代）
