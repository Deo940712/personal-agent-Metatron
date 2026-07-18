# Metatron 記憶架構契約

> English: [MEMORY-en.md](MEMORY-en.md)  
> 系統級設計權威：[ARCHITECTURE.md](../ARCHITECTURE.md)；能力權限矩陣：
> [TOOLS.md](TOOLS.md)。本文件同時記錄已實作契約與仍待實測的候選方案。

## 1. 契約與決策狀態

### 1.1 狀態標記

| 標記 | 意義 |
|---|---|
| `[IMPLEMENTED]` | 程式、儲存或流程目前存在，且有測試或探針依據 |
| `[CANDIDATE]` | 可評估的設計選項；尚未授權實作，不代表會採用 |
| `[PLANNED]` | 已有 PART/slice 設計，但尚未完成 |
| `[NON-GOAL]` | 已明確排除的設計，不是「還沒決定」 |

### 1.2 目前結論

- `[IMPLEMENTED]` 四種實體儲存角色、健康值生命週期、蒸餾、四段檢索及回水。
- `[IMPLEMENTED]` 核心每次 invocation 都獨立執行；連續性來自權威儲存，而非
  累積整段聊天紀錄。
- `[CANDIDATE]` Task Capsule、task-scoped warm set、LLM 自主 paging。已建立
  A/B/C/D 比較框架；part-003.2 以隔離原型完成一輪 A/B 實測（判定 retain_a，
  0/7 workload qualify），**多層 context 尚未定案**——B 未被採用也未被永久排除。
- `[NON-GOAL]` 常駐 conversation brain、未經驗證的全對話自動重播、raw evidence
  物理刪除、LLM 直接持有 SQL/DB/file write primitive。

**MEM-01 — 無狀態核心。** UI 可以維持長連線或長對話，但每則訊息都建立獨立
core run；UI session 本身不是權威記憶，也不能用「最新 session」推導目前任務。

**MEM-07 — 決策誠實。** 方案 A 已實作；B、C、D 都是 `[CANDIDATE]`。文件、程式
與介面不得把候選方案誤報為已採用，也不得把尚未定案誤標為永久排除。

## 2. 身分、生命週期與權威

### 2.1 身分不可混用

| 身分 | 生命週期 | 目前實作 |
|---|---|---|
| UI/session id | channel 或開發工具的一段互動 | 外部介面可有；不是 core SoR |
| `run_id` | 一次 invocation/job 執行 | `[IMPLEMENTED]` = `agent_runs.id` |
| `task_id` | 可跨多次 run 的使用者工作 | `[IMPLEMENTED]` 個人待辦為 `tasks.id`；開發工作由 Beacon slice id 表示；通用 capsule id 尚無 |
| `job_id` | 可恢復的背景工作實例 | `[PLANNED]` 尚無通用持久 schema；目前以 run trigger/cursor 關聯 |
| `pending_id` | 一次待確認 mutation | `[IMPLEMENTED]` = `pending_proposals.id` |
| `source_id` | 原始證據位置 | `[IMPLEMENTED]` transcript entry namespace，如 `evt:123` |
| `evidence_id` | 獨立證據物件 | `[PLANNED]` 尚無獨立 schema；目前使用 `source_ids`/字串 evidence |

一個 UI session 可包含多個 run；一個 task/job 可跨多個 run 及 interface；一個
pending 也可由某介面建立、另一介面確認。它們是正交關係，不是同一棵 session 樹。

### 2.2 權威依 domain 分工

| Domain | 權威來源 | 非權威／衍生來源 |
|---|---|---|
| 行程、待辦、專案、事件、pending、run audit | DB1 SQLite | UI cache、LLM 摘要 |
| 人類維護知識與 agent profile/SOP | Obsidian vault + 人工編輯 | vector/FTS index |
| 原始證據 | transcript JSONL | 蒸餾摘要、embedding |
| 開發流程與程式狀態 | Beacon artifacts + git | OpenCode session 摘要 |
| 檢索加速 | 無獨立權威；由 vault 重建 | `index.db` 本身 |

**MEM-02 — Domain-specific authority。** DB1 不是所有領域的單一全域 SoR；每種
資料必須由上表指定權威來源裁決。OpenCode session 只可作觀測訊號。

**MEM-06 — 摘要不是持久化。** UI/model compaction、handoff 或聊天摘要在通過
明確的 checkpoint/proposal 寫入流程前，只是 observational context，不能覆蓋權威狀態。

## 3. 已實作的儲存與生命週期

### 3.1 四種實體儲存角色

