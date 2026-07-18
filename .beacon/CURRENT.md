# CURRENT

Status: planning-only
Part: (none active)
Slice: (none promoted)

## Context

part-010（crowd-scenario 情境演練）全三 slice 完成並歸檔至 `.beacon/done/part-010/`：
- slice-000：scenarios 專區 + bucket firewall + non_authoritative 儲存（789 tests）
- slice-001：vendored crowd-scenario（pin 1b40712a）+ subprocess adapter +
  recall 模擬標記（796 tests，含真 subprocess 冒煙）
- slice-002：三個人 templates + `python -m core.scenario rehearse` CLI（807 tests）

**全部規劃 part 完成**：自適應助理層四塊到齊（007 Personal Model / 009 Advisor /
008 Scout / 010 Scenario Rehearsal）。807 tests 綠。

## 系統自動運行（使用者離開期間）

排程 jobs 已註冊 Windows Task Scheduler（見 tools/schedule_jobs.ps1）：
remind 每 15 分；scout/advise/consolidate/curate/track 每日。
無 LLM key 的 job 會記 error 於 agent_runs（fail-closed，不影響其他 job）。

## Next candidate (NOT promoted — awaits user gate)

- 跨 part 接線：routine producer / advisor 降頻讀 facet / world-diff 接 scout
- 文件同步（part-010 反映進 ARCHITECTURE/README）
- backlog triage（librarian backlog-017 等）

## Blocked（等使用者環境）

- 四批真 QA：LLM key / Discord token / threads session / MCP 本機連線
- VPS + Tailscale 真機 QA（backlog-008）
