# CURRENT

Status: active
Part: part-007（Personal Model）
Slice: part-007-slice-002 — 證據抽取 + consolidate 整合 + vault 投影

## Context

part-007-slice-000/001 已完成歸檔(`.beacon/done/part-007/`):
- slice-000:profile_facets 第九表 + stm CRUD/CLI + stability detector(656 tests)
- slice-001:profile_facet 提案 + writer 落地 + supersede(672 tests)

## Goal

確定性證據 producer + consolidate 夜間掛鉤(preference 蒸餾 → facet 提案)+
routine 抽取 + vault/agent/profile 投影 + recall 可見。

Design authority: `.beacon/parts/part-007/DESIGN.md`
Slice map: `.beacon/parts/part-007/TODO.md`

## Allowed scope

- [ ] `core/facets.py`：routine 抽取器(schedule/tasks 完成時間 → routine 證據;
      純函數 + 確定性掃描)
- [ ] `core/consolidate.py`：preference 蒸餾組同時產 `profile_facet` 提案
      (evidence_ids = 該組 source_ids;走 writer;LLM 分類欄位級驗證沿用五條)
- [ ] `core/facets.py`：`project_to_vault(db)` 投影 active facets → agent/profile
      筆記(ltm.write_note;confidence 低於閾值不投影;可整批重投影)
- [ ] recall 可見性：投影筆記進 INDEX registry(現有機制自動涵蓋,測試證明)
- [ ] tests：routine 抽取確定性重放、consolidate 掛鉤(LLM mock)、投影 roundtrip
      (facets → 筆記 → 刪筆記 → 重投影一致)、recall 查偏好命中投影筆記
- [ ] Manual QA：真實使用數天後 `facets list` 合理;Obsidian 看 agent/profile

Files-scope: core/facets.py, core/consolidate.py, core/ltm.py,
agents/consolidator.md, tests/test_facets_pipeline.py,
.beacon/parts/part-007/**, .beacon/CURRENT.md

## Forbidden scope

- 自動改行程/待辦(facets 只產知識)
- part-009 建議回饋來源(Advisor 未建;表留欄位不接線)
- per-class 配額調參(初值保守常數即可,真數據再調)

## Verification target

- Unit: `python -m pytest tests/test_facets_pipeline.py -q`
- Regression: `python -m pytest tests/ -q`(基線 672 綠)
- Manual QA: 夜間 job 實跑 + Obsidian 目視投影筆記

## Done gate

抽取/掛鉤/投影/recall 測試綠;DESIGN Verification Targets 五條全數對應;全綠。

## Blocked(不影響本 slice)

- part-006-slice-003 VPS + Tailscale 真機 QA(backlog-008)
- 四批真 QA:LLM key / Discord token / threads session / MCP 本機連線
