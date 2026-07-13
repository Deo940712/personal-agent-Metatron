# part-004.5 TODO

Design authority: `.beacon/parts/part-004.5/DESIGN.md`

## SLICE Map

### part-004.5-slice-001: 主題連續性蒸餾(Membox)

Status: done (2026-07-13)

Goal: 蒸餾契約加 topic 欄位;consolidate 收尾自動連結近 30 天同主題筆記。

Outcome: 兩天各蒸餾出同主題筆記 → 自動產生雙向 related 連結。

Candidate scope:
- [ ] `agents/consolidator.md`:輸出 schema 加 `topic`(必填,<=30字)+ few-shot
- [ ] `core/consolidate.py`:`_validate_group` 第六條(topic);寫筆記後掃近 30
      天同 topic episodic 筆記,雙向補 related
- [ ] pytest:topic 驗證 boundary;連結產生;無同主題時不連結;30 天窗口邊界

Files-scope: agents/consolidator.md, core/consolidate.py, tests/test_consolidate.py

Forbidden scope:
- supersede(slice-002);RRF(slice-003)

Verification target:
- Unit: `python -m pytest tests/test_consolidate.py -q`
- Regression: `python -m pytest tests/ -q`(254 不壞)

Done gate:
- topic 驗證與連結產生測試綠

### part-004.5-slice-002: 矛盾偵測 + supersede 執行(Mneme)

Status: done (2026-07-13)

Goal: preference 蒸餾前注入既有 profile;LLM 可輸出 supersedes;落地補
superseded_by;recall 契約查詢邏輯。

Outcome: 蒸餾出「偏好改變」的新事實 → 舊 profile 筆記被標記 superseded_by,
不刪;recall 讀到會提醒有更新版。

Candidate scope:
- [ ] `agents/consolidator.md`:preference 蒸餾輸入注入既有 profile INDEX;
      輸出可選 `supersedes` 欄位 + few-shot(矛盾情境)
- [ ] `core/consolidate.py`:supersedes 驗證(存在性+非已 superseded)
- [ ] `core/ltm.py` 或 `writer.py`:`mark_superseded(vault, old_id, new_id)`
- [ ] `agents/recall.md`:落地「查 superseded_by,優先引用新版,矛盾並列」規則
- [ ] `core/recall.py`:read_note 工具結果附帶 superseded_by 提示(若有)
- [ ] pytest:supersede 落地、驗證攔截(指不存在/已被 superseded 的 id)、
      recall 讀到 superseded_by 的行為

Files-scope: agents/consolidator.md, agents/recall.md, core/consolidate.py, core/ltm.py, core/writer.py, core/recall.py, tests/test_consolidate.py, tests/test_recall.py

Forbidden scope:
- RRF(slice-003)

Verification target:
- Unit: `python -m pytest tests/test_consolidate.py tests/test_recall.py -q`
- Regression: 全綠

Done gate:
- supersede 落地+驗證+recall 查詢測試綠

### part-004.5-slice-003: RRF 跨段融合檢索(Cognis)

Status: planned

Goal: retrieve.search 從「前段命中即返回」改三段候選 RRF 融合;強命中仍短路。

Outcome: 給定固定排名輸入,RRF 融合分數與排序符合公式;強 index 命中零向量呼叫。

Candidate scope:
- [ ] `core/retrieve.py`:`_rrf_fuse`(純函數)+ `strong_index_hit` 判斷 +
      search() 改寫(候選池放大 limit*2)
- [ ] pytest:RRF 公式正確性(手算固定案例)、強命中短路(mock embed_fn 斷言
      未被呼叫)、全 miss、回血閉環對融合結果生效
- [ ] 全 254+ 既有測試(尤其 test_retrieve.py)迴歸確認介面相容

Files-scope: core/retrieve.py, tests/test_retrieve.py

Forbidden scope:
- cross-encoder rerank(backlog-025,不在本 part)

Verification target:
- Unit: `python -m pytest tests/test_retrieve.py -q`
- Regression: `python -m pytest tests/ -q`(全綠)

Done gate:
- Phase 4.5 gate:主題 trace 連結生效;supersede 落地(舊筆記標記);
  RRF 融合排序正確且強命中短路
