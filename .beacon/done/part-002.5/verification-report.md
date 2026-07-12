# part-002.5 Verification Report

Completed: 2026-07-13(程式面;真 Discord QA blocked)
Slices: 3/3 程式面完成(pending+precheck / chat 兩階段 / discord adapter)

## Final verification

- `python -m pytest tests/ -q` → **210 passed**
- 各 slice audit gate 已跑(KNOWN_ISSUES 記錄):
  - slice-001:A2'/A3' DESIGN 缺陷(非同步第二階段缺重驗)→ confirm_and_apply
  - slice-002:C7(空訊息落 LLM)
  - slice-003:D2(custom_id 編解碼對稱)

## 交付

- `core/stm.py`:pending_proposals(第七表)+ CRUD + expire
- `core/writer.py`:precheck(驗證不落地)+ confirm_and_apply(第二階段重驗)
- `core/chat.py`:平台無關兩階段邏輯(前綴分派、確認流、內容分級、無狀態重啟)
- `channels/discord_bot.py`:薄 adapter(白名單 fail-closed、custom_id 編解碼、
  按鈕 View、DM 推播、discord.py 延遲 import)
- `core/agent.py` job_remind:notify_fn 可注入 + 順掃 pending expire
- pyproject:discord.py optional 依賴

## Phase 2.5 Gate

| 條件 | 結果 |
|---|---|
| 手機發排程 → 預覽 → ✅ → DB1 有列 | ⏳ blocked(真 Discord;純函式與兩階段邏輯已 210 tests 驗證) |
| 提醒 DM 收得到 | ⏳ blocked(send_dm 已實作;需真 token) |

## Manual QA(blocked — 需使用者環境動作)

1. `pip install "my-agent[discord]"`(或 `pip install discord.py`)
2. Discord Developer Portal 建 application + bot,取 bot token
3. 開私人 server,邀 bot 進來;開啟 Message Content Intent
4. 抓自己的 Discord user id(開發者模式 → 右鍵頭像 → 複製 ID)
5. 設環境變數:
   - `MY_AGENT_DISCORD_TOKEN` = bot token
   - `MY_AGENT_DISCORD_ALLOWED_USER_ID` = 你的 user id
   - (+ 之前的 `MY_AGENT_LLM_API_KEY`)
6. `python -m channels.discord_bot` 啟動;手機 DM bot「明天下午兩點開會」
   → 收預覽卡 → 按 ✅ → `python -m core.stm schedule list` 確認
7. 排程器每 N 分鐘跑 `python -m core.agent --job remind`(notify 接 DM)

## 移交

- 真 Discord QA 待上述環境;程式面無 blocker
- 累積待 QA:真 LLM(part-002/003)+ 真 embedding(part-003)+ 真 Discord(本 part)
  —— 建議設好 API key 後一次補齊
