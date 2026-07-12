# part-002.5 TODO

Design authority: `.beacon/parts/part-002.5/DESIGN.md`

## SLICE Map

### part-002.5-slice-001: pending_proposals + writer.precheck

Status: done (2026-07-13)

Goal: DB1 待確認提案持久化 + writer 驗證/落地拆分(兩階段基座)。

Outcome: precheck 驗證不落地;pending 存 DB1 可跨實例取回;apply 對 CLI 行為不變。

Candidate scope:
- [ ] `core/stm.py`:pending_proposals 表(第七張)+ DDL + pending CRUD + expire
- [ ] `core/writer.py`:precheck(proposal, db)(驗證不落地);apply 重構相容
- [ ] pytest:precheck 各攔截路徑 + 不落地驗證;pending CRUD roundtrip + expire
- [ ] regression:162 既有全綠(apply 行為不變)

Files-scope: core/stm.py, core/writer.py, tests/test_pending.py, tests/test_writer.py

Forbidden scope:
- discord.py / chat.py(slice-002)

Verification target:
- Unit: `python -m pytest tests/test_pending.py tests/test_writer.py -q`
- Regression: `python -m pytest tests/ -q`（162 不壞）
- Manual QA: 無

Done gate:
- precheck 不落地;pending 跨實例取回;全 pytest 綠

### part-002.5-slice-002: chat.py 兩階段邏輯（平台無關）

Status: done (2026-07-13)

Goal: 平台無關的訊息處理 + 非同步確認,零 discord 依賴。

Outcome: mock LLM 下,handle_message → pending → confirm(approve/reject) 全流程;
bot「重啟」模擬(新實例)仍能 confirm。

Candidate scope:
- [ ] `core/chat.py`:handle_message(前綴分派 + 自然語言→schedule)、confirm(pending_id, approve)
- [ ] 免確認路徑(today/week/proj/done/查詢)直接回
- [ ] 深度知識查詢拒絕（§4.1 內容分級）
- [ ] pytest（mock LLM，零 discord）：兩階段、無狀態重啟、免確認、拒絕、expire

Files-scope: core/chat.py, tests/test_chat.py

Forbidden scope:
- discord.py 實際連線（slice-003）

Verification target:
- Unit: `python -m pytest tests/test_chat.py -q`
- Regression: 全綠
- Manual QA: 無（純邏輯）

Done gate:
- 兩階段 + 無狀態重啟測試綠

### part-002.5-slice-003: discord_bot.py 薄 adapter + 提醒 DM

Status: done (2026-07-13; 真連線 QA blocked — 等使用者 Discord 環境)

Goal: discord.py 事件橋接 chat.py + 按鈕 View + 提醒 DM;鎖 user id。

Outcome: 真 Discord 手動 QA——手機排程收預覽卡 → ✅ → 落地;提醒收 DM。

Candidate scope:
- [ ] `channels/discord_bot.py`:on_message → chat.handle_message、Button View → chat.confirm
- [ ] user id 白名單（fail-closed）、custom_id 解析、失效按鈕優雅回應
- [ ] `agent.job_remind` notify_fn 可注入 Discord DM + 順掃 pending expire
- [ ] config：DISCORD_ALLOWED_USER_ID_ENV
- [ ] `pyproject.toml` 加 discord.py（optional 依賴）
- [ ] pytest：user 白名單/custom_id 純函式（不連線）；import 守衛
- [ ] 手動 QA：真 Discord 端到端

Files-scope: channels/discord_bot.py, core/agent.py, config.py, pyproject.toml, tests/test_discord.py

Forbidden scope:
- 網頁儀表板 / MCP

Verification target:
- Unit: `python -m pytest tests/ -q`（不連線部分）
- Manual QA: 真 Discord（需 token + discord.py + user id）

Done gate:
- Phase 2.5 gate：手機發排程 → 預覽 → ✅ → DB1 有列；提醒 DM 收得到
