# ECC 技術評估與 Task Capsule A/B 實驗報告

> part-003.2-slice-001 交付物。權威計畫:`.omo/plans/ecc-task-capsule-experiment.md`;
> 記憶契約權威:`docs/MEMORY-zh.md`。本報告區分「ECC 已驗證的實作」「ECC 的文件建議」
> 「ECC 的限制」與「Metatron 可重用/不可照抄之處」,並記錄本專案 A/B 實驗的實測結果。
>
> **ECC 是參考證據,不是 Metatron 的設計權威。** ECC 只加強 B 的實驗理由;是否採用 B
> 仍以本專案真實 workload 的實測為準(MEM-07/17)。

## 範圍與方法

- 對象:`https://github.com/affaan-m/ECC`(Claude Code 的 SQLite operational state
  store + session handoff 系統)。
- 方法:直接讀 ECC 原始碼分類每個機制為 `已實作` / `文件建議` / `未找到` / `限制`,
  再對照 Metatron 的 A/B/C/D 記憶方案(`docs/MEMORY-zh.md` §5)。
- 本報告不執行 ECC;分類全部來自原始碼閱讀。實驗部分則以隔離、可丟棄的 SQLite
  原型實跑(不採用 B、不改正式 schema)。

## 已實作機制(ECC 原始碼有實作證據)

| 機制 | ECC 原始碼 | 分類 |
|---|---|---|
| SQLite operational state store + migration | `scripts/lib/state-store/migrations.js`、`scripts/lib/state-store/queries.js`、`scripts/lib/state-store/index.js` | 已實作 |
| Canonical `ecc.session.v1` session adapter | `scripts/lib/session-adapters/canonical-session.js` | 已實作 |
| Bounded `SessionStart` context injection | `scripts/hooks/session-start.js` | 已實作 |
| Markdown session handoff + session summary | `scripts/hooks/session-end.js` | 已實作 |
| `PreCompact` / `Stop` checkpoint | `scripts/hooks/pre-compact.js`、`scripts/hooks/session-end.js` | 已實作 |
| Historical-only stale-replay guard + token pressure 監控 | `scripts/lib/transcript-context.js` | 已實作 |

八個原始碼位置見〈來源附錄〉。這些證明 ECC 的 checkpoint / bounded injection /
stale guard 是**可運作的工程做法**,直接支持 Metatron B(Task Capsule)的實驗價值。

## 文件建議(ECC 的做法值得借鏡,但非硬性實作)

- session summary 走明確的 checkpoint 寫入,而非把整段對話當權威——對齊 MEM-06。
- SessionStart 注入有 budget 與 historical 標記——對齊 MEM-08 的 bounded injection。
- decision 綁 session 生命週期(便於清理)——但這也是它的限制(見下)。

## 限制(ECC 原始碼可見的邊界)

- ECC 的 SQLite store 是 **operational state,非 semantic RAG**;它不做向量檢索。
- ECC 用 `sql.js`,mutation 後需 **export 整庫**才能持久化(非增量寫)。
- ECC 的 decision 綁 session/cascade;**session summary 可被 retention 清除**。
- **未找到自主 STM↔MTM↔LPM paging** runtime——ECC 沒有 LLM 自主升降記憶層的機制。
- 因此 ECC 只支持 Metatron 的 **B(Task Capsule)**,不提供採用 C/D 的證據。

## Metatron 對應(可重用 vs 不可照抄)

| ECC 元素 | Metatron 對應 | 採用方式 |
|---|---|---|
| SQLite checkpoint store | B Task Capsule store | 借「結構化 checkpoint」概念;用 native `sqlite3` + CAS,不照抄 `sql.js` 整庫 export |
| SessionStart bounded injection | B context assembly | 借 bounded + historical 標記;強制動作前重查權威(MEM-08) |
| stale-replay guard | B authority revalidation | 借 stale-by-default;Metatron 對每個 authority version/hash 核對 |
| session-owned decision | ✗ 不照抄 | Metatron 的 `task_id` 跨 run/介面穩定,不綁 session(MEM-01) |
| whole-DB export | ✗ 不照抄 | 用 append-only revision + 單 current row,增量寫 |

## A/B 方法

- 隔離、可丟棄 SQLite 原型(`experiments/task_capsule/`),拒絕所有 production 路徑。
- 七個真實 workload(`docs/MEMORY-zh.md` §10):three-run continuation、next-day
  resume、parallel-agent handoff、changed constraint、superseded preference、
  evidence rehydrate、cancel/restart。
- A(現況)只從當前權威重建;B 額外拿 prior capsule 作 historical hint,但仍
  **重讀權威後才作答**(stale-by-default)。兩臂同一 fixture 與 oracle。
- **無 LLM**:correctness/reads/context 皆 deterministic;authority reads 與 assembled
  bytes 是真實 LLM token/tool-call 成本的**近似 proxy,非實測**。
- 每臂 1 warmup(排除)+ 30 measured samples,paired AB/BA 順序(seed 20260716)。
- 凍結門檻(看結果前固定):七 workload 至少四個在 median authority reads 或
  assembled bytes 改善 ≥15%,且 aggregate B p95 ≤ 110% A;否則保持 A。

