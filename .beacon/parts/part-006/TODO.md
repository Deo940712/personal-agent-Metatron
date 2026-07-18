# part-006 TODO

Design authority: `.beacon/parts/part-006/DESIGN.md`

## SLICE Map

### part-006-slice-000: 能力工具基座

Status: done (2026-07-15; snapshot: `.beacon/done/part-006/part-006-slice-000-done-current.md`)

Goal: 將現有使用者可見能力模組化成 typed capability tools，建立靜態配對 catalog；
保持 CLI/Discord observable behavior、writer gate 與獨立 skills 邊界不變。

Outcome: `core/tools/` 提供 schedule/tasks/projects/memory 能力；`core/chat.py`
只做文字路由與 Reply 轉換；`docs/TOOLS.md` 明列 feature/tool/agent/interface/
permission/storage；未來 MCP 直接復用同一能力層。

Candidate scope:
- [x] tests/test_tools.py + chat characterization tests 先鎖 today/week/proj/todo/done/recall
- [x] core/tools/contracts.py + catalog.py（typed contracts + 靜態 catalog）
- [x] core/tools/schedule.py, tasks.py, projects.py, memory.py
- [x] core/chat.py 改呼叫 tools；Reply API 與訊息文字保持相容
- [x] docs/TOOLS.md + ARCHITECTURE/INTERFACES/README/AGENTS 連結與摘要

