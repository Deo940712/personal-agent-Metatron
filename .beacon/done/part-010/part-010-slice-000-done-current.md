# part-010-slice-000 — scenarios 專區 + bucket firewall + seed 建構(done 2026-07-19)

Snapshot of CURRENT at completion.

## Goal(達成)

vault/scenarios/ 專區 + 確定性 bucket 化(raw → ordinal firewall)+ ScenarioRequest
建構 + non_authoritative 儲存。全確定性、無 subprocess、無 LLM。

## Delivered

- `core/scenario.py`:
  - `bucketize(value, thresholds)`:raw 數字 → ordinal bucket(確定性;拒非數字)
  - `ordinal_axis(bucket)`:ordinal 標籤 → 0-1 軸值(給 crowd-scenario --metrics;
    未知標籤 → 中點 0.5)
  - `ScenarioRequest` + `build_request`:**firewall——只收 ordinal bucket 標籤,
    拒 raw number**(原始數字永不跨 firewall);軸值全在 [0,1];溯源 buckets 保留
  - `store_narrative`:報告存 vault/scenarios/ 專區,硬標
    source=scenario_rehearsal / non_authoritative=true / synthetic_population=true;
    **缺 non_authoritative → 拒絕落地**;不進 semantic、不進 facet
- `core/ltm.py`:ALLOWED_SUBDIRS + init_vault 加 'scenarios'
- `tests/test_scenario.py`:11 tests(bucketize 邊界/確定性/拒非數字、ordinal 映射、
  build_request 拒 raw number+驗證、store non_authoritative+不進 semantic+缺標記拒絕、
  registry 標記、scenarios 子目錄)

## Verification

- Unit: `python -m pytest tests/test_scenario.py -q` → 11 passed
- Regression: `python -m pytest tests/ -q` → **789 passed**(基線 778 + 11)
- Manual QA(實跑):睡眠 4.7h → severely_low;request metrics 全 0-1 無 raw number;
  假 narrative 存 scenarios/ 標 non_authoritative,不在 semantic/。

## Notes

- 探查 crowd-scenario 真實 CLI(public repo):`--domain` 只接受內建 3 packs
  (stock_tw/product_launch/software_migration),輸出 JSON 含 non_authoritative /
  crowd_consensus / narrative_md / persona_samples。個人 packs 落地為 templates
  (slice-002),映射既有 pack + `--metrics` bucket 值——零修改 vendored。
- subprocess 呼叫 + vendored 是 slice-001;本 slice 零 subprocess。
- 雙重 firewall:Metatron 端 bucket 化 + crowd-scenario contracts.py 自身拒 raw number。
