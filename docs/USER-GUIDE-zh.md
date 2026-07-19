# Metatron 使用手冊

> 你的個人行程 + 知識庫助理。這份手冊只講「怎麼用」，不講技術細節。
> 技術文件見 [ARCHITECTURE.md](../ARCHITECTURE.md)。

---

## 0. 一分鐘看懂這個系統

Metatron 幫你做四件事：

| 能力 | 一句話 | 從哪用 |
|---|---|---|
| **行程/待辦** | 「明天下午兩點開會提前30分提醒」→ 預覽 → 確認 → 到時 DM 提醒你 | Discord / CLI |
| **知識庫** | Threads/網路存的貼文自動整理進 Obsidian，之後問它「我存過哪些 RAG 做法」 | CLI / Obsidian |
| **主動建議** | 每天早上看你的世界變了什麼（逾期、作息偏離），推建議到 Discord | 自動（Discord DM） |
| **了解你** | 從你的行為學偏好與作息（重複出現才算數），越用越準 | 自動累積 |

**鐵律**：它永遠不會自己改你的東西——任何寫入都先預覽、你確認才落地。

---

## 1. Discord（日常主要入口）

### 1.1 查詢指令（打字即回，免確認）

| 你打 | 它回 |
|---|---|
| `今天` 或 `today` | 今日行程 + 待辦 |
| `本週` 或 `week` | 本週行程 |
| `專案` 或 `proj` | 各專案進度（phase / blockers / 下一步） |
| `todo 買貓砂` | 新增待辦（會出預覽+按鈕） |
| `done 3` | 把 #3 標完成（免確認） |

### 1.2 自然語言排程（其他任何文字）

不是上面指令的文字，會被當成排程需求交給 LLM 解析：

```
明天下午兩點跟阿明開會 提前30分提醒
後天早上十點看牙醫 提前一小時提醒
每週一早上九點站會          ← 支援重複行程
```

→ 它回**預覽 + ✅/❌ 按鈕** → 按 ✅ 才真的建立。

> ⚠️ 目前的限制（已排入改進）：路由是關鍵字制。打「明天」它不會列明天行程，
> 而是回「這不是行程/待辦」。知識問答目前也不走 Discord（用 CLI，見 §2）。

### 1.3 提醒與建議 DM（自動來的）

- **提醒**：行程的提醒時間到 → DM 推播（每 15 分鐘掃一次）
- **建議**：每天早上 8 點，若世界有變化（逾期、作息偏移、新抓的知識）→
  DM 推 1-3 條建議，附「採納 ✅ / 略過 🚫」按鈕
- **按鈕有意義**：你的採納/略過會被記住——同類建議你略過三次，它就不再推

### 1.4 啟動 bot

```powershell
cd "C:\Users\tcart\OneDrive\Desktop\MY AGENT"
python -m channels.discord_bot
```

（想常駐可仿照 `tools\schedule_jobs.ps1` 包成排程工作）

---

## 2. CLI（在家/開發時的完整入口）

全部在專案目錄下執行。

### 2.1 行程與待辦

```powershell
python -m core.agent "明天下午三點開會 提前30分提醒"   # 自然語言 → 預覽 → y 確認
python -m core.stm schedule list                        # 列行程
python -m core.stm tasks add "買貓砂" --due 2026-07-21T20:00
python -m core.stm tasks list
python -m core.stm tasks done 3
```

### 2.2 知識庫問答（recall）

```powershell
python -m core.agent "我存過哪些 RAG 相關的做法?"
```

- 回答**必附引用**（筆記 id）；找不到就誠實說找不到，不會編
- 讀到過時筆記會提示「已有新版」；讀到模擬演練會標「非事實」

### 2.3 個人模型（它學到了什麼）

```powershell
python -m core.stm facets list            # 看它學到的偏好/作息
python -m core.stm facets pin 3           # 這條是對的,固定住(它不再改)
python -m core.stm facets forget 5        # 這條忘掉(不再載入,但證據保留)
```

- 學習規則：**同一件事出現 3 次以上、跨 3 天以上**才升級成穩定認知
- `pin` = 你說了算；`forget` = 立即停用

### 2.4 主動建議

```powershell
python -m core.stm advices list                     # 看累積的建議
python -m core.stm advices list --state pending     # 只看未處理的
```

### 2.5 知識偵察（自動幫你抓網路資料）

```powershell
# 訂閱主題(來源必須在信任清單內,見 config.py SCOUT_ALLOWLIST_DOMAINS)
python -m core.stm watchlist add "RAG 論文" "https://arxiv.org/rss/cs.AI" --interval 7
python -m core.stm watchlist list
python -m core.stm watchlist pause 1      # 暫停 / resume 恢復
```

- 每天凌晨 5 點自動抓 → 進 inbox → 凌晨 3:30 自動評分 → 高分進知識庫
- 抓來的內容一律標「外部不可信」，永遠不會被當成指令執行

### 2.6 情境演練（「如果…會怎樣」）

```powershell
python -m core.scenario rehearse personal_schedule   # 排程壓力演練
python -m core.scenario rehearse habit_change        # 習慣改變演練
python -m core.scenario rehearse project_portfolio   # 專案取捨演練
```

- 一群合成 persona 對你的現況做反應，產出敘事報告存 `vault/scenarios/`
- **硬標「模擬,非事實,非預測」**——參考用，不是預言

---

## 3. Obsidian（知識庫本體）

