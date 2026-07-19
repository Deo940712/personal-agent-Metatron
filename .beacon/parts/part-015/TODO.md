# part-015 TODO

Design authority: `.beacon/parts/part-015/DESIGN.md`

三 slice(三個獨立需求,依序);每個 slice 端到端可用。

## SLICE Map

### part-015-slice-000: INDEX 中文化 + ltm.delete_note 原語

Status: DONE（902 tests green;生產 vault INDEX 已遷移,807 registry 保留）

Goal: 最小、零風險先做——INDEX 說明中文化 + 把 delete 邏輯抽進 ltm(後續 CRUD
的 delete 復用)。

Candidate scope:
- [x] `core/ltm.py`：`_INDEX_TEMPLATE` 標題/說明中文化(tag 不變);既有 vault
      INDEX.md 開頭一次性遷移(保留 Registry 807 行)
- [x] `core/ltm.py`：`delete_note(vault, note_id, idx_db)` 原語——三處刪 + 回
      content_hash(供黑名單);`tools/delete_note.py` 改呼叫它(不重複邏輯)
- [x] tests：INDEX 中文字串斷言、delete_note 三處刪 + 回 hash、既有 delete 工具
      仍過(test_ltm.py +3;全綠 902)

Files-scope: core/ltm.py, tools/delete_note.py, tests/test_ltm.py,
tests/test_retrieve.py, .beacon/parts/part-015/**, .beacon/CURRENT.md

Verification target:
- Unit: `python -m pytest tests/test_ltm.py tests/test_retrieve.py -q`
- Regression: `python -m pytest tests/ -q`(基線 899)
- Manual QA: 生產 INDEX.md 開頭中文;delete_note.py 仍可用

Done gate: INDEX 中文 + delete_note 原語測綠;全綠

### part-015-slice-001: 三層下鑽檢索(主題→筆記→內容)

Status: DONE（907 tests green）

Goal: browse_topic + open_note 能力 + router/快徑接線。逐層點進知識。

Candidate scope:
- [x] `core/tools/memory.py`：`browse_topic(tag, context)`(列該 tag 前 20 篇
      標題+id,走 vindex.notes_by_tag + registry)、`open_note(note_id, context)`
      (讀該篇 frontmatter 摘要 + 內文)
- [x] `core/vindex.py`：`notes_by_tag(idx_db, tag, limit)`(精確 token 比對)
- [x] `core/chat.py`：快徑「看 <tag>」「看筆記 <id>」直達(零 LLM);
      list_knowledge 尾加「輸入『看 <主題>』下鑽」提示
- [~] router intent(選配)：暫不做——快徑已覆蓋明確指令,slice-002 若加自然語
      再評估
- [x] tests：browse_topic 列筆記/未知 tag 空、open_note 讀內容/缺 id、快徑零 LLM
      (test_tools.py +4、test_chat.py +1)

Files-scope: core/tools/memory.py, core/chat.py, tests/test_tools.py,
tests/test_router_wiring.py

Verification target:
- Unit: `python -m pytest tests/test_tools.py tests/test_router_wiring.py -q`
- Regression: 全綠
- Manual QA: Discord「看 claude」→ 列筆記;「看筆記 <id>」→ 內容

Done gate: 三層下鑽測綠;快徑零 LLM;全綠

### part-015-slice-002: 知識庫 CRUD(note_write proposal + writer + router)

Status: planned

Goal: Discord 對話新增/修改/刪除筆記,全走 writer 確認。

Candidate scope:
- [ ] `core/proposals.py`：`note_write` payload 驗證(action/note_id/title/body/
      tags;tags ⊆ 受控詞彙表)
- [ ] `core/writer.py`：`apply_note_write`(create→write_note+vindex;
      edit→update+重 upsert;delete→ltm.delete_note+黑名單);全需確認
- [ ] `core/router.py` + `agents/router.md`：note_create/note_edit/note_delete
      三 intent
- [ ] `core/chat.py`：三 intent 分派 → 組 note_write proposal → stage(預覽+確認)
- [ ] tests：三 action 落地(真 vault)、tags 驗證拒絕、全需確認、delete 黑名單、
      router 三 intent 分類、Discord 端到端(create→查得到)

Files-scope: core/proposals.py, core/writer.py, core/router.py, agents/router.md,
core/chat.py, tests/test_note_write.py, tests/test_router.py

Verification target:
- Unit: `python -m pytest tests/test_note_write.py tests/test_router.py -q`
- Regression: 全綠
- Manual QA: Discord 新增→查→改→刪(黑名單)端到端

Done gate: CRUD 三 action 走 writer 確認測綠;DESIGN targets 全對應;全綠
