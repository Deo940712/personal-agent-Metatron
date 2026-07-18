# part-007-slice-000 — facets 資料層 + stability detector(done 2026-07-19)

Snapshot of CURRENT at completion.

## Goal(達成)

DB1 第九表 `profile_facets` + stm CRUD/CLI + stability detector 純函數。

## Delivered

- `core/stm.py`:profile_facets DDL(partial unique active index——修正原設計
  UNIQUE(class,key,state) 的 supersede 歷史撞約束問題,DESIGN 已同步註記)+
  facet_get/facet_get_active/facet_list/facet_insert/facet_touch_evidence/
  facet_promote/facet_set_user_state/facet_supersede + CLI `facets list|pin|forget`
- `core/facets.py`:stability detector 純函數(FacetEvidence/Assessment/
  assess/assess_row/stability_score);決策表 hold/promote/block
- `config.py`:FACET_STABLE_MIN_EVIDENCE=3、FACET_STABLE_MIN_DAYS=3(保守初值)
- `tests/test_facets.py`:26 tests(detector 決策表重放/CRUD 真 DB/UNIQUE active/
  pin 免動+不可 supersede/forget 停用留證據/CLI)
- `tests/test_schema.py`:九表 + profile_facets 欄位

## Verification

- Unit: `python -m pytest tests/test_facets.py tests/test_schema.py -q` → 40 passed
- Regression: `python -m pytest tests/ -q` → **656 passed**(基線 630 + 26)
- Manual QA: 8 表舊庫 → `stm.init` idempotent 升級為 9 表 OK;
  `facets list` 空表印 (empty) 不炸(實跑證據見對話記錄)

## Design deviations

- UNIQUE(facet_class, facet_key, state) → partial unique index on active states
  (兩筆 superseded 同 key 是合法歷史);DESIGN.md 已同步更新並註記原因。
- pin 語義具體化:pin ⇒ provisional 直升 stable + stability=1.0(使用者確認
  即穩定);forget ⇒ 釋放 unique active 槽,同 key 可重新走生命週期。
