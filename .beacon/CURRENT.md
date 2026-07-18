# CURRENT

Status: planning-only
Part: (none active)
Slice: (none promoted)

## Context

part-007（Personal Model）全三 slice 完成並歸檔至 `.beacon/done/part-007/`：
- slice-000：profile_facets 第九表 + stm CRUD/CLI + stability detector（656 tests）
- slice-001：profile_facet 提案 + writer 落地 + supersede（672 tests）
- slice-002：routine 抽取 + consolidate 掛鉤 + vault 投影 + recall 可見（688 tests）

整條鏈路已打通：偏好事件 → 夜間蒸餾 → 證據驅動 facet（重複才升級）→
投影成 vault/agent/profile 可讀筆記 → recall 查得到；pin/forget 使用者硬覆蓋；
矛盾走 supersede 雙側保留。全程走 writer 驗證、evidence 溯源冷儲存。

## Next candidate (NOT promoted — awaits user gate)

- part-009（Proactive Advisor：world-diff quiet-tick 可過期建議）
  ——現在 Personal Model 有 profile 品質,Advisor 可用 facets 校準建議
- part-008（Knowledge Scout：opt-in 網路研究 + external_untrusted 隔離）
- part-010（crowd-scenario 情境演練）
- 或補 part-007 的真實 producer 接線（把 schedule/tasks 完成事件接進 routine 抽取器）
（各 part 設計見 `.beacon/PLAN.md` PARTs 表）

## Blocked（等使用者環境）

- part-006-slice-003 VPS + Tailscale 真機端到端 QA（backlog-008）
- 四批真 QA：LLM key / Discord token / threads session / MCP 本機連線
