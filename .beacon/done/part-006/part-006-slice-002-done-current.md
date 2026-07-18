# DONE: part-006-slice-002 開發迴圈工具 + mcp/tools + stdio adapter(本機)

Completed: 2026-07-16
Design authority: `.beacon/parts/part-006/DESIGN.md` §138-160

## Goal delivered

遠端開發迴圈基座:directives 佇列 + opencode.db 讀取器 + 傳輸無關工具層 +
手寫 JSON-RPC stdio MCP server。OpenCode 內可讀真 session 進度、下一步指令入佇列、
問行程/待辦、排行程 → 確認 → 落地。

1. **DB1 第八表 `directives`** — `pending/consumed/cancelled`;`stm.directive_add/
   list/consume/cancel`;CLI `directives add/list/pending/consume/cancel`。consume/
   cancel 只從 pending 轉出(單次消費)。
2. **`core/octools.session_tail`** — 補讀 message/part 最後 N 則對話 text 摘要
   (唯讀 `mode=ro`、容錯;既有 recent_sessions/session_todos/project_activity 保留)。
3. **`core/mcp/tools.py`** — 傳輸無關工具層,10 工具:開發迴圈 4
   (dev_status/session_tail/directive_push/directive_list)+ 助理 6
   (schedule_list/task_list/project_status/schedule_add/task_add/confirm)。
   每工具 JSON schema + handler;handler 復用 octools/scanners/stm/application,
   **寫入回 pending(需確認),不繞過 writer 邊界**。
4. **`channels/mcp_stdio.py`** — 手寫 JSON-RPC 2.0 over stdio,**零依賴**
   (initialize/tools/list/tools/call)。純函式 handle_request 可完整單元測試。
5. **AGENTS.md** — session 開場規則:先讀 `directives pending`,照辦後 consume。

## 傳輸選型決策(Open Question 已定)

DESIGN §198 的 Open Question(官方 `mcp` SDK vs 手寫 JSON-RPC)→ **手寫**。
理由:`mcp` SDK 未安裝且過重;專案核心哲學是最小依賴(pyproject 只有
openai + sqlite-vec);JSON-RPC 2.0 協定穩定,手寫零依賴、可完整單元測試,
對齊「薄 adapter」哲學(DESIGN Global Risks 已預留此選項)。

## Verification evidence

- 目標測試 `test_mcp.py tests/test_mcp_stdio.py tests/test_directives.py
  tests/test_scanners.py` → **61 passed**
- `python -m pytest tests/ -q` → **578 passed**(原 545 + 新增 33,零回歸)
- `UnitTestCore.ps1 -Part part-006 -Slice slice-002` → PASS
- Ruff 全清、LSP 改動 Python 檔零 error
- **stdio 端到端 smoke(實跑 JSON-RPC)**:initialize → tools/list(10 工具)→
  directive_push 入 DB1 → directive_list 讀回 → task_add 回 pending → consume 閉環
- **對抗式探針(實跑)5/5 通過**:
  1. octools `mode=ro` 連線不可寫(opencode.db 永不被改)
  2. directive consume 單次(不可重複消費)
  3. MCP 寫入工具回 pending,不繞過 writer/確認
  4. 未知工具拒絕(ToolError + JSON-RPC error,不靜默執行)
  5. 壞 JSON-RPC 回 parse error,server 不 crash 續服務

## 交付檔案

core/stm.py(第八表 + directives CRUD + CLI)、core/octools.py(session_tail)、
core/mcp/__init__.py、core/mcp/tools.py、channels/mcp_stdio.py、AGENTS.md、
tests/test_directives.py、tests/test_mcp.py、tests/test_mcp_stdio.py、
tests/test_scanners.py(session_tail 測試)、tests/test_schema.py(8 表)、
.beacon/verification/manifest.json

## Boundary retained

- **本機 stdio 專用,無網路、無認證**(HTTP/SSE + Tailscale 留 slice-003,gate: VPS 階段)。
- opencode.db 唯讀(`mode=ro`,WAL 併發讀,不干擾運行中的 OpenCode)。
- 寫入仍走 writer/確認邊界;MCP 未新增第二個寫入口。
- 未動 part-003.5/007+;dirty worktree 無關變更未動;無 git commit。

## 手動 QA(待使用者環境)

- OpenCode config 指向 `python -m channels.mcp_stdio` → 本機連線問答/排程/dev_status。
