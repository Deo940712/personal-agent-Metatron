# part-006 DESIGN

## Goal

MCP server:**遠端接管開發迴圈**——人不在電腦前,讀取「OpenCode 目前做到哪」
(session 進度 + Beacon CURRENT + git),並下「下一步指令」(指令佇列)。
外加助理查詢(行程/知識/專案)。**一套工具、兩種傳輸**:本機 stdio(先做)→
VPS 遠程 HTTP/SSE over Tailscale。寫入仍走 writer + 確認。

## 使用者定案(2026-07-13)

- 場景:**先 A(本機)後 B(VPS 遠程)**;核心用例 = **遠端讀開發進度 + 下一步指令**
- 遠程安全:**Tailscale 私有網路**(不上公網,零認證複雜度、零攻擊面)
- 寫入:**讀 + 寫,寫仍需確認**

## 探勘實證(2026-07-13):OpenCode session 可讀

`C:\Users\tcart\.local\share\opencode\opencode.db`(SQLite)實測:

| 表 | 內容 | 用途 |
|---|---|---|
| `session` | 21 個 session:title/directory/model/token 統計/time_updated | 「最近在做什麼專案/任務」 |
| `message` + `part` | 完整對話(1886 msgs/7013 parts,JSON data 欄) | 「AI 剛做完什麼」(取最後 N 則 assistant 摘要) |
| `todo` | 每 session 的待辦(content/status/position) | 「AI 的工作清單勾到哪」 |

**唯讀開啟(`mode=ro`)**,不干擾運行中的 OpenCode(WAL 模式支援並行讀)。

## 下指令的三層(誠實分級)

| 層 | 做法 | 決定 |
|---|---|---|
| **L1 指令佇列** | 遠端下指令 → DB1 `directives` 表 → 下次 OpenCode session 開場讀取(AGENTS.md 規則 + MCP 工具) | ✅ **slice-1 做** |
| L2 注入運行中 session | 依賴 OpenCode 內部 attach API,脆弱 | ❌ 不做(等官方 server API 成熟再評) |
| L3 遠端啟動 headless session | `opencode run` CLI,VPS 可行但需沙箱+成本控管 | 📋 backlog,VPS 後評估 |

## 設計哲學:傳輸與工具分離

MCP 本來就把工具邏輯與傳輸分開。延續本專案「薄 adapter 零業務邏輯」:

```
core/mcp/tools.py       ← 工具定義(與傳輸無關;呼叫既有 chat/recall/stm)
        │
        ├─ stdio adapter(channels/mcp_stdio.py)  → 本機 OpenCode spawn(slice-1)
        └─ HTTP/SSE adapter(channels/mcp_http.py)→ VPS 常駐 + Tailscale IP(slice-2)
```

工具寫一次,兩 adapter 共用——同 Discord bot 是 chat.py 的薄 adapter。

## 工具清單

### 開發迴圈工具(核心用例:遠端讀進度 + 下指令)

| 工具 | 讀/寫 | 落地 |
|---|---|---|
| `dev_status([project])` | 讀 | 三源綜合:**opencode.db**(最近 session title/時間/todo 勾選)+ **beacon.scan**(CURRENT part/slice/status + TODO map)+ **git.scan**(最後 commit/未推送數)——即 coding_tracker 的三訊號源(§3.3)復用 |
| `session_tail(session_id?, n)` | 讀 | opencode.db message/part:最後 n 則對話摘要(「AI 剛做了什麼、卡在哪」) |
| `directive_push(project, text)` | **寫** | DB1 `directives` 表(新增):下一步指令入佇列 |
| `directive_list([status])` | 讀 | 佇列現況 |

**指令佇列閉環**:`directive_push("my-agent", "curator 做完後先跑 audit 再進 recall")`
→ DB1 → 下次在該專案開 OpenCode session 時,AGENTS.md 規則(「開場執行
`python -m core.stm directives pending`」)+ 或 MCP `directive_pop` 讓 session 自取
→ 標 consumed。**不注入運行中 session**(L2 不做)——佇列是可靠的最低承諾。

### 助理工具(§3.4 延續)

