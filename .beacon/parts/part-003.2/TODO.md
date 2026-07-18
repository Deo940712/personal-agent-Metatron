# part-003.2 TODO

Design authority: `.beacon/parts/part-003.2/DESIGN.md`
Work plan authority: `.omo/plans/ecc-task-capsule-experiment.md`

## SLICE Map

### part-003.2-slice-001:ECC 評估 + 隔離 Task Capsule A/B 實驗

Status: done (2026-07-16; snapshot: `.beacon/done/part-003.2/part-003.2-slice-001-done-current.md`)
判定:retain_a(0/7 qualify;B p95 超預算)。531 tests 綠、UnitTestCore PASS、6 對抗探針通過。

Goal: 以隔離可丟棄 SQLite 原型,用七個真實 workload 公平比較 A(現況)與 B(Task
Capsule),產出繁體中文 ECC 技術評估與可重現 A/B 證據,回「保持 A / 提案 B 設計 /
無效」的建議。不採用 B/C/D、不改正式 schema/runtime。

Candidate scope(對應 work plan Todos 2-15):
- [x] Todo 2:`docs/ECC-TASK-CAPSULE-REPORT-zh.md` + `.beacon/verification/CheckTaskCapsuleExperiment.py`(5 tests)
- [x] Todo 3:`experiments/task_capsule/models.py` + tests(28 tests,typed capsule/observation)
- [x] Todo 4:`experiments/task_capsule/paths.py` + tests(19 tests,production-path 拒絕 + disposal)
- [x] Todo 5:`tests/fixtures/task_capsule/` 七 workload corpus + 驗證 tests(13 tests)
- [x] Todo 6:`experiments/task_capsule/metrics.py` + `experiment_spec.json` + tests(21 tests,凍結門檻)
- [x] Todo 7:`experiments/task_capsule/store.py` + migrations + tests(13 tests,CAS/idempotency/revision)
- [x] Todo 8:`experiments/task_capsule/context.py` + tests(13 tests,bounded historical + authority revalidation)
- [x] Todo 9:runner A-arm(stateless reconstruction)+ tests(與 B 同檔 24 tests)
- [x] Todo 10:`experiments/task_capsule/artifacts.py` + tests(11 tests,atomic write + resumable)
- [x] Todo 11:`experiments/task_capsule/checkpoint.py` + tests(12 tests,deterministic promotion)
- [x] Todo 12:runner B-arm(capsule hints + 重查權威)+ tests
- [x] Todo 13:`experiments/task_capsule/__main__.py` CLI + 執行 A/B + `.omo/evidence/` 證據(9 tests,實跑 retain_a)
- [x] Todo 14:報告定稿(量測 + threats-to-validity「無 LLM = proxy」;final checker 過)
- [x] Todo 15:Beacon 驗證 + 對抗式稽核(6 探針)+ 歸檔 + CURRENT 回 planning-only

Files-scope: experiments/task_capsule/**, tests/test_task_capsule_*.py,
tests/fixtures/task_capsule/**, docs/ECC-TASK-CAPSULE-REPORT-zh.md,
.beacon/verification/CheckTaskCapsuleExperiment.py, .beacon/verification/manifest.json,
.beacon/parts/part-003.2/**, .beacon/done/part-003.2/**, .omo/evidence/**

Forbidden scope:
- production DB1 schema/table/index、core/stm.py schema、core/application.py、
  core/agent.py、core/chat.py、Discord、MCP、scheduled jobs
- production code import experiments/task_capsule;SessionStart/PreCompact/Stop hook
- config.STATE_DB/VAULT_PATH/INDEX_DB/TRANSCRIPT_DIR/DATA_DIR 寫入
- 完整 chat/transcript/chain-of-thought;raw session export;session 當 task authority
- embeddings/RAG/warm set/STM-MTM-LPM paging
- 看結果後改 workload/expected/metric/門檻;因 B 通過就改正式架構;C/D 實作
- git commit/stage/push/reset/checkout/restore/stash/clean

Verification target:
- Unit: `python -m pytest tests/test_task_capsule_models.py tests/test_task_capsule_store.py tests/test_task_capsule_context.py tests/test_task_capsule_runner.py -q`
- Regression: `python -m pytest tests/ -q`(既有 360 全綠)
- Reproduction: 空 temp output 跑實驗 CLI 兩次 deterministic
- Beacon: `UnitTestCore.ps1 -Part part-003.2 -Slice slice-001`

Done gate:
- 全部 task_capsule 邊界/對抗測試綠;既有回歸全綠;實驗證據可重算;報告 final checker 過;
  part-003.2 歸檔;CURRENT 回 planning-only,B 採用留作使用者未來決策
