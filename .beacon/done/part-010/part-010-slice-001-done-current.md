# part-010-slice-001 — vendored crowd-scenario + subprocess adapter(done 2026-07-19)

Snapshot of CURRENT at completion.

## Goal(達成)

vendored 釘版 crowd-scenario + subprocess adapter + vault/scenarios 落地 +
recall non_authoritative 標記。

## Delivered

- `skills/crowd_scenario_vendor/`:vendored clone(pin commit
  `1b40712a...`;MIT;VENDORED.md)——只保留 src/+pyproject+LICENSE+README,
  **零修改黑箱**;實測 subprocess 跑通(確定性、無網路)
- `config.py`:CROWD_SCENARIO_SRC(PYTHONPATH 路徑)+ SCENARIO_DEFAULT_N=24
- `core/scenario.py`:
  - `_subprocess_runner`:subprocess 呼叫 `python -m crowdscenario run`
    (PYTHONPATH 指 vendored src;timeout 60s;失敗 → ScenarioError)→ 解析 JSON
  - `run_rehearsal(request, vault, runner, db, ts)`:runner 注入(預設 subprocess,
    測試 mock)→ 演練 → non_authoritative 缺失拒絕落地 → store_narrative;
    崩潰記 failed event、core 不受影響
- `core/recall.py` + `agents/recall.md`:讀到 scenario_rehearsal /
  non_authoritative 筆記 → 標 `_non_authoritative_note`,契約強制引用時標
  「模擬演練,非事實/非預測」
- `tests/test_scenario_run.py`:7 tests(subprocess mock 解析+落地、崩潰隔離+
  failed event、non_authoritative 缺失拒絕、壞 JSON shape、recall 標記+正常筆記不標、
  **真 vendored subprocess 冒煙**)

## Verification

- Unit: `python -m pytest tests/test_scenario_run.py -q` → 7 passed(含真 subprocess)
- Regression: `python -m pytest tests/ -q` → **796 passed**(基線 789 + 7)
- Manual QA(真 subprocess 端到端):software_migration 演練 → consensus=negative /
  non_authoritative=true → 存 scenarios/(不在 semantic/)→ recall 標模擬。

## Notes

- crowd-scenario CLI 需 pack 的**全部軸**(software_migration = breaking_severity/
  migration_effort/value_gain);缺軸 exit 2。templates(slice-002)按 pack 補齊軸集。
- vendored 只 src/(不含 .git/tests/case_studies);subprocess PYTHONPATH 隔離,
  crowd-scenario 崩潰/漂移不影響 core。
- 雙重 firewall + 雙重 non_authoritative:Metatron bucket 化 + store 拒未標記;
  crowd-scenario contracts.py 也自帶。
