# Vendored: Deo940712/crowd-scenario

- Pinned commit: 1b40712a1eb6b1a09fb49546e48ee86863eaab62
- Cloned: 2026-07-19
- Upstream: https://github.com/Deo940712/crowd-scenario
- License: MIT
- 更新方式:重新 clone + 覆蓋 src/ + 更新本檔 commit
- 本專案**零修改**(黑箱);整合靠 subprocess CLI + PYTHONPATH 指向 src/

## 為什麼 vendored

crowd-scenario 是確定性、無 runtime 依賴、firewall 隔離(contracts.py 硬拒 raw
number 進 seed、輸出硬標 non_authoritative)的情境演練引擎。`core/scenario.py` 用
subprocess 呼叫它,壞掉/漂移不影響 core(同 threads-sync 慣例)。

## 只 vendored 執行期

只保留 `src/` + `pyproject.toml` + `LICENSE` + `README.md`;不含 upstream 的
`.git/.beacon/tests/case_studies/examples`(當黑箱用,不需要)。

## CLI 契約(整合依據,實測 pinned commit)

```
python -m crowdscenario run --domain <pack> --symbol <s> --scenario <label> \
    --metrics '{"axis": 0.0-1.0, ...}' --n <k>
```

- `--domain`:內建 `stock_tw` / `product_launch` / `software_migration`(只這三個;
  個人情境映射到既有 pack,見 `core/scenario.py` templates,part-010-slice-002)
- `--metrics`:JSON;**只有 ordinal bucket 值(0-1)存活進 seed**,raw number 永不跨
  firewall(Metatron 端也先 bucket 化,雙重保險)
- 輸出 JSON:`non_authoritative` / `synthetic_population` / `crowd_consensus` /
  `narrative_md` / `persona_samples[]`

執行需 `PYTHONPATH` 指向 `skills/crowd_scenario_vendor/src`(config 提供路徑)。