## 實驗結果

證據:`.omo/evidence/task-13-ecc-task-capsule-experiment-summary.json`（與 `.csv`）。
凍結 spec hash `79e29280…`、fixture hash `81c4545f…`;每臂 30 measured samples。

**判定:`retain_a`**(0/7 workloads qualify;aggregate B p95 超出 110% 預算)。

| workload | A/B 正確 | A reads | B reads | A bytes | B bytes | qualify? |
|---|---|---|---|---|---|---|
| three_run_continuation | ✓/✓ | 3 | 3 | 213 | 213 | 否 |
| next_day_resume | ✓/✓ | 3 | 3 | 215 | 215 | 否 |
| parallel_agent_handoff | ✓/✓ | 3 | 3 | 202 | 202 | 否 |
| changed_constraint | ✓/✓ | 2 | 2 | 185 | 185 | 否 |
| superseded_preference | ✓/✓ | 2 | 2 | 190 | 190 | 否 |
| evidence_rehydrate | ✓/✓ | 3 | 3 | 278 | 278 | 否 |
| cancel_restart | ✓/✓ | 2 | 2 | 195 | 195 | 否 |

- **正確性/恢復**:兩臂全部 workload 100% 正確、100% recovery。B 在 stale workload
  (changed_constraint / superseded_preference)也正確——因為它重讀權威、排除 stale
  hint,沒有沿用舊 constraint/偏好。
- **成本 proxy**:A 與 B 的 authority reads 與 assembled bytes **完全相同**,零改善。
  原因:B 遵守 stale-by-default 契約,capsule 只是 historical hint,產出前仍重讀
  全部必需權威(MEM-08)。因此在正確性優先的重建下,capsule 沒有省下任何權威讀取。
- **延遲**:B 的 p95 約為 A 的 ~100 倍(A aggregate p95 ≈ 30.6µs,B ≈ 3.08ms),
  因 B 額外開啟隔離 SQLite capsule store。這超出 110% 預算。

## 建議

- **保持 A(retain_a)。** 在本專案的七個真實 workload、deterministic 正確性優先的
  重建下,B(Task Capsule)相對 A 沒有可測量的成本節省,且引入 SQLite 開啟延遲。
  依 MEM-17「A 沒有可重現失敗就維持 A」,不採用 B。
- **這不否定 B 的工程正確性**:B 的 store(CAS/idempotency/append-only revision)、
  context assembly(bounded/historical)、checkpoint(deterministic promotion)全部
  通過測試與對抗探針。結論是「在當前量測框架下 B 無淨益」,而非「B 有 bug」。
- **B 可能有益的前提(未來若要重測)**:當「重讀權威」本身昂貴(真實 LLM
  token/tool-call、遠端 I/O、大型 context 組裝)且 capsule 能安全跳過部分重讀時,
  B 才可能勝出。這需要真實 LLM 迴圈,而非本實驗的 deterministic proxy。
- **不升級 C/D**:B 未通過 gate,更無證據支持 C(warm set)或 D(LLM paging)。
  任何未來採用 B 仍需使用者另行決策 + 一份獨立的 production-design 提案。

## Threats to validity（效度限制）

- **無 LLM = proxy,非實測**:本實驗**無 LLM**參與;authority reads 與 assembled
  bytes 是真實 LLM token/tool-call 成本的 deterministic **近似 proxy**。B 的實際
  production 效益(若有)是被近似,不是被量測。任何採用提案都必須承認這個 gap。
- **A/B 重建等價**:為公平與安全,B 的 reconstructor 與 A 相同(都重讀權威),
  這在設計上就使「reads/bytes」兩指標趨同。真正能區分 A/B 的是「是否允許信任
  capsule 而跳過重讀」——但那與 stale-by-default 契約衝突,本實驗刻意不做。
- **合成 fixture**:七 workload 是去識別化合成情境,非真實長任務軌跡;成本分佈
  可能與真實使用不同。
- **延遲量測含 SQLite 開啟**:B p95 包含每次開啟 capsule DB 的固定成本;真實系統
  可能重用連線,絕對延遲會較低,但相對 A 仍有額外 I/O。

## 來源附錄

ECC 已實作證據(逐一由原始碼查核):

- https://github.com/affaan-m/ECC/blob/main/scripts/lib/state-store/migrations.js
- https://github.com/affaan-m/ECC/blob/main/scripts/lib/state-store/queries.js
- https://github.com/affaan-m/ECC/blob/main/scripts/lib/state-store/index.js
- https://github.com/affaan-m/ECC/blob/main/scripts/lib/session-adapters/canonical-session.js
- https://github.com/affaan-m/ECC/blob/main/scripts/hooks/session-start.js
- https://github.com/affaan-m/ECC/blob/main/scripts/hooks/session-end.js
- https://github.com/affaan-m/ECC/blob/main/scripts/hooks/pre-compact.js
- https://github.com/affaan-m/ECC/blob/main/scripts/lib/transcript-context.js
