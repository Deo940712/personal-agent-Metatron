# CURRENT

Status: planning-only
Part: (none active)
Slice: (none promoted)

## Context

part-011（收尾接線 + 文件 + 回歸測試）全三 slice 完成並歸檔至
`.beacon/done/part-011/`：
- slice-000：作息迴圈接線（死程式碼 extract_routine 復活；completed 事件 →
  routine facet → advisor 偏離 → 建議）
- slice-001：advisor 校準降頻 + world-diff new_knowledge 訊號（防注入 count-only）
- slice-002：文件同步（part-010 已實作）+ golden queries 回歸（backlog-007）

**所有 part（001-011）完成。852 tests 綠。** 自適應助理層四塊到齊且跨 part 迴圈
已接線閉環；文件與程式碼對齊；記憶檢索有 golden queries 回歸防護。

## Next candidate (NOT promoted — awaits user gate)

- 全部為 gate-locked / 環境依賴，無立即可執行工作：
  - backlog-025 cross-encoder rerank（觸發：golden queries 出排名問題）
  - backlog-026 per-category 衰減（觸發：真實使用 1-2 月有數據）
  - backlog-017 librarian（觸發：vault 有量）
  - backlog-028 MiroFish part-011（觸發：真實大型模擬需求）
  - backlog-029 AgentSpec registry（觸發：多新 agent 型別）

## Blocked（等使用者環境）

- 四批真 QA：LLM key / Discord token / threads session / MCP 本機連線
- part-006 VPS + Tailscale 真機 QA（backlog-008）
- 真網路抓取 QA（scout 真 RSS 來源）
