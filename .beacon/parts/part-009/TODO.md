# part-009 TODO

Design authority: `.beacon/parts/part-009/DESIGN.md`

Open question 定案（slice 設計時）：
- advice 存 **獨立 `advices` 表**（有 expires_at/priority/state 語意，不塞 events）。
- tick 頻率：每日晨間為主（cron），slice-000 只做 tick 機制不綁死頻率。
- part-008（Knowledge Scout）未建：world-diff 的「新收知識」訊號欄位留白不接線。

## SLICE Map

### part-009-slice-000: advices 表 + baseline checkpoint + world-diff 讀取器

Status: done (2026-07-19; snapshot: `.beacon/done/part-009/part-009-slice-000-done-current.md`)
706 tests 綠(基線 688 + 18);idempotent 9→10 表升級 + world-diff manual QA 通過。

Goal: DB1 第十表 `advices` + baseline checkpoint（cursors 復用）+ 確定性
world-diff 讀取器。tick 機制成形：無變化 → quiet（零 LLM）；有變化 → 回結構化
diff。全確定性、無 LLM。

Outcome: `advisor.observe(db)` 回 world-diff（新增/異動行程、逾期任務、停滯專案、
作息偏離、失速 goal）；無重要變化回空 diff + quiet=True；baseline 存 cursors
（pipeline='advisor'），推進/不推進可控。

Candidate scope:
- [x] `core/stm.py`：`advices` DDL + CRUD（advice_add/get/list/set_state/
      dedup_recent/count_since/expire_due）+ CLI `advices list`
- [x] `core/advisor.py`：`observe(db, now_ts) -> WorldDiff`（確定性讀取器）：
      新增行程/逾期任務/停滯專案/routine facet 偏離（part-007）/goal facet；
      quiet 屬性短路
- [x] baseline 推進：`advance_baseline(db, ts)` 寫 cursor（壞值 fallback 0）
- [x] tests：advices CRUD + state 機、world-diff 五訊號確定性重放、quiet 判定、
      baseline roundtrip、expire_due（33 tests）

Files-scope: core/stm.py, core/advisor.py, tests/test_advisor.py,
tests/test_schema.py, .beacon/parts/part-009/**, .beacon/CURRENT.md

Forbidden scope:
- LLM reflect（slice-001）
- Discord 推播 / action→confirm（slice-002）
- part-008 知識訊號接線（未建）
- 修改既有九表 schema

Verification target:
- Unit: `python -m pytest tests/test_advisor.py tests/test_schema.py -q`
- Regression: `python -m pytest tests/ -q`
- Manual QA: `python -m core.stm init` idempotent 升級為十表；`advices list` 空表不炸

Done gate:
- world-diff 確定性；quiet/baseline 機制測綠；`init` idempotent；全綠

### part-009-slice-001: reflect + advice 生成 + 防疲勞

Status: done (2026-07-19; snapshot: `.beacon/done/part-009/part-009-slice-001-done-current.md`)
716 tests 綠(基線 706 + 10);quiet 零 LLM + reflect 產 advice manual QA 通過。

Goal: LLM reflect（有變化才呼叫）+ advice 提案生成（過欄位級驗證）+ 四重防疲勞
（配額/去重/過期/優先級）。

Outcome: `advisor.tick(db)` — quiet tick 零 LLM（mock 斷言）；有變化 → reflect
產 advice（observation/suggestion/evidence_ids/expires_at/priority）→ 欄位級驗證
→ 落 advices 表；每日配額/去重/過期生效；reflect 失敗 baseline 不推進。

Candidate scope:
- [x] `agents/advisor.md`（Cassiel）：reflect 契約（讀 world-diff + facets → advice；
      evidence_ids 只能用 diff 中實際 id 可空；保守優先級；無值得建議 → 空）
- [x] `core/advisor.py`：`reflect(diff, db, _api)` LLM 呼叫 + `_validate_advice`
      （priority enum/文字非空/evidence 屬實/ttl 界內/dedup_key）
- [x] `core/advisor.py`：`tick(db, now_ts, _api)`（observe → quiet 短路 /
      reflect → 驗證 → 配額+去重 → advice_add → advance_baseline；LLMError 不推進）
- [x] 防疲勞：每日配額（ADVICE_DAILY_QUOTA）、dedup_key 去重、過期作廢；
      PUSH_MIN_PRIORITY 留 slice-002 用
- [x] tests：quiet 零 LLM、reflect 產合格 advice、五類驗證拒絕、配額、去重、
      過期、reflect 失敗不推 baseline（10 tests）

Files-scope: core/advisor.py, agents/advisor.md, config.py,
tests/test_advisor_reflect.py

Forbidden scope:
- Discord 推播 / action→confirm（slice-002）
- 自動執行 advice 的 action（永遠只產建議）

Verification target:
- Unit: `python -m pytest tests/test_advisor_reflect.py -q`
- Regression: `python -m pytest tests/ -q`
- Manual QA: 塞含異常作息的 events → tick → advices list 出現合理建議；
  無變化日 → tick quiet（零 LLM）

Done gate:
- quiet 零 LLM + reflect 產 advice + 四重防疲勞測綠；DESIGN Verification Targets
  前四條對應；全綠

### part-009-slice-002: Discord 推播 + action→confirm + 校準回饋 + job 接線

Status: planned

Goal: advice 主動推 Discord + action 走 preview→confirm→writer + 接受/忽略回饋
成 part-007 facet 證據 + `--job advise` CLI/cron 接線。

Outcome: `advise` job 跑 tick → medium/high advice 推 Discord DM（含 action 按鈕）
→ 按 action 走既有 pending 確認落地（不繞過 writer）→ 接受/忽略回饋成
preference facet 證據（校準閉環）。

Candidate scope:
- [ ] `core/agent.py`：`job_advise` + `--job advise`（延遲 import advisor）
- [ ] `core/advisor.py`：`push_candidates(db)` 取 medium/high pending advice；
      action 的 proposal 走 application.invoke / writer pending（復用既有確認）
- [ ] `channels/discord_bot.py`：advice DM 推播 + action 按鈕（復用兩階段確認 UI）
- [ ] 校準回饋：advice_set_state(accepted/ignored) → 產 preference facet 提案
      （evidence = advice 的 source；走 writer；忽略某類 → 降頻訊號）
- [ ] tests：job 接線、push 只取 medium/high、action→confirm 落地（未確認不落地）、
      回饋產 facet 證據、忽略降頻
- [ ] Manual QA：塞 events → job advise → Discord 收建議 → 按 action → 確認 → 落地；
      無變化日 → quiet（無推播）

Files-scope: core/agent.py, core/advisor.py, channels/discord_bot.py,
tests/test_advisor_push.py

Forbidden scope:
- advice 自動落地（永遠 confirm）
- 繞過 writer 的任何 action 捷徑

Verification target:
- Unit: `python -m pytest tests/test_advisor_push.py -q`
- Regression: `python -m pytest tests/ -q`
- Manual QA: 端到端 job advise → Discord → action → confirm → 落地（程式面；
  真 Discord 連線 QA 待 token）

Done gate:
- job/push/action-confirm/校準回饋測綠；DESIGN Verification Targets 五條全對應；全綠
