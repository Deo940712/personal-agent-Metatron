# CURRENT

Status: planning-only
Part: (none active)
Slice: (none promoted)

## Context

part-012（對話式 orchestrator，backlog-033）全兩 slice 完成並歸檔至
`.beacon/done/part-012/`：
- slice-000：router 意圖分類器（七 intent，欄位級驗證，LLM 失敗 fallback；886 tests）
- slice-001：router 接線 chat + schedule_query 時間窗 + Discord 開 recall + unclear
  友善追問；附帶修 recall 空回應 bug（gpt-5.5 content=null → gemini fallback）

**「感覺是固定程序」的體感問題已解決**：Discord 現在聽得懂「明天有什麼」「我存過
哪些 X」「最近怎樣」「哈囉」，聽不懂會友善追問——但寫入鐵律完全不變
（提案→writer→確認）。真機 QA 五句全通。

## 環境就緒狀態

- ✅ LLM（gpt-5.5 內網 proxy + gemini fallback）
- ✅ Discord bot（指令/兩階段確認/DM 推播/對話式路由/recall）
- ✅ 排程 6 jobs 自主運行
- ✅ Tailscale MCP 遠端（實測綁 100.89.45.93 通、綁 0.0.0.0 拒）
- ⬜ 知識庫目前空——threads 同步或 watchlist 抓過才有料
- ⬜ threads 真同步 QA（session 存在，未跑）

## Next candidate (NOT promoted — awaits user gate)

- threads 真同步（跑一次 skills/runner 把已存貼文灌進知識庫，recall 才有料）
- 對話層調校：schedule_write 也可考慮走 range 感知；smalltalk 帶 facets 個人化
- gate-locked backlog（rerank/decay/librarian/MiroFish/AgentSpec）觸發條件未到

## Blocked（等使用者環境）

- threads session 真同步實跑
- VPS（已用內網反代/Tailscale 取代，不需要）
