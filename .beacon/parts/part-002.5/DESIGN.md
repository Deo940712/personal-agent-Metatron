# part-002.5 DESIGN

## Goal

Discord bot 介面(INTERFACES.md §4):私人 server + 鎖 user ID、訊息指令
(排程/待辦/查詢)、**非同步確認流**(預覽 → ✅/❌ 按鈕 → 落地)、提醒 DM 推播。
完成後:手機發「明天開會」→ 收預覽 → 按 ✅ → DB1 有列;提醒到期收 DM。

## Non-goals

- 深度知識查詢(recall 全文)——留本機,不經 Discord(§4.1 內容分級)
- slash command(起步用純訊息;§4.3)
- 語音/多平台(Hermes 那套 21 平台——過度工程)

## 探針發現(2026-07-13;設計修正依據)

| # | 發現 | 設計後果 |
|---|---|---|
| A1 | 現有 `agent.invoke(confirm_fn)` 的 confirm_fn 是**同步阻塞回呼**——writer.apply 在同一次呼叫內就落地 | Discord 按鈕是**非同步**(使用者幾分鐘後才點),不能阻塞等待 → 必須把「產生提案」與「確認落地」拆兩階段 |
| A2 | bot 是常駐 process,但核心哲學是無狀態 | 待確認提案**不能只存記憶體**(bot 重啟就丟)→ 序列化存 DB1 |
| A3 | discord.py 未裝、token 未設 | bot 邏輯與 discord.py 解耦,核心邏輯可脫離真 Discord 單元測試 |

### slice-001 稽核追加發現(2026-07-13)

| # | 發現 | 設計後果 |
|---|---|---|
| A2' | precheck 到按鈕落地相隔數分鐘,期間 target 可能被刪/改;`apply_validated(Proposal)` 不重驗 | 第二階段必須**重跑 precheck**——新增 `writer.confirm_and_apply(dict)`:接 pending 的 dict、重驗後才落地。`apply_validated(Proposal)` 僅限同步 CLI(無空窗) |
| A3' | `pending_get.proposal` 是 dict,`apply_validated` 吃 Proposal 物件——型別不符會炸 | chat.confirm 走 `confirm_and_apply(dict)`,型別對齊 |
| A5' | 同提案可存多筆 pending(無去重) | chat 層保證「一訊息一 pending」;無需 DB 去重(單人低頻) |

## Chosen Design

### 兩階段確認(A1/A2 的解)

現有同步 `invoke(confirm_fn)` 保留給 CLI(終端機能阻塞等 stdin)。
Discord 走**非同步兩階段**:

```
階段1 (收訊):
  text → schedule 子 agent → 提案 → writer.precheck(只驗證不落地)
    ├─ 需確認 → 存 pending_proposals(DB1)→ 回預覽 + [✅][❌](button custom_id = pending.id)
    ├─ 免確認(done/查詢)→ 直接 writer.apply → 回結果
    └─ 驗證失敗 → 回拒絕原因

階段2 (按鈕回呼):
  custom_id → 取 pending_proposals(DB1)→
    ├─ ✅ → writer.apply(重建的提案, confirm_fn=已確認)→ 標 pending done → 回「已建立」
    ├─ ❌ → 標 pending cancelled → 回「已取消」
    └─ 逾時(10 分)→ 定期清理標 expired + 記 events
```

### DB1 新增:pending_proposals 表

```sql
CREATE TABLE pending_proposals (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  proposal     TEXT    NOT NULL,          -- JSON 序列化的提案信封
  preview      TEXT    NOT NULL,          -- 已算好的預覽文
  status       TEXT    NOT NULL DEFAULT 'pending'
               CHECK (status IN ('pending','done','cancelled','expired')),
  channel_ref  TEXT,                      -- Discord user/channel id(回覆定址)
  created_at   INTEGER NOT NULL
);
CREATE INDEX idx_pending_status ON pending_proposals(status);
```

DDL 併入 core/stm.py(第七張表);part-001 六表不動,新增一表。

### writer 新增:precheck(A1 的解)

`writer.precheck(proposal, db) -> PrecheckResult`:跑 §3.1 全部驗證(信封/target/
evidence/enum)但**不落地、不需 confirm_fn**;回 `{ok, needs_confirm, preview, reason}`。
`apply` 內部重構為 `precheck` + `_apply_change`,行為對 CLI 完全不變(既有 93→測試不壞)。

### 模組

| 檔案 | 職責 |
|---|---|
| `core/stm.py` +pending CRUD | pending_add / pending_get / pending_set_status / pending_expire_due |
| `core/writer.py` +precheck | 驗證與落地拆分;apply 相容不變 |
| `core/chat.py` | **平台無關**的兩階段邏輯:handle_message(text)→ reply+可選 pending_id;confirm(pending_id, approve)→ reply。**零 discord 依賴,可純單元測試** |
| `channels/discord_bot.py` | 薄 adapter:discord.py 事件 → chat.py;鎖 user ID;按鈕 View;提醒 DM。**零業務邏輯** |
| `core/agent.py` job_remind | notify_fn 改可注入 Discord DM(既有 console 保留為預設) |
| `config.py` | DISCORD_TOKEN_ENV(已有)、DISCORD_ALLOWED_USER_ID_ENV(新) |

### 指令解析(§4.3)

chat.py 先做確定性前綴分派(零 LLM):`today`/`week`/`proj`/`done N`/`todo ...`
→ 直接 stm 查詢或 task 提案;其餘自然語言 → schedule 子 agent。
深度知識查詢明確拒絕:「知識查詢請用本機 CLI」(§4.1)。

## Verification Targets

- pending CRUD:add/get/status/expire roundtrip + boundary
- writer.precheck:驗證通過/各種攔截 + 不落地(precheck 後 DB 無變化)
- chat.py 兩階段(全 mock LLM,零 discord):
  - 排程 → pending 存 → confirm(approve) → 落地;confirm(reject) → 不落地
  - done/查詢免 pending 直接回
  - 深度知識查詢被拒
  - bot「重啟」模擬:pending 存 DB1 → 新 chat 實例仍能 confirm(無狀態驗證)
- expire:逾時 pending 被清 + 記 events
- discord_bot.py:import 守衛(discord 未裝時不炸其他測試);user id 白名單邏輯

## Unit Test Strategy

chat.py / writer / stm 全 pytest(mock LLM,零 discord.py)。discord_bot.py 只測
不需連線的純函式(user 白名單、custom_id 解析);真 Discord 連線是手動 QA。

## Manual QA Strategy

需使用者:`pip install discord.py` + 建私人 server + bot token + 抓自己 user id。
然後:手機發「明天下午兩點開會」→ 收預覽卡 → 按 ✅ → CLI `stm schedule list` 確認;
`--job remind` 指到 Discord notify → 收 DM。

## Risks

- discord.py 版本 API 變動(View/Button 在 2.x 穩定)——pin 版本
- bot 重啟後舊按鈕的 interaction 失效(Discord 限制)——按鈕回呼查 pending 若
  status≠pending 就回「此確認已失效,請重發」;不 crash
- 單人鎖 user id:白名單為空 → 預設拒絕全部(fail-closed,同 Hermes)

## Open Questions

- 逾時清理觸發方式:併入 `--job remind`(順道掃 expire)vs 獨立 job
  → 傾向併入 remind(已是常駐排程,不多開 job)
