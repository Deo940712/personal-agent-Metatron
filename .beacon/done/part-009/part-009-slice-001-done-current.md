# part-009-slice-001 — reflect + advice 生成 + 防疲勞(done 2026-07-19)

Snapshot of CURRENT at completion.

## Goal(達成)

LLM reflect(有變化才呼叫)+ advice 提案生成(過欄位級驗證)+ 四重防疲勞。

## Delivered

- `agents/advisor.md`(Cassiel):reflect 契約——讀 world-diff + facets → 克制建議;
  evidence_ids 只能用 diff 中真實 id(可空);保守優先級;無值得建議 → 空
- `core/advisor.py`:
  - `reflect(diff, db, _api)`:quiet 短路(防呆零 LLM)→ LLM → `_validate_advice`
    欄位級驗證(priority enum/文字非空/evidence 屬實/ttl 界內/dedup_key 非空)→
    逐條跳過不合格、記 events
  - `tick(db, now_ts, _api)`:expire_due → observe → quiet 短路推 baseline /
    reflect → 配額+去重過濾 → advice_add(邏輯時間 created_at)→ 推 baseline;
    LLMError → baseline 不推進
  - `_build_reflect_prompt` / `_diff_evidence_ids`(確定性)
- `core/stm.py`:advice_add 加 created_at 參數(tick 邏輯時間一致,配額/去重視窗正確)
- `config.py`:ADVICE_DAILY_QUOTA=3 / DEDUP_WINDOW_DAYS=3 / DEFAULT_TTL_DAYS=3 /
  PUSH_MIN_PRIORITY=medium(保守初值)
- `tests/test_advisor_reflect.py`:10 tests(quiet 零 LLM/reflect 短路/產合格 advice/
  空 evidence 允許/五類驗證拒絕/丟壞留好/配額/去重/過期清理/reflect 失敗不推 baseline)

## Verification

- Unit: `python -m pytest tests/test_advisor_reflect.py -q` → 10 passed
- Regression: `python -m pytest tests/ -q` → **716 passed**(基線 706 + 10)
- Manual QA(實跑):空世界 tick → quiet + 零 LLM 呼叫;逾期任務 tick → reflect 產
  1 條 advice;`advices list` 顯示 high priority 建議。

## DESIGN Verification Targets 對照(前四條)

- [x] world-diff 無重要變化 → quiet tick,不呼叫 LLM(斷言零呼叫)
- [x] 有變化 → 產 advice 帶 observation/suggestion/evidence_ids/expires_at
- [~] advice 的 action 落地走 confirm(slice-002:action 目前不接線)
- [x] reflect 失敗 → baseline 不推進
- [x] 每日配額/去重/過期生效

## Notes

- 配額/去重視窗以 tick 的邏輯 now_ts 為準(advice_add created_at 參數化)——
  避免牆鐘與測試時間錯位,也讓 tick 完全可重放。
- advice 的 action(一鍵提案)欄位 schema 已在 DB(actions)但 slice-001 不產不接線;
  action→confirm 落地是 slice-002。
