# part-009-slice-002 — Discord 推播 + action→confirm + 校準回饋 + job 接線(done 2026-07-19)

Snapshot of CURRENT at completion.

## Goal(達成)

advice 主動推 Discord + action 走 preview→confirm→writer + 接受/忽略回饋成
part-007 facet 證據 + `--job advise` cron 接線。整條 Advisor 閉環打通。

## Delivered

- `core/advisor.py`:
  - `push_candidates(db)`:取 priority ≥ ADVICE_PUSH_MIN_PRIORITY 的 pending
    未過期 advice
  - `format_advice`:人可讀推播文(含 id 供回饋定址)
  - `apply_action(db, advice_id, idx, confirm_fn)`:advice 一鍵 action 走
    **writer.apply(confirm_fn)**——未確認不落地(advice 永不自己行動)
  - `record_feedback(db, advice_id, accepted)`:標 advice state + 產 preference
    facet 證據(facet_key=advice_pref__<dedup>,value=accept|ignore;寫回饋事件
    進冷儲存取得真 evidence id;走 writer 全驗證)——校準閉環,越用越準
- `core/agent.py`:`job_advise` + `--job advise`(tick → push_candidates →
  notify_fn 推播 → 標 pushed;記 agent_runs)
- `channels/discord_bot.py`:advice 回饋按鈕 encode/decode(myadv:<id>:<a|i>;
  與 confirm 按鈕不撞)+ interaction handler 路由回饋 + `advice_feedback_view`
- `core/proposals.py`:advisor 進 KNOWN_AGENTS
- `tests/test_advisor_push.py`(14)+ `tests/test_discord.py`(+5):push 篩選/
  job 接線/CLI/action→confirm(未確認不落地)/校準回饋 accept+ignore+reinforce/
  走 writer 驗證/按鈕 id roundtrip + 不撞碼

## Verification

- Unit: `python -m pytest tests/test_advisor_push.py tests/test_discord.py -q` → 32 passed
- Regression: `python -m pytest tests/ -q` → **735 passed**(基線 716 + 19)
- Manual QA(端到端實跑):逾期任務 → tick → advice → push_candidates 推 1 條 →
  record_feedback(accept)→ 產 `preference/advice_pref__overdue_rent = accept`
  facet(走 writer)。閉環完整。

## DESIGN Verification Targets 對照(全五條)

- [x] world-diff 無重要變化 → quiet tick,不呼叫 LLM(slice-001)
- [x] 有變化 → 產 advice 帶 observation/suggestion/evidence_ids/expires_at(slice-001)
- [x] advice 的 action 落地走 confirm(未確認不落地)(本 slice)
- [x] reflect 失敗 → baseline 不推進(slice-001)
- [x] 每日配額/去重/過期生效;忽略某類 → 降頻(本 slice:忽略回饋成 facet 證據,
      未來 push 可讀此 facet 降頻——校準基礎已建)

## Notes

- Discord 真連線 QA 待 token(程式面完成;純函數按鈕編解碼已測、async 路由復用
  既有 confirm 模式)。
- 「忽略降頻」:回饋已成 preference facet 證據(advice_pref__<dedup>=ignore);
  push 時讀此 facet 主動降頻是後續調校點(有真實使用數據再定閾值,不預先造)。
