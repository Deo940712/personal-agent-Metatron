# part-003.1 DESIGN

## Goal

建立一份中英文等價、可機器驗證的記憶架構契約。文件必須把「已實作的儲存與
檢索系統」和「仍在評估的多層 context 設計」分開，並說清楚子 agent 工具自主性、
orchestrator 控制面及 deterministic writer commit 邊界。

本 PART 只修改文件與文件驗證器，不變更 runtime、schema、dependency 或 public API。

## Authority and Status Vocabulary

- `docs/MEMORY-zh.md` / `docs/MEMORY-en.md`：記憶契約權威，章節拓撲完全一致。
- `ARCHITECTURE.md`：系統級摘要與決策狀態；不得複製整份契約。
- `docs/TOOLS.md`：capability、agent、interface、permission、storage 配對權威。
- `[IMPLEMENTED]`：目前程式與資料模型已存在且可驗證。
- `[CANDIDATE]`：可比較的架構選項，未授權實作。
- `[PLANNED]`：已有其他 PART/slice 的明確計畫，但尚未完成。
- `[NON-GOAL]`：確定排除；不得把「尚未定案」誤標成 NON-GOAL。

## Required Decision Model

文件必須分開四個概念：

1. storage roles：DB1／vault／transcript／index。
2. retrieval stages：index-first／FTS／vector／rehydrate。
3. context continuity：一次 run、跨 run 任務 checkpoint、task-scoped warm set。
4. agent-managed paging：LLM 自主升降 STM／MTM／LPM。

多層 context 使用 A/B/C/D 比較，不先定案：

| 方案 | 狀態 | 定義 |
|---|---|---|
| A | `[IMPLEMENTED]` | 無狀態 invocation + 權威儲存重讀 + 按需檢索 |
| B | `[CANDIDATE]` | A + 結構化 Task Capsule/checkpoint |
| C | `[CANDIDATE]` | B + deterministic task-scoped warm set |
| D | `[CANDIDATE]` | C + LLM 自主 paging；須以實測證明優於 C |

決策順序固定為 A→B→C→D；前一級沒有可重現問題時，不升級複雜度。

## Tool and Mutation Boundary

- 「可呼叫 capability」不等於「可直接寫共享儲存」。
- 子 agent 可依靜態 allowlist 直接呼叫 scoped `read`、`propose`，以及架構明定的
  `auto_apply` capability；不必讓 orchestrator 逐次代轉。
- `auto_apply` 仍必須走 deterministic validation/commit path。
- LLM 永不取得 raw SQL、DB connection、任意 vault/file write 或裸 `writer.apply`。
- Orchestrator 是 control plane；capability gateway + writer 是 data plane。
- 高風險 mutation 繼續 preview→confirm→writer，逾時 fail-closed。

## Normative Document Topology

兩份記憶文件必須有完全相同的編號 H2：

1. Contract and decision status
2. Identity, lifetime, and authority
3. Implemented storage and lifecycle
4. Implemented retrieval and context assembly
5. Multi-layer memory options under evaluation
6. Agent tools, isolation, and mutation authority
7. Trust, provenance, conflict, and correction
8. Concurrency, idempotency, observability, and recovery
9. Probe-verified implementation reference
10. Evaluation plan and decision gates

每份文件各包含 `MEM-01`～`MEM-17`，每個 ID 恰好一次。

## Invariant Set

- MEM-01 core invocation 無狀態；UI session 不是權威記憶。
- MEM-02 storage authority 依 domain 分工，不宣稱單一全域 SoR。
- MEM-03 transcript 原始證據 append-only。
- MEM-04 index 可重建且不持有唯一資料。
- MEM-05 蒸餾筆記保留 source_ids 回水路徑。
- MEM-06 compaction/摘要不自動成為權威狀態。
- MEM-07 多層 context 尚未定案，A/B/C/D 狀態不得誤標。
- MEM-08 Task Capsule 若採用，只存結構化 checkpoint，不存 chain-of-thought。
- MEM-09 warm set 若採用，限 task scope 且可由權威資料重建。
- MEM-10 LLM 自主 paging 必須實測優於 C 才能採用。
- MEM-11 capability call 與 shared-state mutation authority 分離。
- MEM-12 LLM 子 agent 不取得 raw storage write primitive。
- MEM-13 共享 mutation 經 deterministic writer boundary 驗證。
- MEM-14 需確認操作逾時 fail-closed。
- MEM-15 並行更新若未來存在，必須有版本／原子 claim／冪等保護。
- MEM-16 外部不可信資料不能成為指令或未驗證事實。
- MEM-17 架構升級由真實任務指標觸發，不以「看起來先進」為理由。

## Allowed Files

與 `.beacon/CURRENT.md` Allowed Scope 完全相同。

## Forbidden Changes

- runtime/schema/API/dependency 變更。
- 把 B/C/D 寫成已採用，或把 D 永久判死。
- 新增常駐 conversation core、知識圖譜、第二個 writer 或 direct DB write。
- 把 `application.invoke`、atomic pending claim、directives/MCP 寫成已完成。

## Verification Strategy

Tests-after：新增標準函式庫文件檢查器，驗證 UTF-8、章節拓撲、invariant 唯一性、
status vocabulary、本地連結與絕對路徑；再跑全 pytest 與 strict UnitTestCore。

## Done Gate

雙語規格與所有入口摘要無矛盾；A/B/C/D、工具權限及 writer 邊界清楚；既有平台
實證沒有遺失；正向與負向文件探針、全測試均通過。
