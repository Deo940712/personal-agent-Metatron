# part-007 TODO

Design authority: `.beacon/parts/part-007/DESIGN.md`

Open question 定案（slice 設計時）：routine 抽取**掛在 consolidate 夜間 job**（設計
傾向；夜間已在跑、不加新排程面）。stability 公式初值保守，常數集中 config，
真實使用 1-2 月有數據再調（同 backlog-026）。

## SLICE Map

### part-007-slice-000: facets 資料層 + stability detector

Status: done (2026-07-19; snapshot: `.beacon/done/part-007/part-007-slice-000-done-current.md`)
656 tests 綠(基線 630 + 26);idempotent 升級 QA 通過。
Design deviation:UNIQUE 三欄 → partial unique active index(DESIGN 已同步)。

Goal: DB1 第九表 `profile_facets` + stm CRUD/CLI + stability detector 純函數。
證據累積 → provisional → stable 的升級判定完全可重放測試；pin/forget 使用者
硬覆蓋在資料層生效。

Outcome: `python -m core.stm facets list/pin/forget` 可用；detector 純函數對
mock 證據流給出確定性升級決策；一次證據永不直接 stable。

Candidate scope:
- [x] `core/stm.py`：`profile_facets` DDL（partial unique active，DESIGN 已修正）+ CRUD
      （facet_get/facet_get_active/facet_list/facet_insert/facet_touch_evidence/
      facet_promote/facet_set_user_state/facet_supersede）+ CLI `facets list|pin|forget`
- [x] `core/facets.py`：stability detector 純函數
      （`assess(FacetEvidence) -> Assessment`；常數 FACET_STABLE_MIN_EVIDENCE=3 /
      FACET_STABLE_MIN_DAYS=3 進 config，初值保守）
- [x] pin ⇒ 評分無效化；forgotten ⇒ 阻止升級（detector + CRUD 雙層擋）
- [x] tests：detector 純函數重放（單證據不 stable / N 證據跨 M 天升級 /
      pinned 免動 / forgotten 不升級）+ stm CRUD 真 DB 測試 + UNIQUE active 約束
      （26 tests）

Files-scope: core/stm.py, core/facets.py, config.py, tests/test_facets.py,
tests/test_schema.py, .beacon/parts/part-007/**, .beacon/CURRENT.md

Forbidden scope:
- writer proposal type / supersede 執行（slice-001）
- consolidate 整合、vault 投影、recall（slice-002）
- LLM 呼叫（本 slice 全確定性）
- 修改既有八表 schema

Verification target:
- Unit: `python -m pytest tests/test_facets.py tests/test_schema.py -q`
- Regression: `python -m pytest tests/ -q`
- Manual QA: `python -m core.stm init`（idempotent）→ `facets list` 空表不炸

Done gate:
- detector 決策表全測綠；pin/forget 資料層生效；`init` 對舊庫 idempotent 升級；全綠

### part-007-slice-001: profile_facet 提案 + writer 落地 + supersede

Status: done (2026-07-19; snapshot: `.beacon/done/part-007/part-007-slice-001-done-current.md`)
672 tests 綠(基線 656 + 16);manual QA(手組 proposal → 落地/偽證據拒絕)通過。

Goal: `profile_facet` proposal type + writer 驗證落地路徑 + 矛盾 supersede 執行。

Outcome: facet 建立/升級/supersede 全走 writer 欄位級驗證；偽造 evidence_ids、
覆蓋 pinned/forgotten 一律拒絕並記 events；supersede 舊 facet 留 superseded_by 不刪。

Candidate scope:
- [x] `core/proposals.py`：`profile_facet` payload schema
      （action: create|reinforce|supersede；class/key/value/evidence_ids）
- [x] `core/writer.py`：`apply` dispatch 支援 profile_facet；驗證：facet_class 合法、
      evidence_ids 存在於 transcript、不覆蓋 pinned/forgotten、supersede 目標真實
      且未被取代（同 part-004.5 Mneme 規則）
- [x] supersede 執行：新 facet active、舊 facet state='superseded' + superseded_by
      （mark → insert → link 三步，釋放 unique active 槽）
- [x] tests：合法三 action 落地、五類拒絕路徑（偽 evidence / pinned / forgotten /
      不存在 supersede 目標 / 已被取代目標）、events 記錄 proposal_rejected（16 tests）

Files-scope: core/proposals.py, core/writer.py, core/stm.py, tests/test_facets_writer.py

Forbidden scope:
- LLM、consolidate、vault 投影（slice-002）
- 繞過 writer 的任何 facet 寫入捷徑

Verification target:
- Unit: `python -m pytest tests/test_facets_writer.py -q`
- Regression: `python -m pytest tests/ -q`
- Manual QA: 手組 proposal dict 走 writer.apply → facets list 看結果

Done gate:
- 三 action + 五拒絕路徑測試綠；writer 仍是唯一寫入邊界；全綠

### part-007-slice-002: 證據抽取 + consolidate 整合 + vault 投影

Status: planned

Goal: 確定性證據 producer + consolidate 夜間掛鉤（preference 蒸餾 → facet 提案）+
routine 抽取 + vault/agent/profile 投影 + recall 可見。

Outcome: 夜間 job 跑完，重複出現的偏好升級成 facet；active facets 投影成
vault/agent/profile 筆記（source: agent_knowledge + source_ids）；recall 問
「我的偏好」查得到；投影是衍生物可重建。

Candidate scope:
- [ ] `core/facets.py`：routine 抽取器（schedule/tasks 完成時間 → routine 證據；
      純函數 + 確定性掃描）
- [ ] `core/consolidate.py`：preference 蒸餾組同時產 `profile_facet` 提案
      （evidence_ids = 該組 source_ids；走 writer；LLM 分類欄位級驗證沿用五條）
- [ ] `core/facets.py`：`project_to_vault(db)` 投影 active facets → agent/profile
      筆記（ltm.write_note；confidence 低於閾值不投影；可整批重投影）
- [ ] recall 可見性：投影筆記進 INDEX registry（現有機制自動涵蓋，測試證明）
- [ ] tests：routine 抽取確定性重放、consolidate 掛鉤（LLM mock）、投影 roundtrip
      （facets → 筆記 → 刪筆記 → 重投影一致）、recall 查偏好命中投影筆記
- [ ] Manual QA：真實使用數天後 `facets list` 合理；Obsidian 看 agent/profile

Files-scope: core/facets.py, core/consolidate.py, core/ltm.py, agents/consolidator.md,
tests/test_facets_pipeline.py

Forbidden scope:
- 自動改行程/待辦（facets 只產知識）
- part-009 建議回饋來源（Advisor 未建；表留欄位不接線）
- per-class 配額調參（初值保守常數即可，真數據再調）

Verification target:
- Unit: `python -m pytest tests/test_facets_pipeline.py -q`
- Regression: `python -m pytest tests/ -q`
- Manual QA: 夜間 job 實跑 + Obsidian 目視投影筆記

Done gate:
- 抽取/掛鉤/投影/recall 測試綠；DESIGN Verification Targets 五條全數對應；全綠
