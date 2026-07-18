# part-010 TODO

Design authority: `.beacon/parts/part-010/DESIGN.md`

Open question 定案（探查 crowd-scenario 真實 CLI 後）：
- crowd-scenario CLI `--domain` 只接受內建 3 packs（stock_tw/product_launch/
  software_migration），且**不改 vendored 原始碼**。故個人 domain packs 落地為
  **core/scenario.py 的 scenario templates**：把 Metatron 狀態 bucket 化後，映射到
  最貼近的既有 pack + 以 `--metrics` 餵 ordinal 化後的軸值。零修改 vendored、
  保留 subprocess 隔離。
- CLI 契約（實測）：`python -m crowdscenario run --domain <pack> --symbol <s>
  --scenario <label> --metrics '{...}' --n <k>` → JSON（含 non_authoritative /
  synthetic_population / crowd_consensus / narrative_md / persona_samples）。
- 演練觸發：先純使用者要求（CLI）；advisor 觸發列後續。

## SLICE Map

### part-010-slice-000: scenarios 專區 + bucket 化 firewall + seed 建構

Status: done (2026-07-19; snapshot: `.beacon/done/part-010/part-010-slice-000-done-current.md`)
789 tests 綠(基線 778 + 11);bucket firewall + non_authoritative 存放 manual QA 通過。

Goal: vault/scenarios/ 專區 + 確定性 bucket 化（raw 數字 → ordinal，firewall）+
ScenarioRequest 建構 + non_authoritative 儲存。全確定性、無 subprocess、無 LLM。

Outcome: `scenario.bucketize(value, thresholds)` 把原始數字轉 ordinal bucket；
`scenario.build_request(...)` 產不含 raw number 的請求；`scenario.store_narrative(...)`
把報告存 vault/scenarios/ 標 non_authoritative；三者純函數/確定性可測。

Candidate scope:
- [x] `core/scenario.py`：`bucketize`（確定性，拒非數字）+ `ordinal_axis` +
      `ScenarioRequest`/`build_request`（**拒 raw number**，只收 ordinal bucket）+
      `store_narrative`（vault/scenarios/，non_authoritative，缺標記拒絕）
- [x] `core/ltm.py`：ALLOWED_SUBDIRS + init_vault 加 'scenarios'
- [x] tests：bucketize 邊界/確定性/拒非數字、build_request 拒 raw number、
      store non_authoritative + 不進 semantic + 缺標記拒絕（11 tests）

Files-scope: core/scenario.py, core/ltm.py, tests/test_scenario.py,
.beacon/parts/part-010/**, .beacon/CURRENT.md

Forbidden scope:
- subprocess / vendored 呼叫（slice-001）
- 個人 scenario templates（slice-002）
- LLM
- 讓 scenario 進 semantic 事實層 / facet 證據（硬規則）

Verification target:
- Unit: `python -m pytest tests/test_scenario.py -q`
- Regression: `python -m pytest tests/ -q`
- Manual QA: bucketize 幾個真實值 → ordinal；store 一筆假 narrative → vault/scenarios 標記正確

Done gate:
- bucket firewall + 存放標記測綠；不污染 semantic；全綠

### part-010-slice-001: vendored crowd-scenario + subprocess adapter

Status: done (2026-07-19; snapshot: `.beacon/done/part-010/part-010-slice-001-done-current.md`)
796 tests 綠(基線 789 + 7,含真 vendored subprocess 冒煙);端到端 manual QA 通過。

Goal: vendored 釘版 crowd-scenario（VENDORED.md）+ subprocess adapter（呼叫 CLI →
解析 CrowdNarrative）+ vault/scenarios 落地 + recall non_authoritative 標記。

Outcome: `scenario.run_rehearsal(request, runner)` subprocess 呼叫
`python -m crowdscenario run ...` → 解析 JSON（non_authoritative/crowd_consensus/
narrative_md/persona_samples）→ store_narrative；crowd-scenario 崩潰 → core 不受影響；
recall 引用 scenario → 帶「模擬/非事實」標記。

Candidate scope:
- [x] `skills/crowd_scenario_vendor/`：vendored clone（pin `1b40712a`；MIT；
      VENDORED.md；零修改黑箱，只 src/+pyproject+LICENSE+README）
- [x] `core/scenario.py`：`run_rehearsal`（runner 注入，預設 subprocess PYTHONPATH
      隔離）→ 解析 JSON → non_authoritative 缺失拒絕 → store；崩潰記 failed event
- [x] `agents/recall.md` + `core/recall.py`：scenario_rehearsal → `_non_authoritative_note`
      強制引用標「模擬演練，非事實/非預測」
- [x] tests：subprocess mock 解析+落地、崩潰隔離、non_authoritative 缺失拒絕、
      recall 標記、**真 vendored subprocess 冒煙**（7 tests）

Files-scope: skills/crowd_scenario_vendor/**, core/scenario.py, core/recall.py,
agents/recall.md, tests/test_scenario_run.py

Forbidden scope:
- 修改 vendored 原始碼（黑箱）
- 個人 templates（slice-002）
- scenario 進 semantic/facet

Verification target:
- Unit: `python -m pytest tests/test_scenario_run.py -q`
- Regression: `python -m pytest tests/ -q`
- Manual QA: 真 vendored subprocess 跑一次內建 pack → 解析報告存 vault/scenarios

Done gate:
- subprocess 解析/落地/容錯/recall 標記測綠；vendored 零修改；全綠

### part-010-slice-002: 個人 scenario templates + CLI 觸發 + 端到端

Status: done (2026-07-19; snapshot: `.beacon/done/part-010/part-010-slice-002-done-current.md`)
807 tests 綠(基線 796 + 11);CLI 真 subprocess 端到端 QA 通過。part-010 三 slice 全數完成。

Goal: 個人 scenario templates（personal_schedule/habit_change/project_portfolio）
映射 Metatron 狀態 → 既有 pack + bucket metrics + `python -m core.scenario` CLI +
端到端。

Outcome: `scenario rehearse <template>` 讀 Metatron 狀態（schedule/tasks/facets）→
bucket 化 → 映射既有 crowd-scenario pack → subprocess 演練 → 報告存 vault/scenarios
標 non_authoritative；recall 引用帶模擬標記。

Candidate scope:
- [x] `core/scenario.py`：三 template（personal_schedule/project_portfolio →
      software_migration；habit_change → product_launch）映射器：讀狀態 →
      bucketize → build_request
- [x] `core/scenario.py`：`main()` CLI（`rehearse <template>`；--db/--vault）
- [x] 觸發：純使用者 CLI（advisor 觸發列後續，不做）
- [x] tests：三 template 映射確定性（firewall 全 0-1 無 raw number）、
      端到端（mock subprocess → vault/scenarios non_authoritative）、CLI 真 subprocess
      （11 tests）
- [ ] Manual QA：真 schedule/tasks → rehearse personal_schedule → subprocess →
      報告存 vault/scenarios，recall 引用帶模擬標記

Files-scope: core/scenario.py, tests/test_scenario_templates.py

Forbidden scope:
- advisor 自動觸發（後續）
- scenario 影響真實狀態（永遠 non_authoritative）

Verification target:
- Unit: `python -m pytest tests/test_scenario_templates.py -q`
- Regression: `python -m pytest tests/ -q`
- Manual QA: 端到端 rehearse → vault/scenarios → recall 標記

Done gate:
- template 映射/CLI/端到端測綠；DESIGN Verification Targets 五條全對應；全綠
