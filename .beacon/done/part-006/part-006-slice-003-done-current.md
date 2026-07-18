# DONE: part-006-slice-003 HTTP/SSE adapter + Tailscale(程式面)

Completed: 2026-07-16(程式面);VPS + Tailscale 手動 QA blocked(等 VPS 階段)
Design authority: `.beacon/parts/part-006/DESIGN.md` §162-169

## Goal delivered(程式面)

同工具集(core/mcp/tools)的 HTTP/JSON-RPC 傳輸,供 VPS 上遠端 OpenCode 連線。
綁定前 fail-closed bind guard:綁公網 IP → 拒絕啟動;只允許 loopback、RFC1918 私網、
Tailscale(100.64.0.0/10)。復用 mcp_stdio.handle_request——工具寫一次,stdio/http 共用。

## gate 分層(誠實)

`Status: planned (gate: VPS 階段)` 分兩層:
- **程式面**(HTTP 傳輸 + bind guard + 單元測試)→ 無 gate,本機完成 ✅
- **VPS + Tailscale 端到端 QA** → gate 在 VPS 階段,標 **blocked**(同前幾 slice 的
  「手動 QA 待使用者環境」模式)

## 傳輸選型決策

延續 slice-002 的零依賴:stdlib http.server + 同步 JSON-RPC 回應(唯讀 + 確認的用例
不需完整 SSE streaming)。使用者定案「零依賴 HTTP JSON-RPC」。純函式
handle_http_body/assert_safe_bind_host 可完整單元測試。

## 安全:fail-closed bind guard(Forbidden scope:公網曝露)

- 拒絕 `0.0.0.0`(綁全部介面)與所有公網 IP。
- 只允許:loopback、RFC1918(10/8、172.16/12、192.168/16)、Tailscale CGNAT(100.64/10)。
- 明確列 RFC1918 範圍,不用 `ipaddress.is_private`(它涵蓋 TEST-NET 等保留範圍)。
- `serve()` 綁定前過 guard;綁公網 → 啟動拒絕(不是綁了才發現)。
- Tailscale 是 WireGuard 加密私網,故不需 token/TLS(Forbidden scope)。

## Verification evidence

- 目標測試 `test_mcp_http.py` → **22 passed**(bind guard 公網拒絕/私網/Tailscale/
  loopback OK、env 解析、HTTP JSON-RPC tools/list + directive_push、bad json、
  notification、health)
- `python -m pytest tests/ -q` → **630 passed**(原 608 + 新增 22,零回歸)
- `UnitTestCore.ps1 -Part part-006 -Slice slice-003` → PASS
- Ruff 全清、LSP 零 error
- **端到端 smoke(真 HTTP JSON-RPC)**:GET /health、POST tools/list(10 工具)、
  POST directive_push 入 DB1、POST task_add 回 pending(尊重確認邊界);
  bind guard 拒公網 + serve() fail-closed
- **對抗式探針(實跑)5/5 通過**:
  1. 6 個公網 host 拒絕 + serve() fail-closed on public
  2. loopback + RFC1918 + Tailscale CGNAT 全接受
  3. HTTP 寫入工具回 pending,不繞過 writer/確認
  4. 壞/惡意 JSON-RPC body → well-formed error,不 crash
  5. 未知工具 → JSON-RPC error,不執行

## 交付檔案

channels/mcp_http.py、config.py(MCP_BIND_HOST_ENV + MCP_HTTP_PORT)、
tests/test_mcp_http.py、.beacon/BACKLOG.md(backlog-008 VPS 遷移 checklist)、
.beacon/verification/manifest.json

## Boundary retained

- 無公網曝露、無 token/TLS(Tailscale 已加密);綁公網 fail-closed。
- 寫入仍走 writer/確認邊界;HTTP 未新增第二個寫入口(復用 stdio 的 handle_request)。
- 零新依賴(標準庫 http.server + ipaddress);未改 core/mcp/tools。
- dirty worktree 無關變更未動;無 git commit。

## 手動 QA — BLOCKED(等 VPS 階段)

VPS 遷移 checklist 見 `.beacon/BACKLOG.md` backlog-008:
設 Tailscale IP → `python -m channels.mcp_http` → 筆電 OpenCode 遠端連 →
dev_status/排行程→確認→落地端到端。part-006 全 part 的 done gate 在此真機 QA 完成。
