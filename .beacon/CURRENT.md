# CURRENT

Status: planning-only
Part: (none active)
Slice: (none promoted)

## Context

part-009（Proactive Advisor / Subconscious）全三 slice 完成並歸檔至
`.beacon/done/part-009/`：
- slice-000：advices 第十表 + baseline checkpoint + 確定性 world-diff（706 tests）
- slice-001：reflect + advice 生成 + 四重防疲勞（716 tests）
- slice-002：Discord 推播 + action→confirm + 校準回饋 + job 接線（735 tests）

Metatron 現在「活起來」：`--job advise` 定期醒來看 world-diff（新增行程/逾期任務/
停滯專案/作息偏離/goal）→ quiet 零 LLM / 有變化才 reflect → 產可過期建議
（配額/去重/過期防疲勞）→ 推 Discord → action 走確認 → 接受/忽略回饋成 part-007
preference facet（校準閉環，越用越準）。全程只建議、不自主行動。

part-007（Personal Model）+ part-009（Advisor）構成自適應助理層（ARCHITECTURE §15）
的前兩塊。

## Next candidate (NOT promoted — awaits user gate)

- part-008（Knowledge Scout：opt-in 網路研究 + external_untrusted 隔離）
  ——接上 world-diff 的「新收知識」訊號欄位（目前留白）
- part-010（crowd-scenario 情境演練）
- 補接線：schedule/tasks 完成事件 → part-007 routine 抽取器 producer；
  advisor 忽略降頻讀 advice_pref facet
（各 part 設計見 `.beacon/PLAN.md` PARTs 表）

## Blocked（等使用者環境）

- 真 Discord 連線 QA（advice 推播 + 按鈕，待 token）
- part-006-slice-003 VPS + Tailscale 真機 QA（backlog-008）
- 四批真 QA：LLM key / Discord token / threads session / MCP 本機連線
