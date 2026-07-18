# CURRENT

Status: active
Part: part-009（Proactive Advisor / Subconscious）
Slice: part-009-slice-002 — Discord 推播 + action→confirm + 校準回饋 + job 接線

## Context

part-009-slice-000/001 已完成歸檔（`.beacon/done/part-009/`）：
- slice-000：advices 第十表 + baseline + 確定性 world-diff（706 tests）
- slice-001：reflect + advice 生成 + 四重防疲勞（716 tests）

## Goal

advice 主動推 Discord + action 走 preview→confirm→writer + 接受/忽略回饋成
part-007 facet 證據 + `--job advise` CLI/cron 接線。

Design authority: `.beacon/parts/part-009/DESIGN.md`
Slice map: `.beacon/parts/part-009/TODO.md`

## Allowed scope

- [ ] `core/agent.py`：`job_advise` + `--job advise`（延遲 import advisor）
- [ ] `core/advisor.py`：`push_candidates(db)` 取 medium/high pending advice；
      action 的 proposal 走既有 pending 確認（不繞過 writer）
- [ ] `channels/discord_bot.py`：advice DM 推播 + action 按鈕（復用兩階段確認 UI）
- [ ] 校準回饋：advice_set_state(accepted/ignored) → 產 preference facet 提案
      （evidence = advice 的 source；走 writer；忽略某類 → 降頻訊號）
- [ ] tests：job 接線、push 只取 medium/high、action→confirm 落地（未確認不落地）、
      回饋產 facet 證據、忽略降頻
- [ ] Manual QA：塞 events → job advise → Discord 收建議 → 按 action → 確認 → 落地

Files-scope: core/agent.py, core/advisor.py, channels/discord_bot.py,
tests/test_advisor_push.py, .beacon/parts/part-009/**, .beacon/CURRENT.md

## Forbidden scope

- advice 自動落地（永遠 confirm）
- 繞過 writer 的任何 action 捷徑

## Verification target

- Unit: `python -m pytest tests/test_advisor_push.py -q`
- Regression: `python -m pytest tests/ -q`（基線 716 綠）
- Manual QA: 端到端 job advise → Discord → action → confirm → 落地（程式面；
  真 Discord 連線 QA 待 token）

## Done gate

job/push/action-confirm/校準回饋測綠；DESIGN Verification Targets 五條全對應；全綠。

## Blocked（不影響本 slice 程式面）

- 真 Discord 連線 QA（待 token）
- part-006-slice-003 VPS + Tailscale 真機 QA（backlog-008）
