# CURRENT

Status: planning-only

part-002.5 程式面完成並歸檔（.beacon/done/part-002.5/）。
Discord bot 兩階段確認 + 提醒 DM + 白名單全部就位；210 tests 綠。

## 待使用者動作（累積中）

真 QA 三批（建議設好 API key 一次補齊）：
1. 真 LLM（part-002/003）：`MY_AGENT_LLM_API_KEY`
2. 真 embedding（part-003）：同上或 `MY_AGENT_EMBED_BASE_URL`
3. 真 Discord（part-002.5）：`pip install discord.py` + bot token + user id
   （步驟見 .beacon/done/part-002.5/verification-report.md）

## 下一步選項（PART 完成 = 自然暫停點）

- **part-004 sync skills**：threads-sync 遷入 → curator（FIRE 拆卡 backlog-019）
  → x_sync；知識庫開始進真資料（recall 子 agent 契約也在此）
- part-003.5 唯讀儀表板（INTERFACES §5）

在 DESIGN 建立並 promote SLICE 前，無可執行 SLICE。
