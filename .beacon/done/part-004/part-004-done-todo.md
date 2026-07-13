# part-004 TODO

Design authority: `.beacon/parts/part-004/DESIGN.md`

## SLICE Map

### part-004-slice-001: threads-sync 接入 + skills/runner

Status: done (2026-07-13; 真同步 QA blocked — Playwright session 在原機器)

Goal: threads-sync vendored clone 進 skills/ + 執行器(cursors/agent_runs 整合)。

Outcome: `python -m skills.runner threads_sync` 可跑(真 session 缺 → 優雅回報
login_expired);DB1 有執行記錄。

Candidate scope:
- [ ] `skills/threads_sync/`:clone Deo940712/threads-sync,pin commit,VAULT_PATH 覆蓋探勘+接線
- [ ] `skills/runner.py`:執行 1-5 步驟、exit code 捕捉、cursors + agent_runs 寫入
- [ ] pytest:mock skill CLI → runner 整合點(成功/失敗/login_expired 三路徑)

Files-scope: skills/**, tests/test_runner.py

Forbidden scope:
- 改 threads-sync 內部邏輯(黑箱;最多 config 覆蓋一行)
- curator / recall(後續 slices)

Verification target:
- Unit: `python -m pytest tests/test_runner.py -q`
- Regression: 全綠(210+)
- Manual QA: 真 threads-sync 跑通 — blocked(Playwright session 在原機器)

Done gate:
- runner 三路徑測試綠;真同步 blocked 誠實記錄

### part-004-slice-002: curator(前處理 + LLM 契約 + 管線)

Status: planned

Goal: inbox 筆記 → 評分/分類/去重 → 正式入庫(writer + registry + vindex)。

Outcome: 手工假貼文丟 inbox → curator 批次 → 高分入 registry 可檢索、低分標 low-score。

Candidate scope:
- [ ] `core/curator_pre.py`:inbox 掃描、content_hash、跨源去重、§5.2 欄位補齊
- [ ] `agents/curator.md`:評分+分類契約(閾值 4.0、配額、evidence 規則)
- [ ] `core/curate.py`:pre → LLM 批次(≤10 篇)→ 驗證 → 落地 → 統計
- [ ] writer:classify_note 落地(frontmatter 更新 + manual_tags 守衛 + registry + vindex)
- [ ] INDEX 詞彙表擴充(14 類 + low-score)——列出讓使用者確認
- [ ] `core/agent.py` 加 `--job curate`
- [ ] pytest(mock LLM):閘門/配額/去重/manual_tags/驗證攔截 + boundary

Files-scope: core/curator_pre.py, core/curate.py, core/writer.py, agents/curator.md, core/agent.py, tests/test_curate.py

Forbidden scope:
- FIRE 拆卡完整版(backlog-019,先 summary+tags 起步)
- recall(slice-003)

Verification target:
- Unit: `python -m pytest tests/test_curate.py -q`
- Regression: 全綠
- Manual QA: 假貼文 3 篇(高/低分/重複)端到端目檢

Done gate:
- 評分閘門+配額+去重測試綠;假資料端到端通

### part-004-slice-003: recall 子 agent(問答 + 引用)

Status: planned

Goal: 代理型 recall:唯讀工具迴圈 → 帶引用回答。

Outcome: `python -m core.agent "recall 我存過哪些 RAG 貼文"` 給出引用 note_id/url 的答案。

Candidate scope:
- [ ] `agents/recall.md`:代理型契約(工具白名單、引用硬規則、找不到誠實說)
- [ ] `core/recall.py`:工具迴圈(上限 6 步)、引用格式化、命中回血接線
- [ ] chat.py 路由:本機 CLI 的 recall 前綴(Discord 仍拒絕——內容分級不變)
- [ ] pytest(mock):引用存在、無來源不斷言、步數上限、回血
- [ ] Phase 4 gate 端到端(mock):貼文 → curator → recall → 引用正確

Files-scope: agents/recall.md, core/recall.py, core/chat.py, core/agent.py, tests/test_recall.py

Forbidden scope:
- supersede 執行(part-004.5;契約先寫「查 superseded_by 欄位」)

Verification target:
- Unit: `python -m pytest tests/ -q`
- Manual QA: 真 LLM recall 一問 — 與其他真 QA 同批(blocked 等 key)

Done gate:
- Phase 4 gate(mock 版):threads-sync 假輸出 → curator 入庫 → recall 帶引用答對
