# part-005 TODO

Design authority: `.beacon/parts/part-005/DESIGN.md`

## SLICE Map

### part-005-slice-001: octools + scanners(三源唯讀掃描)

Status: done (2026-07-13)

Goal: 三個確定性掃描器,全唯讀、全容錯。

Outcome: 對本專案跑三掃描器,回傳真實的 git/beacon/opencode 資料;壞輸入不 crash。

Candidate scope:
- [ ] `core/octools.py`:recent_sessions(mode=ro、毫秒轉秒、directory 正規化)、
      session_todos(完成率)、schema 容錯
- [ ] `core/scanners.py`:git_scan(subprocess 容錯、無 upstream 容忍)、
      beacon_scan(CURRENT 兩形態 parser、缺 .beacon → None)
- [ ] pytest:tmp git repo 實測、假 opencode.db(同 schema)、假 CURRENT.md、
      boundary(非 git 目錄/壞 db/空表)

Files-scope: core/octools.py, core/scanners.py, tests/test_scanners.py

Forbidden scope:
- LLM / track 管線(slice-002);MCP(part-006)

Verification target:
- Unit: `python -m pytest tests/test_scanners.py -q`
- Regression: `python -m pytest tests/ -q`(280 不壞)

Done gate:
- 三掃描器容錯測試綠;對本專案實跑回真資料

### part-005-slice-002: track 管線 + coding_tracker 契約

Status: planned

Goal: 三源 → LLM 綜合 → project_update 提案 → writer 落地。Phase 5 gate。

Outcome: `--job track` 自動更新 projects 表;LLM 幻覺專案被拒。

Candidate scope:
- [ ] `agents/coding_tracker.md`:契約(beacon 最高權威、輔證規則)+ few-shot
- [ ] `core/track.py`:管線(批次 ≤10、部分失敗容忍)
- [ ] `core/proposals.py` + `core/writer.py`:project_update 驗證 + 落地
      (免確認,理由見 DESIGN)
- [ ] `core/agent.py`:--job track
- [ ] pytest(mock LLM):全管線、幻覺專案名、部分掃描失敗、writer 驗證 boundary
- [ ] 手動 QA:本專案真三源 + mock LLM → projects 表更新

Files-scope: agents/coding_tracker.md, core/track.py, core/proposals.py, core/writer.py, core/agent.py, tests/test_track.py

Forbidden scope:
- MCP 工具暴露(part-006)

Verification target:
- Unit: `python -m pytest tests/test_track.py -q`
- Regression: 全綠
- Manual QA: 本專案端到端

Done gate:
- Phase 5 gate:coding_tracker 三源掃描自動更新 projects 表