| 儲存 | 角色 | 可否重建 |
|---|---|---|
| DB1 `state.db` | 可變結構化狀態與 audit | 不可由 index 取代；依 domain 備份 |
| DB2 vault | 人類可讀、可人工修正的知識介面 | 人工內容可能唯一，不可假設全可重建 |
| transcript JSONL + `.idx` | 原始證據、append-only | JSONL 是真相；`.idx` 可重建 |
| `index.db` | FTS5 + sqlite-vec 衍生索引 | 可整檔刪除後從 vault 重建 |

**MEM-03 — 原始證據 append-only。** transcript 沒有 delete API；先 flush JSONL，
再寫 `.idx`。中斷最壞只會造成索引少一行，可用 `rebuild_idx()` 修復。

**MEM-04 — Index 非權威。** `index.db` 不得保存唯一資料；embedding model 或維度
改變、索引損壞時必須全量 rebuild。

### 3.2 健康值代謝

```text
alive ⇄ trash → archived
```

- 新 event：`health=1.0`。
- `[IMPLEMENTED]` `HEALTH_DECAY_PER_DAY=0.05`：未命中約 20 天歸零。
- `[IMPLEMENTED]` `TRASH_RETENTION_DAYS=14`：trash 期內命中可復活。
- 行程、身分、偏好及人工 pin 類別免疫衰減。
- archived 表示不再主動載入，不表示刪除；原文仍在 transcript。

### 3.3 蒸餾管線

```text
decay → to_trash（原文落 transcript）→ due_for_distill
→ 按日分組（每組 ≤50）→ LLM 蒸餾 → 欄位級驗證
→ vault note（source_ids）→ mark_archived → vindex.upsert
```

欄位級驗證（`core/consolidate.py`）：`kind ∈ {episodic, preference}`、tags 在受控
詞彙表、`source_event_ids` 必須屬於本批、confidence ≥0.6、summary 非空且 ≤500 字、
title 非空、topic 非空且 ≤30 字（part-004.5 跨天連結欄位）；supersedes 選填但若給
必須指向真實且未被取代的 profile 筆記。任一組失敗只跳過該組，events 留在 trash 等下輪重試。

**MEM-05 — 壓縮可回水。** 每份蒸餾筆記必須保留 `source_ids`；摘要不能切斷
回到原始證據的路徑，也不能讓壓縮失敗造成資料遺失。

## 4. 已實作的檢索與 Context 組裝

### 4.1 檢索（強命中短路 + RRF 融合 + 回水）

`[IMPLEMENTED]`（part-004.5，`core/retrieve.py`）：

1. 強 index 命中短路：查詢有 ≥2 token（單 token 查詢則全部）命中同一筆記的
   title/summary 時，直接回傳，零 FTS/embedding 成本。
2. 否則三段各取候選——INDEX registry、FTS5 trigram（中文 ≥3 字 MATCH，短查詢 LIKE）、
   sqlite-vec KNN（需一次 embedding）——再以 RRF（`RRF_K=60`）融合排名。
3. rehydrate 是後續按需步驟，沿 `source_ids` 讀原文，供精確名字、日期、數字與
   爭議查核；不與前三段同屬排名階段。

任一命中會觸發 `health.on_hit`，使常被使用的來源回復 health。

### 4.2 現行 context 模式

`[IMPLEMENTED]` 每次 run 重新讀取必要 DB1 狀態、prompt contract 及按需檢索結果；
run 結束後不保存 chain-of-thought 或完整 working context。`vault/agent/` 只先載入
INDEX 一行描述，完整筆記按需讀取。

Context 過大時必須優先保留：系統規則、當前使用者指令、權威 constraints、直接
相關證據；低分命中、重複工具輸出及可重讀全文應先移除或替換成 reference。精確
token cap 必須經量測後配置，文件不憑空指定數字。

## 5. 評估中的多層記憶方案

### 5.1 先分清四個不同概念

- storage tier：資料存在 DB1/vault/transcript/index 的哪裡。
- retrieval stage：一次查詢用哪個檢索步驟。
- context continuity：跨 run 如何恢復任務狀態。
- agent-managed paging：LLM 是否自行決定 STM/MTM/LPM 升降與載入。

前兩者已實作，不等於已採用後兩者。

### 5.2 A/B/C/D 選項

