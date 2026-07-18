# DONE: part-003.2-slice-001 ECC 評估 + 隔離 Task Capsule A/B 實驗

Completed: 2026-07-16
Design authority: `.beacon/parts/part-003.2/DESIGN.md`
Work plan authority: `.omo/plans/ecc-task-capsule-experiment.md`

## Goal delivered

以隔離、可丟棄的 SQLite 原型,用七個真實 workload 公平比較記憶方案 A(現況,已實作)
與 B(Task Capsule),產出繁體中文 ECC 技術評估與可重現的 A/B 證據。**未採用 B/C/D、
未修改正式 DB1 schema/runtime。**

## 實驗結論

**判定:`retain_a`**(0/7 workloads qualify;aggregate B p95 超出 110% 預算)。

- 兩臂全部 workload 100% 正確、100% recovery;B 在 stale workload
  (changed_constraint / superseded_preference)也正確——它重讀權威、排除 stale hint。
- A 與 B 的 authority reads 與 assembled bytes **完全相同**,零改善:B 遵守
  stale-by-default 契約,capsule 只是 historical hint,產出前仍重讀全部必需權威。
- B p95 約為 A 的 ~100 倍(額外開啟隔離 SQLite),超出預算。
- 依 MEM-17「A 沒有可重現失敗就維持 A」,**不採用 B**;C/D 更無證據。
- 效度限制:**無 LLM**,authority reads/bytes 是真實 token/tool-call 成本的
  deterministic proxy,非實測;B 的 production 效益是近似而非量測。

報告:`docs/ECC-TASK-CAPSULE-REPORT-zh.md`。
證據:`.omo/evidence/task-13-ecc-task-capsule-experiment-summary.json`(與 `.csv`),
凍結 spec hash `79e29280…`、fixture hash `81c4545f…`,每臂 30 measured samples。

## Verification evidence

- 目標測試(11 個 task_capsule 模組)→ **171 passed**
- `python -m pytest tests/ -q` → **531 passed**(原 360 + 新增 171,零回歸)
- `UnitTestCore.ps1 -Part part-003.2 -Slice slice-001` → PASS
- Ruff:全部 experiments/ 與新測試檔清;LSP:改動 Python 檔零 error
- **對抗式探針(實跑,非僅測試綠)6/6 通過**:
  1. production 路徑(STATE_DB/VAULT_PATH/INDEX_DB/TRANSCRIPT_DIR/DATA_DIR)寫入一律拒絕
  2. 跑完整實驗後 production 檔案 hash 前後不變
  3. stale capsule 不污染 B 答案(B 重讀權威、排除 stale)
  4. checkpoint 拒絕 stale-authority promotion 且不留 partial revision
  5. resume 偵測 fixture/spec drift 並拒絕
  6. dispose 拒絕無 marker 目錄,保全無關檔案
- 實跑 CLI:validate → run(30 samples)→ summarize → dispose 全通,evidence 匯出

## 交付檔案

實作:`experiments/task_capsule/`(models/paths/metrics/fixtures/store/context/
runner/checkpoint/artifacts/experiment/__main__ + migrations + experiment_spec.json)
測試:`tests/test_task_capsule_*.py`(11 檔)
fixtures:`tests/fixtures/task_capsule/`(manifest + 7 workload)
報告:`docs/ECC-TASK-CAPSULE-REPORT-zh.md`
checker:`.beacon/verification/CheckTaskCapsuleExperiment.py`
證據:`.omo/evidence/task-13-ecc-task-capsule-experiment-summary.{json,csv}`

## Boundary retained

- production code 未 import experiments/task_capsule;無 runtime hook;
  正式 DB1 schema/API/runtime 未變。
- 未導入 embeddings/RAG/warm set/LLM paging;未開始 part-006-slice-002/003。
- B 採用留作使用者未來決策 + 獨立 production-design 提案;C/D 未授權。
- 無 git commit/stage/push;dirty worktree 無關變更未動。