用 Obsidian 開 `C:\Users\tcart\my-agent-data\vault\`：

| 資料夾 | 內容 |
|---|---|
| `semantic/` | 貼文知識、抓來的網路資料（評分後的） |
| `episodic/` | 每天發生什麼的自動日誌摘要 |
| `agent/profile/` | 它對你的認知（偏好/作息的可讀投影） |
| `agent/ops/` `agent/sop/` | 營運教訓、你顯式存的流程 |
| `scenarios/` | 情境演練報告（非事實區） |
| `INDEX.md` | 總索引（每篇一行描述） |

- 你手動改過的筆記標籤**永遠不會被系統覆蓋**
- 舊筆記不會被刪，只會被新版「取代標記」

---

## 4. 網頁儀表板（在家一眼總覽）

```powershell
python -m channels.dashboard
```

開 http://127.0.0.1:7777 → 七個版塊（今日/專案/管線健康/記憶狀態/事件流/建議/指令佇列）。
**純唯讀**——看得到、改不了，安全。

（你有內網反代：upstream 指向 `127.0.0.1:7777` 即可；認證在反代層自己加）

---

## 5. 在 OpenCode / Claude Code 裡用（MCP）

### 本機
在 OpenCode 的 MCP 設定加：
```json
{ "metatron": { "command": "python", "args": ["-m", "channels.mcp_stdio"],
  "cwd": "C:\\Users\\tcart\\OneDrive\\Desktop\\MY AGENT" } }
```

### 遠端（筆電連桌機，走 Tailscale）
桌機起 server：
```powershell
$env:MY_AGENT_MCP_BIND_HOST = "100.89.45.93"   # 你的 Tailscale IP
python -m channels.mcp_http
```
筆電 OpenCode 指向 `http://100.89.45.93:7788`。

可用工具：查行程、排行程（回預覽，`confirm` 工具確認）、查專案、
`dev_status`（讀你各專案的開發進度）、`directive_push`（遠端留話給下次開發 session）。

---

## 6. 自動排程（已在背景跑，你不用管）

| 時間 | 做什麼 |
|---|---|
| 每 15 分 | 掃到期提醒 → DM |
| 03:00 | 夜間記憶蒸餾（把當天事件濃縮成知識、學你的偏好作息） |
| 03:30 | inbox 評分入庫 |
| 04:00 | 專案進度掃描（git + beacon + OpenCode session） |
| 05:00 | 知識偵察抓取 |
| 08:00 | 晨間建議 → DM |

管理：
```powershell
powershell -File tools\schedule_jobs.ps1          # 重新註冊全部
powershell -File tools\schedule_jobs.ps1 -Remove  # 全部移除
Get-Content C:\Users\tcart\my-agent-data\logs\*.log -Tail 20   # 看 job log
```

---

## 7. 疑難排解

| 症狀 | 處置 |
|---|---|
| 打指令沒反應 / 報「no such table」 | `python -m core.stm init`（安全,只補缺的表） |
| Discord bot 沒回應 | 看 bot 是否在跑;白名單空 = 全拒(檢查環境變數) |
| LLM 類功能全失敗 | 檢查 `MY_AGENT_LLM_API_KEY` / `MY_AGENT_LLM_BASE_URL`(User 環境變數) |
| 提醒沒推 DM | 檢查 `MY_AGENT_DISCORD_TOKEN` + `MY_AGENT_DISCORD_ALLOWED_USER_ID`;失敗會 fallback 印在 log |
| 檢索怪怪的 | `python -m pytest tests/test_golden_queries.py -q`(檢索品質回歸) |
| 任何 job 壞掉 | 看 `agent_runs`:`python -c "from core import stm; con=stm.connect(); [print(r) for r in con.execute('SELECT id,status,summary,error FROM agent_runs ORDER BY id DESC LIMIT 5')]"` |
| 整體健康檢查 | `python -m pytest tests/ -q`(全綠 = 系統健康) |

### 環境變數一覽（全部 User 層級）

| 變數 | 用途 |
|---|---|
| `MY_AGENT_LLM_API_KEY` | LLM 金鑰 |
| `MY_AGENT_LLM_BASE_URL` | LLM 端點（內網 proxy） |
| `MY_AGENT_EMBED_BASE_URL` | embedding 端點（選配） |
| `MY_AGENT_DISCORD_TOKEN` | Discord bot token |
| `MY_AGENT_DISCORD_ALLOWED_USER_ID` | 白名單 user id |
| `MY_AGENT_MCP_BIND_HOST` | MCP HTTP 綁定 IP（未設=127.0.0.1） |

> ⚠️ **金鑰永遠放環境變數，不要寫進 config.py**——那個檔案會進 git。

---

## 8. 它的行為原則（為什麼它是這樣）

1. **永不自作主張**：所有寫入先預覽、你確認才落地；逾時視同拒絕
2. **永不編造**：知識回答必附引用；找不到就說找不到
3. **永不刪除**：原始記錄永久保存；「忘記」只是不再主動想起
4. **慢慢認識你**：一次行為不會變成永久標籤；重複出現才升級；你 pin/forget 說了算
5. **網路內容是資料不是指令**：抓來的東西再怎麼寫「請執行 X」都只會被當成文字
6. **模擬不是事實**：演練報告永遠帶著「非事實」標記

---

*版本：2026-07-19（parts 001-011 全數完成；852 tests）*
*已知改進方向：對話式路由（backlog-033）——讓 Discord 對話更自然、開放知識問答*
