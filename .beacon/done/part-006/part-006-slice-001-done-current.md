# DONE: part-006-slice-001 互動硬化(MCP 前置地基)

Completed: 2026-07-16
Design authority: `.beacon/parts/part-006/DESIGN.md` §112-148

## Goal delivered

在 MCP 成為第三個介面入口前,補齊 CLI/Discord 的三個架構裂縫(架構審查 P0):

1. **統一 invocation 入口** — `core/application.py::invoke(text, InvocationContext)
   -> InvocationResult`(text/route/outcome/run_id/pending_id/needs_confirmation)。
   委派既有確定性前綴分派(無 LLM router),並包 `agent_runs` 記錄。**CLI 與
   Discord 都改呼叫它**:
   - **CLI**(`agent.main`)給 `confirm_fn` → 同步模式:需確認的寫入立即
     preview→confirm→落地(不留 pending 按鈕),保留原 CLI UX。
   - **Discord**(`discord_bot.on_message`)無 `confirm_fn` → 非同步 pending 流,
     回按鈕。
   兩種模式共用同一分派與同一 `pending_claim` 原子保護。Discord 也因此**有了
   run audit**(舊 chat.handle_message 路徑不記 run 的稽核缺口已補)。
2. **pending 原子認領** — `pending_proposals` CHECK 加 `applying` 狀態;
   `stm.pending_claim(db,id)` 單一原子 UPDATE(`WHERE id=? AND status='pending'`);
   `stm.pending_finish(db,id,status)` 從 `applying` 收尾;`chat.confirm` 改用
   claim/finish。**併發雙擊/跨介面同時確認只落地一次**。
3. **recall 嚴格引用** — `RecallResult` 加 `outcome`;`found` 必須 ≥1 有效
   citation,LLM 回「有主張但 citations=[]」一律降級 `not_found`。**無來源不得斷言**
   由程式面保障(不信 LLM 自律)。

## Verification evidence

- `python -m pytest tests/test_application.py tests/test_pending_claim.py tests/test_recall.py -q`
  → **48 passed**(application 17 含同步 confirm 6 + pending_claim 14 + recall 17)
- `python -m pytest tests/ -q` → **360 passed**(原 326 + 新增 34,零回歸)
- CLI 同步路徑 smoke:`todo`→applied(pending_id=None 立即落地)、`today`→answered、
  `done`→applied、decline→rejected、agent_runs 3/3 finished
- `powershell -ExecutionPolicy Bypass -File .beacon/verification/UnitTestCore.ps1 -Part part-006 -Slice slice-001`
  → PASS
- Ruff:改動檔案全清;LSP:改動檔案零 error
- **對抗式探針(實跑,非僅測試綠)**:
  1. 8-way 併發 confirm → 恰好一筆行程落地
  2. recall 無引用主張 → outcome=not_found、citations=[]
  3. Discord path(trigger=chat)→ agent_runs 記錄且 finished
  4. pending_finish 未經 claim → False(不可繞過認領)
  → ALL PROBES PASSED

## Boundary retained

- **CLI 現已走統一入口 `application.invoke`**,以 `confirm_fn` 保留同步 UX
  (preview→confirm→立即落地);Discord/未來 MCP 不給 confirm_fn 走 pending 非同步。
  同一入口、同一分派、同一 pending_claim 原子保護,兩種確認模式並存。
- `agent.invoke` 保留為既有 API(B6 白名單/recall 前綴邏輯仍被 8 個測試覆蓋);
  CLI `main` 已改用 `application.invoke`,不再經 `agent.invoke`。
- LLM router / AgentSpec registry 延後(backlog-029)。
- MCP transport(stdio/directives)留在 slice-002;HTTP/Tailscale 留在 slice-003。
- writer 仍是唯一 deterministic shared-state commit boundary;未新增第二個 apply path。

## Files touched

core/application.py(新)、core/agent.py、core/stm.py、core/chat.py、core/recall.py、
core/tools/memory.py、core/tools/contracts.py、channels/discord_bot.py、
agents/recall.md、tests/test_application.py(新)、tests/test_pending_claim.py(新)、
tests/test_recall.py、.beacon/verification/manifest.json