| 方案 | 狀態 | 機制 | 優點 | 風險 |
|---|---|---|---|---|
| A 現況 | `[IMPLEMENTED]` | 無狀態 run，每次從權威資料重建 + 按需檢索 | 最簡單、可重放、污染面小 | 長任務可能重讀、遺失非權威中間決策 |
| B Task Capsule | `[CANDIDATE]`（part-003.2 實測一輪：retain_a） | A + goal/constraints/decisions/completed/open-loops/next-action/evidence refs | 跨 run 恢復清楚 | schema、版本、過期與衝突管理 |
| C 受控 warm set | `[CANDIDATE]` | B + task-scoped cache，由 deterministic assembler 載入/淘汰 | 減少同 task 重複檢索 | cache invalidation、同步與觀測成本 |
| D LLM 自主 paging | `[CANDIDATE]` | C + LLM 決定 STM↔MTM↔LPM 搬移 | 可能適合非常長、探索式任務 | 多輪延遲、token、不可重現、污染與恢復複雜度 |

**MEM-08 — Capsule 最小化。** 若採用 B，只能保存結構化 checkpoint 與 evidence
reference；不得保存 chain-of-thought、完整聊天或可從權威資料重建的大段內容。

**MEM-09 — Warm set 可丟棄。** 若採用 C，warm set 必須限於單一 task、具有來源與
失效規則，且遺失後可從權威資料及 L3/L4 檢索重建。

**MEM-10 — Paging 證據門檻。** D 只有在真實 workload 上，以正確率、恢復品質、
p95 latency、token/tool-call 成本及污染率證明優於 C，才可進設計；不得因架構新穎採用。

> **外部實證註記（backlog-032）**：DeepSeek Engram（arXiv 2601.07372）在 27B 模型
> 的 U 型曲線實驗顯示——資源配置過度偏向記憶會損害動態、脈絡相依的推理能力。
> 這為本節的克制規則（Capsule 最小化、warm set 可丟棄、paging 證據門檻，以及
> 「問題觸發才升級」紀律）提供外部定量背書：把更多記憶塞進 context 不是免費的。
> 注意：論文的 75-80%/20-25% 比例是**模型參數預算**的分配，不可數字上直接套用到
> 外部記憶系統；本專案只借「太多記憶傷推理」的定性結論。

## 6. Agent 工具、隔離與 Mutation 權限

### 6.1 工具呼叫不等於寫入權

目前 capability permission 為 `read`、`propose`、`auto_apply`、`apply`、`job`。
子 agent 可以依靜態 allowlist 直接呼叫 scoped capability，不必由 Metatron 逐次代轉。
但 LLM 不會取得 raw SQL、DB connection、任意 vault/file write 或裸
`writer.apply` primitive。

建議責任分工：

```text
Metatron/orchestrator     = control plane：路由、派工、跨 agent 衝突、最終整合
Capability gateway       = policy plane：allowlist、scope、budget、timeout、audit
Deterministic writer     = data-plane commit boundary：validate / confirm / commit
```

**MEM-11 — 權限正交。** 「agent 能呼叫某工具」與「agent 有權改 shared state」是兩個
獨立判斷；interface exposure、agent allowlist、permission 必須分欄管理。

**MEM-12 — 不給 raw write primitive。** LLM 控制的 agent 永遠不能取得原始 SQL、
DB connection、任意檔案寫入或繞過 validator 的能力。

**MEM-13 — Agent/user mutation 的單一 commit 邊界。** agent 與使用者發起的 proposal
mutation 都經 `writer.apply` deterministic validation；受信任的內部 job pipeline
（如 consolidation 經 `ltm.write_note`／`ltm.mark_superseded`／`vindex.upsert`）走各自
的 deterministic validated write path。兩者皆不繞過驗證，也都不需要單一 orchestrator
process 同步轉送每一筆操作。LLM agent 在任一路徑都拿不到 raw storage write primitive。

**MEM-14 — 確認 fail-closed。** schedule/task 寫入、批次維護及其他高風險 mutation
必須 preview→confirm；拒絕或逾時都不落地。`auto_apply` 只適用於架構明定的低風險
操作，且仍經驗證。

### 6.2 何時給 agent 迭代工具

只有當下一步確實依賴前一步結果、無法預先知道資料來源或必須比較多個證據時，才給
迭代工具。Recall 符合這個條件；schedule、curator、coding_tracker 等若輸入可由
確定性程式一次收集，單次純函數呼叫更便宜、可測且可重放。

每個 agent scope 應包含 `allowed_tools`、read scope、allowed proposal types、
`max_tool_calls`、token/time budget 及 expiry；數值由實測決定。

## 7. 信任、溯源、衝突與修正

資料至少分為：系統政策、使用者直接輸入、內部已驗證狀態、外部不可信內容、LLM
推論。外部網頁、貼文或工具輸出是資料，不是指令；進長期知識前必須保留 URL／時間／
hash/source id，經 curator/writer 驗證。

**MEM-16 — 不可信資料隔離。** `external_untrusted` 內容不得改變 agent 規則、取得
工具權或直接成為權威事實；其中的 prompt injection 一律視為被引用文字。