Files-scope: core/tools/**, core/chat.py, tests/test_tools.py, tests/test_chat.py,
docs/TOOLS.md, ARCHITECTURE.md, INTERFACES.md, README.md, README-en.md, AGENTS.md,
.beacon/parts/part-006/**, .beacon/verification/manifest.json

Forbidden scope:
- pending schema/migration/claim、application.invoke（slice-001）
- MCP transport/directives（slice-002/003）
- vendored code、低階 stm/SQL 公開、dynamic plugins、第二個 write tool

Verification target:
- Unit: `python -m pytest tests/test_tools.py tests/test_chat.py tests/test_recall.py -q`
- Regression: `python -m pytest tests/ -q`
- Manual QA: stm init + schedule/tasks/projects list CLI smoke

Done gate:
- tool catalog 與 docs 配對矩陣一致；chat 行為不變；writer 唯一寫入口不變；全綠

### part-006-slice-001: 互動硬化(MCP 前置地基)

Status: done (2026-07-16; snapshot: `.beacon/done/part-006/part-006-slice-001-done-current.md`)

Goal: 統一 invocation 入口 + pending 原子認領 + recall 嚴格引用——在多一個 MCP
入口前補齊 CLI/Discord 的三個架構裂縫(架構審查 P0)。

Outcome: CLI/Discord 走同一 `application.invoke` 回 `InvocationResult`;併發確認
只落地一次;recall found 答案無引用即拒絕;Discord 也有 agent_runs 記錄。

Candidate scope:
- [x] `core/application.py`:`invoke(text, InvocationContext) -> InvocationResult`
      (route/outcome/pending_id/needs_confirmation/run_id);委派確定性前綴分派;
      無 LLM router
- [x] CLI(core/agent.py main)+ Discord(channels/discord_bot.py)都改呼叫
      application.invoke;CLI 給 confirm_fn 走同步立即落地(UX 不變),Discord 不給
      走 pending 非同步。兩者皆記 agent_runs
- [x] `pending_proposals` 加 `applying` 狀態 + `stm.pending_claim`(原子 UPDATE)
      + `stm.pending_finish`;chat.confirm 改用 claim/finish
- [x] `recall.ask` 回答契約分 found/not_found;found 無有效 citation → 降級 not_found
- [x] pytest + 對抗式探針:三介面同入口一致、併發 claim 只落地一次、found 無引用降級、
      Discord 有 agent_runs 記錄

Files-scope: core/application.py, core/agent.py, core/chat.py, core/recall.py, core/stm.py, channels/discord_bot.py, agents/recall.md, tests/test_application.py, tests/test_pending_claim.py, tests/test_recall.py

Forbidden scope:
- LLM router / AgentSpec registry(延後,backlog-029)
- MCP 傳輸(slice-1)

Verification target:
- Unit: `python -m pytest tests/test_application.py tests/test_pending_claim.py tests/test_recall.py -q`
- Regression: 全綠(既有 314)
- Manual QA: CLI 與 Discord 同指令行為一致

Done gate:
- 三裂縫測試綠;既有回歸全綠

### part-006-slice-002: 開發迴圈工具 + mcp/tools + stdio adapter(本機)

Status: done (2026-07-16; snapshot: `.beacon/done/part-006/part-006-slice-002-done-current.md`)
578 tests 綠、UnitTestCore PASS、stdio 端到端 smoke + 5 對抗探針通過。傳輸選型:手寫 JSON-RPC(零依賴)。

Goal: 遠端開發迴圈基座(directives 佇列 + opencode.db 讀取器)+ 工具定義 +
stdio MCP server。

Outcome: OpenCode 內 `dev_status` 讀到真 session 進度;`directive_push` 下指令
→ 新 session 開場讀到;「今天行程」可問;排行程 → 確認 → 落地。

Candidate scope:
- [x] DB1 第八表 `directives`(pending/consumed/cancelled)+ stm CRUD + CLI(14 tests)
- [x] `core/octools.py`:opencode.db 唯讀讀取器(mode=ro;session 摘要/tail/todo)
      ——session_tail 補齊;recent_sessions/session_todos/project_activity 既有(6 新 tests)
- [x] `core/mcp/tools.py`:開發迴圈 4 工具 + 助理 6 工具(16 tests)
- [x] `channels/mcp_stdio.py`:MCP stdio server(**手寫 JSON-RPC 2.0,零依賴**;
      Open Question 定案:mcp SDK 未裝且過重,手寫對齊最小依賴哲學)(11 tests)
- [x] AGENTS.md 開場規則:session 開始先讀 `directives pending`
- [x] pytest:directives CRUD、octools 唯讀(不鎖庫)、dev_status 三源、寫入回 pending、confirm 落地
      + stdio 端到端 smoke + 5 對抗探針
- [ ] 手動 QA:OpenCode 本機連線 → dev_status/下指令閉環(待使用者環境)

Files-scope: core/mcp/**, core/octools.py, core/stm.py, channels/mcp_stdio.py, AGENTS.md, tests/test_mcp.py, tests/test_octools.py

Forbidden scope:
- HTTP/遠程(slice-2);Tailscale

Verification target:
- Unit: `python -m pytest tests/test_mcp.py -q`
- Regression: 全綠
- Manual QA: OpenCode 本機 stdio 連線問答/排程

Done gate:
- 工具+stdio+confirm 測試綠;本機 OpenCode 手動 QA 通

### part-006-slice-003: HTTP/SSE adapter + Tailscale(VPS 後)

Status: code done (2026-07-16; snapshot: `.beacon/done/part-006/part-006-slice-003-done-current.md`)
程式面完成:630 tests 綠、UnitTestCore PASS、端到端 HTTP smoke + 5 對抗探針通過。
手動 QA(VPS + Tailscale 真機)blocked 至 VPS 階段。傳輸選型:零依賴 HTTP JSON-RPC。

Goal: 同工具集的 HTTP 傳輸,綁 Tailscale IP,遠端 OpenCode 操控。

Outcome: VPS 起 server 綁 Tailscale IP → 筆電 OpenCode 遠端連 → 問答/排程/確認全通。

Candidate scope:
- [x] `channels/mcp_http.py`:**stdlib http.server + 同步 JSON-RPC**(零依賴),
      共用 core/mcp/tools 與 mcp_stdio.handle_request(22 tests)
- [x] `MCP_BIND_HOST` 環境變數;綁公網 IP / 0.0.0.0 → 啟動拒絕(fail-closed;
      只允許 loopback/RFC1918/Tailscale 100.64/10)
- [x] config(MCP_BIND_HOST_ENV + MCP_HTTP_PORT)+ VPS 遷移 checklist(backlog-008)
- [x] pytest:綁公網拒絕、Tailscale/私網/loopback OK、http tool call + 端到端 smoke + 5 對抗探針
- [ ] 手動 QA:VPS + Tailscale 端到端(**blocked 至 VPS 階段**)

Files-scope: channels/mcp_http.py, config.py, tests/test_mcp_http.py

Forbidden scope:
- 公網曝露、token/TLS(Tailscale 已加密,不需要)

Verification target:
- Unit: `python -m pytest tests/ -q`
- Manual QA: VPS + Tailscale — blocked(等 VPS 階段)

Done gate:
- 綁公網拒絕測試綠;VPS 手動 QA(blocked 至 VPS 就緒)
