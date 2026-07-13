# CURRENT

Status: planning-only

part-004 完成並歸檔（.beacon/done/part-004/，Phase 4 gate mock 端到端通過）。
完整知識鏈就位：threads-sync → runner → inbox → curator（去重/評分/入庫）
→ INDEX/vindex → recall（帶引用問答，引用驗證程式面保障）。

## 待使用者動作（累積四批真 QA）

1. `MY_AGENT_LLM_API_KEY`（+ 選配 BASE_URL）→ 真 LLM/embedding QA
2. Discord token + user id → 真 Discord QA
3. threads-sync Playwright session（原機器 cookies）→ 真同步 QA

## 下一步選項（PART 完成 = 自然暫停點）

- **part-004.5 記憶強化**：Membox 主題 trace / Mneme supersede / RRF（真資料前的最後強化）
- **part-006 slice-1 stdio MCP**：遠端開發迴圈（dev_status/directive 佇列）——可插隊
- part-003.5 唯讀儀表板 / part-005 coding_tracker

在 DESIGN 建立並 promote SLICE 前，無可執行 SLICE。