| 工具 | 讀/寫 | 落地 | 確認? |
|---|---|---|---|
| `recall_query(query)` | 讀 | core/recall.py(part-004) | 否 |
| `schedule_list` / `task_list` / `project_status` | 讀 | stm | 否 |
| `memory_rehydrate(note_id)` | 讀 | retrieve.rehydrate | 否 |
| `schedule_add(text)` / `task_add(text)` | **寫** | chat.handle_message → pending | **是** |
| `confirm(pending_id, approve)` | 寫 | chat.confirm(兩階段收尾) | — |

寫入類**復用 chat.py 的兩階段**;pending 是 DB1 共用 → MCP 發起、Discord 確認,
跨介面天然一致。遠程 Tailscale 下 recall 全文內容分級(§4.1)解除。

## 能力工具層前置(2026-07-15 定案:先模組化能力,再統一入口)

使用者可見能力先收斂到 `core/tools/`，讓 CLI、Discord、未來 MCP 共用；這裡的
tool 是**應用能力邊界**，不是把每個 Python 函式公開。`stm` CRUD、SQL helper、
writer 內部 dispatch 都保持 private。

```text
core/tools/
  contracts.py   typed context/result + ToolSpec
  catalog.py     靜態 feature→tool→agent→interface→permission→storage 對照
  schedule.py    行程讀取與 schedule proposal staging
  tasks.py       待辦讀取、proposal staging、done
  projects.py    專案狀態讀取
  memory.py      recall/rehydrate 能力邊界
```

規則:

1. catalog 是靜態文件/權限資料，不是動態 plugin loader。
2. 所有 write-capable capability 仍只能產 proposal 或呼叫 `writer.apply` 的既有
   驗證路徑；不新增第二個公開寫入口。
3. 排程 jobs 與 `skills/` 獨立 CLI 管線列入 catalog，但不搬進 `core/tools/`；
   它們的可獨立執行、idempotent 邊界不變。
4. Agent allowlist 與 MCP exposure 是 catalog 的不同欄位；「存在的 capability」
   不代表每個 agent/interface 都能呼叫。

### slice-0:能力工具基座

- 建立 typed contracts + 靜態 catalog。
- 抽出目前 `chat.py` 內的 today/week/proj/todo/done/recall 能力；`chat.Reply`
  保持相容，只做文字路由與結果轉換。
- 建立 `docs/TOOLS.md` 作為配對矩陣權威；ARCHITECTURE/INTERFACES 只摘要並連結。
- characterization tests 先鎖住 chat observable behavior，再搬移。

## 互動硬化前置(能力工具基座之後)

MCP 會成為第三個介面入口。在多一個入口前,先把 CLI/Discord 已暴露的三個
架構裂縫補起來,否則 MCP 會複製同樣的問題(架構審查 P0):

1. **統一 invocation 入口**:目前 CLI 走 `agent.invoke`、Discord 走
   `chat.handle_message`,兩條路能力不一致(today/todo 只在 Discord;agent_runs
   只在 CLI;pending 只在 Discord)。新增 `core/application.py::invoke(text, ctx)
   -> InvocationResult`,三介面都只呼叫它。不引入 LLM router——沿用現有確定性
   前綴分派,無法判定才送 schedule 子 agent。
2. **pending 原子認領**:`chat.confirm` 目前「讀 pending → 檢查 status → apply →
   最後標 done」有競態(雙擊/跨介面同時確認 → 落地兩次)。改成
   `UPDATE pending_proposals SET status='applying' WHERE id=? AND status='pending'`,
   rowcount=1 才執行,=0 表示已被處理。
3. **recall 嚴格引用**:`recall.ask` 目前只在 citations 非空時驗證,LLM 可回
   「有主張但 citations=[]」繞過「無來源不得斷言」。改成回答分
   `found`(必須 ≥1 有效 citation)/ `not_found`(才可空 citations)兩態。

`InvocationResult` 欄位:`text / route / outcome / pending_id / needs_confirmation
/ run_id`。`outcome ∈ {applied, rejected, not_actionable, answered, no_result,
needs_confirmation}`。這一步也順帶讓 Discord 有 agent_runs 記錄。

**AgentSpec / model 分級**:延後(非本 part 阻塞項)。目前子 agent 契約頂部的
`type/model/tools` 只是文件、程式沒讀;真正的工具白名單仍由程式碼硬控。等
part-007+ 有多個新 agent 型別時再建靜態 registry(backlog-029),不預先造抽象。

