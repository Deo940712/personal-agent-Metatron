# part-003.2 DESIGN

## Goal

以真實 workload 實證比較記憶方案 A(現況,已實作)與 B(Task Capsule),產出一份
繁體中文 ECC 技術評估與可重現的 A/B 實驗證據,最後給出「保持 A / 提案 B 設計 /
實驗無效」的建議。**本 PART 不採用 B/C/D、不修改正式 DB1 schema、不改 runtime**;
只在隔離、可丟棄的 SQLite 原型上量測。

Work plan authority: `.omo/plans/ecc-task-capsule-experiment.md`
Contract authority: `docs/MEMORY-zh.md` §§1,2,5,7,10(MEM-01/06/07/08/15/17)

## 前置 gate(已滿足)

`part-006-slice-001` 已完成並歸檔(`.beacon/done/part-006/part-006-slice-001-done-current.md`):
統一 `application.invoke` 入口、pending 原子認領、recall 嚴格 found/not_found——
context 恢復的安全基線就緒。

## Required Decision Model(從 work plan 凍結)

1. **Prototype B, do not adopt B**:交付證據與建議;正式 schema/API 不因原型成功而變。
2. **Isolated store only**:所有 CLI/test 需明確非正式 DB 路徑或 temp directory;
   拒絕 `config.STATE_DB`、`VAULT_PATH`、`INDEX_DB`、`TRANSCRIPT_DIR` 及 `DATA_DIR` 子路徑。
3. **Task is not session**:`task_id` 跨 run/介面穩定;`source_session_ids` 只是 provenance。
   刪除 session observation 永不刪 capsule/decision。
4. **Minimal typed capsule**:`schema_version, task_id, version, status, goal, constraints,
   decisions, completed, failed_attempts, open_loops, next_action, evidence_refs,
   authority_versions, created_at, updated_at`。無 chain-of-thought、無完整聊天。
5. **Observations remain observational**:canonical snapshot 帶 source kind/id、擷取時間、
   authority class、版本/hash、payload;只有 deterministic validation 可 promote 進 revision。
6. **Optimistic concurrency**:expected-version CAS + idempotency key + append-only revision
   audit + one current materialized row(MEM-15)。
7. **Bounded historical injection**:exact task match、bounded budget、固定欄位優先序、
   historical-only wrapper、動作前重查權威(MEM-08)。
8. **Fair A/B**:兩臂同一權威 fixture 與 expected answer;只有 B 額外拿 prior capsule;
   deterministic scoring,不需 LLM。
9. **Pre-registered gate**:B 須通過全部 hard safety/correctness;七 workload 至少四個在
   median authority reads 或 assembled context 改善 ≥15%;aggregate p95 ≤110% A。
   否則保持 A(MEM-17)。這些是實驗門檻,非永久 SLO。
10. **No C/D escalation**:B 成功只授權後續 production-design proposal;C 需 B 後仍有殘留
    重複檢索;D 需獨立 C-vs-D 實驗。

## Integration boundary

- 獨立 package `experiments/task_capsule/`;production code 不得 import;無 runtime hook。
- 不改 `core/stm.py` schema、`core/application.py`、`core/agent.py`、`core/chat.py`、
  Discord、MCP、scheduled jobs。
- LLM 不得取得 raw SQL、DB connection、任意檔案寫入或裸 `writer.apply`(MEM-12/13)。

## Verification Strategy

- TDD with pytest;真實 SQLite temp files,不 mock 交易/鎖。
- Static:`ruff check experiments/task_capsule tests`、改動 Python 檔 LSP 零 error;無新 runtime dep。
- Reproduction:空 temp output 跑實驗 CLI 兩次,同版本 deterministic。
- Safety:對 production 路徑、task mismatch、stale version、corrupt row、injected stale
  authority 跑負向 probes,全部 fail closed。
- Beacon:`UnitTestCore.ps1 -Part part-003.2 -Slice slice-001`。

## Slice Map

### part-003.2-slice-001:ECC 評估 + 隔離 Task Capsule A/B 實驗

實作 work plan Todos 2-15:ECC 報告 + typed model + isolated store + context assembly
+ metrics/thresholds + fixtures + A/B runner + 執行 + 報告定稿 + Beacon 驗證/稽核/歸檔。
Done gate 見 work plan Success criteria。

## Risks

- A/B 不公平 → 同 fixture bundle、frozen scoring、paired AB/BA 順序。
- 過期 capsule 污染權威 → stale-by-default、動作前重查、historical-only wrapper。
- 實驗誤碰正式資料 → production-path 拒絕閘門、disposal 只刪已驗證 experiment root。
- 無 LLM 使量測是 proxy → 報告 threats-to-validity 明示 authority reads/bytes 是近似非實測。

## Open Questions

無。work plan 已 decision-complete 且經使用者核准;審查由 build agent 直接對照
MEMORY-zh.md/PLAN.md/config.py 完成(外部審查 agent 逾時,記錄於 draft)。
