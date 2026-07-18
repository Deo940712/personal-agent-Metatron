# CURRENT

Status: planning-only
Part: (none active)
Slice: (none promoted)

## Context

part-008（Knowledge Scout）全三 slice 完成並歸檔至 `.beacon/done/part-008/`：
- slice-000：watchlist 第十一表 + allowlist（fail-closed）+ due 判定（757 tests）
- slice-001：web fetch skill（RSS/Atom）+ inbox 落地 + external_untrusted 污染標籤
  + curator 注入隔離框（769 tests）
- slice-002：觸發邏輯 + `--job scout` + 端到端 fetch→inbox→curate→recall（778 tests）

自適應助理層（ARCHITECTURE §15）三塊完成：
- part-007 Personal Model（證據驅動 facets）
- part-009 Proactive Advisor（world-diff 建議 + 校準閉環）
- part-008 Knowledge Scout（opt-in 網路研究 + 不受信任隔離）

Scout 嚴守防注入：allowlist（fail-closed，防子字串攻擊）+ 逐則 URL 驗 +
external_untrusted 標籤 + curator 隔離框 + 抓取零 writer 寫入 + 只觸發條件下研究。

## Next candidate (NOT promoted — awaits user gate)

- part-010（crowd-scenario 情境演練：vendored 釘版 + subprocess，只吃 bucket seed、
  只回 advisory 報告、標 non_authoritative）
- 補接線：schedule/tasks 完成事件 → part-007 routine 抽取器 producer；
  advisor 忽略降頻讀 advice_pref facet；part-009 world-diff「新收知識」訊號
  接 part-008 scout 落地
- 全面文件同步（ARCHITECTURE/README/TOOLS 反映 part-007/008/009 已實作）
（各 part 設計見 `.beacon/PLAN.md` PARTs 表）

## Blocked（等使用者環境）

- 真網路抓取 QA（scout 真 RSS 來源）
- 真 Discord 連線 QA（advice 推播 + 按鈕，待 token）
- part-006-slice-003 VPS + Tailscale 真機 QA（backlog-008）
- 四批真 QA：LLM key / Discord token / threads session / MCP 本機連線
