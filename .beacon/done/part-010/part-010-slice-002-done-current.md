# part-010-slice-002 — 個人 scenario templates + CLI + 端到端(done 2026-07-19)

Snapshot of CURRENT at completion.

## Goal(達成)

個人 scenario templates 映射 Metatron 狀態 → 既有 pack + bucket metrics +
`python -m core.scenario` CLI + 端到端。part-010 情境演練鏈路打通。

## Delivered

- `core/scenario.py`:
  - 三 template 映射器(讀 Metatron 狀態 → bucketize → build_request):
    - `personal_schedule` → software_migration(待辦量/逾期量/行程密度)
    - `habit_change` → product_launch(routine 穩定度/goal 數/待辦壓力)
    - `project_portfolio` → software_migration(專案數/blockers/活躍)
  - `rehearse_template(template, db, vault, runner)`:讀狀態 → build → run_rehearsal
  - `main()` CLI:`python -m core.scenario rehearse <template> --db --vault`
  - `_invert` / `_count_upcoming_schedule` 輔助
  - 頂層 import config/stm(修 template 函式的 NameError)
- `tests/test_scenario_templates.py`:11 tests(三 template 映射確定性+firewall
  全 0-1 無 raw number、空狀態仍合法、invert、端到端 mock subprocess、未知 template
  拒絕、**CLI 真 subprocess**)

## Verification

- Unit: `python -m pytest tests/test_scenario_templates.py -q` → 11 passed
- Regression: `python -m pytest tests/ -q` → **807 passed**(基線 796 + 11)
- Manual QA(CLI 真 subprocess 端到端):seed 待辦/逾期/專案 →
  `rehearse personal_schedule` → positive;`rehearse project_portfolio` → neutral;
  兩份報告存 vault/scenarios/,輸出帶「模擬演練·非事實」前綴。

## DESIGN Verification Targets 對照(全五條)

- [x] Metatron 資料 → bucket seed:raw 數字被 bucket 化,seed 不含原始數字(slice-000)
- [x] subprocess 呼叫成功解析 CrowdNarrative;crowd-scenario 崩潰 → core 不受影響(slice-001)
- [x] 輸出存 vault/scenarios/ 標 non_authoritative;不進 semantic/(slice-000/001)
- [x] 個人 domain pack 產出合理 persona 反應鏈(本 slice:三 template 映射既有 pack)
- [x] recall 引用 scenario → 帶「模擬/非事實」標記(slice-001)

## Notes

- 個人 packs 落地為 templates 而非新 DomainPack:crowd-scenario `--domain` 只接受
  內建 3 packs 且不改 vendored;templates 映射到最貼近 pack 的軸 + bucket 值,
  零修改 vendored、保留 subprocess 隔離。好的映射日後可 PR upstream 成真 pack。
- advisor 自動觸發演練列後續(純使用者 CLI 觸發已足;不預先造耦合)。
