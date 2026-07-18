# CURRENT

Status: planning-only
Part: (none active)
Slice: (none promoted)

## Context

part-003.1（雙語記憶架構契約）已完成並歸檔至 `.beacon/done/part-003.1/`。
part-003.2-slice-001（ECC 評估 + 隔離 Task Capsule A/B 實驗）已完成並歸檔至
`.beacon/done/part-003.2/`（判定 retain_a，未採用 B/C/D、未改正式 schema）。
part-003.5-slice-001（唯讀網頁儀表板）已完成並歸檔至 `.beacon/done/part-003.5/`：
stdlib http.server 零依賴、七版塊、三層唯讀保證。
part-006 全 slice 程式面完成並歸檔至 `.beacon/done/part-006/`：
- slice-000 能力工具基座 / slice-001 互動硬化 / slice-002 本機 stdio MCP
- slice-003 遠程 HTTP JSON-RPC（bind guard fail-closed，只允 loopback/RFC1918/
  Tailscale；630 tests 綠、端到端 smoke + 5 對抗探針通過）
**唯一剩餘**：slice-003 的 VPS + Tailscale 真機手動 QA（blocked 至 VPS 階段，
checklist 見 backlog-008）。

## Next candidate (NOT promoted — awaits user gate)

- part-007（Personal Model：profile_facets 學習生命週期）
- part-008（Knowledge Scout：opt-in 網路研究 + external_untrusted 隔離）
- part-009（Proactive Advisor：world-diff quiet-tick 可過期建議）
- 或在真實 LLM 迴圈下重測 Task Capsule B。
（各 part 設計見 `.beacon/PLAN.md` PARTs 表）

## Blocked（等使用者環境）

- part-006-slice-003 VPS + Tailscale 真機端到端 QA。
- 四批真 QA：LLM key / Discord token / threads session / MCP 本機連線。

## Open decision (documentation-only, no implementation yet)

- 多層記憶：A（現況）維持。B（Task Capsule）已實證比較 → retain_a，未採用；
  是否在真實 LLM 迴圈下重測 B、或採用 B 進 production，留作使用者未來決策
  （需獨立 production-design 提案）。C（warm set）、D（LLM paging）無證據，未授權。
  報告見 `docs/ECC-TASK-CAPSULE-REPORT-zh.md`；證據見
  `.omo/evidence/task-13-ecc-task-capsule-experiment-summary.{json,csv}`。