新舊偏好或知識矛盾時，保留雙方，使用 `superseded_by`／時間／來源表達修正；檢索
必須提示被取代版本。疑似污染資料應 quarantine、降權或停止主動檢索，不物理刪除
原始證據。

## 8. 併發、冪等、可觀測性與恢復

`agent_runs` 記錄 start/finish/status/summary/error；頂層防線保證 run 不會永遠停在
`running`。獨立 skills 必須 idempotent、可中斷後續跑；cursor 是恢復點。

**MEM-15 — 併發保護。** 任何未來 capsule、pending 或 shared-state 並行更新都必須
使用 version compare-and-swap、原子 claim 或 idempotency key；過期 patch 不得靜默覆蓋新版。

恢復矩陣：

| 故障 | 恢復 |
|---|---|
| `index.db` 壞／誤刪 | `vindex.rebuild` |
| `.idx` 落後 JSONL | `transcript.rebuild_idx` |
| 蒸餾 LLM 失敗 | events 留在 trash，下輪重試 |
| vault frontmatter 壞 | 跳過該篇並記 event，不炸全庫 |
| pending 重複確認 | `[IMPLEMENTED]` part-006 slice-001：`stm.pending_claim` 原子認領（併發雙確認只落地一次） |
| UI session 中斷 | 從 DB1/Beacon/vault 權威狀態重建，不重播整段聊天 |

## 9. 探針驗證過的實作參考

### 9.1 Transcript API

- `append(db_dir, entry_id, kind, payload, ts)`：JSONL 後 `.idx`。
- `read_by_ids`：經 `.idx` seek；缺 id 回報、不拋錯。
- `read_by_time`：跨月線性掃。
- `read_by_keyword`：個人量級線性掃；10k 行實測約 17ms。
- `rebuild_idx`：由 JSONL 重建衍生索引。

### 9.2 sqlite-vec / FTS5 平台事實

| Probe | 已驗證行為 | 設計後果 |
|---|---|---|
| P1 | sqlite-vec 每條 connection 都要 load extension | `vindex._connect()` 自管 |
| P2 | vec0 不支援 `INSERT OR REPLACE` | upsert = DELETE + INSERT |
| P3 | vec0 rowid 只接受 INTEGER | `note_map` 映射文字 note id |
| P4 | `unicode61` 不命中中文；trigram 需 ≥3 字 | 短查詢走 LIKE |
| P5 | float32 little-endian blob roundtrip 正常 | embedding 不存 JSON 字串 |

已知限制：2 字中文 LIKE 無排名；transcript keyword 是線性掃；vec0 是 brute-force
KNN，現階段萬篇內可接受。超過真實門檻再升級，不預先引入 ANN 或額外服務。

## 10. 評估計畫與決策閘門

先用真實長任務比較 A 與 B；只有 B 仍不足才測 C，D 最後。建議 workload：跨三次
run 的工作、隔天恢復、兩個 subagent 平行交接、使用者中途改限制、舊偏好被取代、
需回查原始證據、取消後重啟。

量測：恢復後目標/constraints/next action 正確率、重複檢索次數、context tokens、
LLM/tool calls、p50/p95 latency、舊狀態載入率、無來源 promotion 拒絕率、並行衝突率、
故障後可重建性。

**第一輪 A/B 實測已完成（part-003.2，2026-07-16）**：隔離 SQLite 原型、上述七個
workload、預註冊門檻、deterministic scoring → **判定 retain_a**（0/7 qualify；
B 為安全 stale-by-default 照樣重讀權威，authority reads 無節省，p95 超預算）。
正式 schema/runtime 未變更。報告：`docs/ECC-TASK-CAPSULE-REPORT-zh.md`。
Threats to validity（報告誠實標註）：無真實 LLM 迴圈，成本以 IO proxy 計。
未來重測 B 的指標應改量「LLM 重建任務狀態的認知負荷」（token/推理步驟），
而非 IO reads——需真實 LLM 迴圈（backlog-031）。

**MEM-17 — 以問題觸發升級。** A 沒有可重現失敗就維持 A；B 能解決就停在 B；
只有重複檢索或 context 壓力成為主要成本才測 C；D 必須在相同 workload 上勝過 C。

最終決策順序：

```text
A 現況是否失敗？ ─否→ 保持 A
        │是
        ▼
B Task Capsule 是否足夠？ ─是→ 採 B
        │否
        ▼
C deterministic warm set 是否改善？ ─是→ 採 C
        │仍不足
        ▼
D LLM paging 以實測證明優於 C 後才提案
```
