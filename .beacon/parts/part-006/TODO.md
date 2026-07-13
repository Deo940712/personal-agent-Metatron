# part-006 TODO

Design authority: `.beacon/parts/part-006/DESIGN.md`

## SLICE Map

### part-006-slice-001: 開發迴圈工具 + mcp/tools + stdio adapter(本機)

Status: planned

Goal: 遠端開發迴圈基座(directives 佇列 + opencode.db 讀取器)+ 工具定義 +
stdio MCP server。

Outcome: OpenCode 內 `dev_status` 讀到真 session 進度;`directive_push` 下指令
→ 新 session 開場讀到;「今天行程」可問;排行程 → 確認 → 落地。

Candidate scope:
- [ ] DB1 第八表 `directives`(pending/consumed/cancelled)+ stm CRUD + CLI
- [ ] `core/octools.py`:opencode.db 唯讀讀取器(mode=ro;session 摘要/tail/todo)
      ——同時是 part-005 的 opencode.sessions 掃描器,提前落地
- [ ] `core/mcp/tools.py`:開發迴圈 4 工具(dev_status/session_tail/directive_push/directive_list)+ 助理 7 工具
- [ ] `channels/mcp_stdio.py`:MCP stdio server(官方 `mcp` SDK,探勘後定)
- [ ] AGENTS.md 開場規則:session 開始先讀 `directives pending`
- [ ] pytest:directives CRUD、octools 唯讀(不鎖庫)、dev_status 三源、寫入回 pending、confirm 落地
- [ ] 手動 QA:OpenCode 本機連線 → dev_status/下指令閉環

Files-scope: core/mcp/**, core/octools.py, core/stm.py, channels/mcp_stdio.py, AGENTS.md, tests/test_mcp.py, tests/test_octools.py

Forbidden scope:
- HTTP/遠程(slice-2);Tailscale

Verification target:
- Unit: `python -m pytest tests/test_mcp.py -q`
- Regression: 全綠
- Manual QA: OpenCode 本機 stdio 連線問答/排程

Done gate:
- 工具+stdio+confirm 測試綠;本機 OpenCode 手動 QA 通

### part-006-slice-002: HTTP/SSE adapter + Tailscale(VPS 後)

Status: planned (gate: VPS 階段)

Goal: 同工具集的 HTTP/SSE 傳輸,綁 Tailscale IP,遠端 OpenCode 操控。

Outcome: VPS 起 server 綁 Tailscale IP → 筆電 OpenCode 遠端連 → 問答/排程/確認全通。

Candidate scope:
- [ ] `channels/mcp_http.py`:HTTP/SSE 傳輸,共用 core/mcp/tools
- [ ] `MCP_BIND_HOST` 環境變數;綁公網 IP → 啟動拒絕(fail-closed)
- [ ] config + VPS 遷移 checklist(Tailscale/MCP_BIND_HOST/cron)
- [ ] pytest:綁公網拒絕、Tailscale IP OK、http tool call
- [ ] 手動 QA:VPS + Tailscale 端到端

Files-scope: channels/mcp_http.py, config.py, tests/test_mcp_http.py

Forbidden scope:
- 公網曝露、token/TLS(Tailscale 已加密,不需要)

Verification target:
- Unit: `python -m pytest tests/ -q`
- Manual QA: VPS + Tailscale — blocked(等 VPS 階段)

Done gate:
- 綁公網拒絕測試綠;VPS 手動 QA(blocked 至 VPS 就緒)
