# part-007-slice-002 — 證據抽取 + consolidate 整合 + vault 投影(done 2026-07-19)

Snapshot of CURRENT at completion.

## Goal(達成)

確定性證據 producer + consolidate 夜間掛鉤 + routine 抽取 +
vault/agent/profile 投影 + recall 可見。整條 Personal Model 鏈路打通。

## Delivered

- `core/facets.py`:
  - `extract_routine`:確定性 routine 抽取器(schedule/tasks 完成時間 → 五時段桶
    → 主時段 facet;純函數,證據不足回 None,不猜不推斷)
  - `project_to_vault`:active facets → `agent/profile/` 可讀筆記
    (source: agent_knowledge + source_ids;低 confidence 過濾;值變更重投影
    自動 supersede 舊筆記;facets 是真相、投影可重建)
- `core/consolidate.py`:preference 組帶 `facet_key` → `_emit_facet` 產
  profile_facet 提案走 writer(create/reinforce 確定性映射;evidence=source_ids
  過 transcript 驗證);夜間 job 尾端自動 project_to_vault;transcript_dir 全程串接
- `core/writer.py`:apply/apply_validated 加 transcript_dir 參數(facet evidence 驗證)
- `agents/consolidator.md`:契約加選填 facet_key/facet_class(穩定偏好才給)
- `tests/test_facets_pipeline.py`:16 tests(routine 抽取重放/桶邊界/consolidate 掛鉤
  向後相容/facet create+reinforce/偽證據拒絕不炸/投影 roundtrip/低信心跳過/
  重投影 supersede/registry 可見/job 尾端投影)

## Verification

- Unit: `python -m pytest tests/test_facets_pipeline.py -q` → 16 passed
- Regression: `python -m pytest tests/ -q` → **688 passed**(基線 672 + 16)
- Manual QA(端到端實跑,證據見對話記錄):偏好事件 → 夜間 job →
  reply_lang facet 建立(provisional)→ 投影成 agent/profile 筆記
  (source: agent_knowledge + source_ids:[evt:1])→ `facets list` 顯示。
  job stats: facets_projected=1。

## DESIGN Verification Targets 對照

- [x] 單次證據不建 stable facet;N 次同證據 → provisional → stable(slice-000 detector)
- [x] pin 後評分不再改動;forget 後不再升級/載入,證據列仍在(slice-000/001)
- [x] 矛盾新值 → supersede 舊 facet(舊留 superseded_by,不刪)(slice-001)
- [x] active facets 投影成 vault 筆記且 recall 查得到(本 slice)
- [x] writer 攔截:偽造 evidence_ids / 覆蓋 pinned → 拒絕(slice-001)

## Notes

- routine 抽取器為純函數 + 確定性掃描;實際接線到 schedule/tasks 完成事件的
  producer 留待真實使用觀察(抽取器本身已可測、可用)。DESIGN Open Question
  「routine 掛 consolidate vs 獨立 job」定案:抽取器獨立純函數,投影掛 consolidate。
- 投影重複時舊筆記走 supersede(不刪);registry 行會累積,由 librarian
  (backlog-017)未來清理——個人量級可接受。
