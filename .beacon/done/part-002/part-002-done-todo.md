# part-002 TODO

Design authority: `.beacon/parts/part-002/DESIGN.md`

## SLICE Map

### part-002-slice-001: writer.py + 提案驗證 + 閘門

Status: done (2026-07-13; snapshot: `.beacon/done/part-002/part-002-slice-001-done-current.md`)

Goal: 唯一寫入口:提案信封解析、七條驗證、三層危險閘門、confirm_fn 注入、落地 + events。

Outcome: 合法 schedule_change 提案經 confirm 後落地 DB1;非法/逾時/非互動一律拒絕並記 events。

Candidate scope:
- [ ] `core/proposals.py`:信封 dataclass + schedule_change/task_change payload 驗證
- [ ] `core/writer.py`:apply(proposal, confirm_fn) 全邏輯(§3.1 七條 + §3.2 閘門)
- [ ] 落地:schedule/tasks INSERT/UPDATE + INSERT events(記變更)
- [ ] pytest:驗證通過/攔截各路徑、confirm y/N、非互動 fail-closed

Forbidden scope:
- 任何 LLM 呼叫(writer 是純確定性程式)
- vault 寫入類 proposal_type(classify_note 等——part-003+)

Verification target:
- Unit: `python -m pytest tests/test_writer.py -q`
- Regression: `python -m pytest tests/ -q` 全綠
- Manual QA: 無(純程式邏輯,單元測試覆蓋)

Done gate:
- 七條驗證 + 三層閘門各有測試;全 pytest 綠

### part-002-slice-002: llm.py + subagents.py + schedule 契約

Status: done (2026-07-13; manual QA blocked — 見 snapshot)

Goal: LLM 薄層(OpenAI 相容)+ 子 agent 執行器 + agents/schedule.md 契約。

Outcome: mock LLM 下,一句排程輸入 → 合法 schedule_change 提案 JSON。

Candidate scope:
- [ ] `core/llm.py`:complete()(base_url/key 環境變數、重試 1、JSON 模式含降級)
- [ ] `core/subagents.py`:run(name, inputs) → 讀 agents/<name>.md → complete → 解析提案
- [ ] `agents/schedule.md`:系統 prompt + JSON schema + few-shot(含 rrule 例)
- [ ] pytest(mock complete_fn):正常解析、壞 JSON 重試、再壞拒絕

Forbidden scope:
- 真 LLM 呼叫進 CI 測試(只 mock)
- orchestrator 路由(slice-003)

Verification target:
- Unit: `python -m pytest tests/test_subagents.py -q`
- Regression: 全 pytest 綠
- Manual QA: 設環境變數後手動跑一次真 LLM 解析,檢查提案 JSON

Done gate:
- mock 測試綠;手動真 LLM 一次成功

### part-002-slice-003: agent.py orchestrator + remind job

Status: done (2026-07-13; 真 LLM 手動 QA 待使用者提供 API key — 見 snapshot)

Goal: 入口組裝:agent_runs 記錄、上下文、路由、派工、writer、回覆;`--job remind` 確定性提醒。

Outcome: `python -m core.agent "<自然語言>"` 全流程可用;`--job remind` 到期通知 + rrule 前推。

Candidate scope:
- [ ] `core/agent.py`:invoke(text, trigger, reply_to/confirm_fn) + CLI 入口
- [ ] `--job remind`:§6.6 流程(partial index 查詢、通知 console、reminded_at/rrule 前推)
- [ ] rrule 前推的確定性實作(FREQ=DAILY/WEEKLY 子集即可,part-002 範圍)
- [ ] pytest:mock LLM 全流程、無狀態雙呼叫、remind 單次/重複行程
- [ ] 手動 QA:真 LLM 排程一筆 + remind 觸發

Forbidden scope:
- Discord(part-002.5)
- consolidate job(part-003)

Verification target:
- Unit: `python -m pytest tests/ -q`
- Regression: 28 個既有測試仍綠
- Manual QA: 真 LLM「明天下午兩點開會提前30分提醒」→ 預覽 → y → list 可見;remind 觸發

Done gate:
- Phase 2 gate:兩次獨立呼叫狀態僅經 DB1;提案被 writer 攔截測試通過