## Chosen Design(四 slice)

### slice-1:互動硬化(MCP 前置地基)

- `core/application.py`:`invoke(text, ctx: InvocationContext) -> InvocationResult`
  ——收斂 CLI 的 `agent.invoke` 與 Discord 的 `chat.handle_message` 分派邏輯到一處;
  `InvocationContext(trigger, allow_recall, channel_ref)`。CLI/Discord adapter 改呼叫它。
- `pending_proposals` 加 `applying` 狀態;`stm.pending_claim(db, id) -> bool`(原子
  UPDATE);`chat.confirm` 改用 claim。
- `recall.ask` 回答契約分 `found`/`not_found`;found 無有效 citation → 降級 not_found。
- pytest:三介面經同一入口行為一致;併發 claim 只成功一次;found 無引用被拒。

### slice-2:core/mcp/tools + stdio adapter(本機,slice-1 之後)

- DB1 新增 `directives` 表(第八表):
  `directives(id, project, text, status CHECK(pending/consumed/cancelled), created_at, consumed_at)`
  + stm CRUD + CLI(`python -m core.stm directives pending/add/consume`)
- `core/octools.py`:opencode.db 唯讀讀取器(`mode=ro`;session 摘要/tail/todo)
  ——**同時就是 part-005 coding_tracker 的 opencode.sessions 掃描器**(提前落地)
- `core/mcp/tools.py`:開發迴圈 4 工具 + 助理 7 工具(schema + handler)
- `channels/mcp_stdio.py`:MCP stdio server(SDK 探勘後定;傾向官方 `mcp` SDK)
- AGENTS.md 加開場規則:「執行 `python -m core.stm directives pending`,有指令先照辦」
- 無網路、無認證——本機自用

### slice-3:HTTP/SSE adapter + Tailscale(VPS 後)

- `channels/mcp_http.py`:同工具集的 HTTP/SSE 傳輸
- 綁 **Tailscale IP**(非 0.0.0.0,非公網 IP):`MCP_BIND_HOST` 環境變數,
  預設 Tailscale 介面;絕不綁公網
- 無需 token/TLS——Tailscale 已是加密私有網路(WireGuard)。SSRF 式防護:
  拒絕綁公網 IP(啟動時檢查,fail-closed)
- VPS 遷移 checklist(backlog-008)加:設 Tailscale、MCP_BIND_HOST、排程改 cron

## Verification Targets

- tools:每工具 input schema 驗證 + handler 正確呼叫既有層(mock)
- 寫入工具:回 pending + 預覽;confirm 工具落地;非法輸入拒絕
- stdio adapter:JSON-RPC roundtrip(mock stdin/stdout)、tool list、tool call
- http adapter(slice-2):綁公網 IP → 啟動拒絕(fail-closed);Tailscale IP → OK
- 手動 QA:OpenCode 連本機 stdio → 問「今天行程」得答案;排行程 → 確認 → 落地

## Unit Test Strategy

pytest;MCP 傳輸層 mock;工具邏輯測真(呼叫既有 stm/chat,不 mock DB)。
真 OpenCode 連線是手動 QA。

## Manual QA Strategy

- slice-1:OpenCode config 加 stdio server → 本機問答/排程
- slice-2:VPS 起 http server 綁 Tailscale IP → 筆電 OpenCode 遠端連 → 同驗證

## Risks

- MCP SDK 版本/協定變動——pin 版本;或手寫 JSON-RPC(協定穩定,無依賴)
- 寫入確認的跨介面一致性:MCP 發起、Discord 確認——pending 已是 DB1 共用,
  chat.confirm 平台無關,天然支援(part-002.5 已驗證無狀態跨實例)
- Tailscale 未裝時 slice-2 無法測——slice-2 本就 gate 在 VPS 階段

## Open Questions

- MCP 傳輸用官方 `mcp` Python SDK vs 手寫 JSON-RPC?
  → slice-1 探勘 SDK 成熟度後定;傾向 SDK(stdio/http 都包好)但若依賴太重則手寫
- confirm 在 MCP 內怎麼呈現:獨立 `confirm` 工具 vs 回傳帶 pending_id 讓使用者
  下一輪呼叫 → 傾向獨立 confirm 工具(OpenCode 對話裡自然)
