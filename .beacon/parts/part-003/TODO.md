# part-003 TODO

Design authority: `.beacon/parts/part-003/DESIGN.md`

## SLICE Map

### part-003-slice-001: transcript 冷儲存 + health 代謝

Status: done (2026-07-13; snapshot: `.beacon/done/part-003/part-003-slice-001-done-current.md`)

Goal: 回水基座(JSONL + .idx 三模式讀取)與健康值代謝(decay/回血/狀態轉換)。

Outcome: events 進 trash 時原文落地冷儲存;decay 批次正確、immune 豁免、trash 到期可撈。

Candidate scope:
- [ ] `core/transcript.py`:append(同步寫 .idx)、read_by_ids/time_window/keyword、按月輪替
- [ ] `core/health.py`:decay(config 參數)、on_hit、alive→trash(含 trashed_at)→撈到期
- [ ] config:HEALTH_DECAY_PER_DAY / TRASH_RETENTION_DAYS / TRANSCRIPT_DIR 生效
- [ ] pytest:roundtrip 三模式、.idx 一致性、decay 數學、immune、boundary(空檔/壞行)

Forbidden scope:
- LLM 呼叫、vault 寫入(slice-002)
- 檢索(slice-003)

Verification target:
- Unit: `python -m pytest tests/test_transcript.py tests/test_health.py -q`
- Regression: `python -m pytest tests/ -q`(93 既有不壞)
- Manual QA: 無

Done gate:
- 三模式讀取 roundtrip;decay/狀態機測試綠;全 pytest 綠

### part-003-slice-002: ltm.py + consolidate 蒸餾管線

Status: done (2026-07-13; snapshot: `.beacon/done/part-003/part-003-slice-002-done-current.md`)

Goal: vault 寫入層 + 夜間蒸餾 job(mock LLM 全管線通)。

Outcome: 塞假 events → `--job consolidate` → vault episodic/ 有筆記(帶 source_ids)
→ events archived;壞決策被欄位級驗證攔截。

Candidate scope:
- [ ] `core/ltm.py`:筆記寫入(frontmatter §5.2、ID 防撞)、INDEX.md registry 維護、讀取解析
- [ ] vault 初始化(INDEX.md + 受控詞彙表 + episodic/ + agent/profile/)
- [ ] `agents/consolidator.md` 契約 + `core/consolidate.py` 全管線
- [ ] 蒸餾決策欄位級驗證(五條)+ 逐組跳過不整批失敗
- [ ] `core/agent.py` 加 `--job consolidate`
- [ ] B7 完全修復:db 參數必填化
- [ ] pytest(mock LLM):管線全路徑 + 驗證攔截 boundary

Forbidden scope:
- 真 LLM 進測試;檢索(slice-003)

Verification target:
- Unit: `python -m pytest tests/test_ltm.py tests/test_consolidate.py -q`
- Regression: 全 pytest 綠
- Manual QA: Obsidian 開 vault 目檢筆記 frontmatter 與 INDEX registry

Done gate:
- mock 全管線綠;驗證攔截測試綠;B7 標 fixed

### part-003-slice-003: vindex + retrieve 四段檢索

Status: done (2026-07-13; snapshot: `.beacon/done/part-003/part-003-slice-003-done-current.md`)

Goal: FTS5 + sqlite-vec 索引與四段級聯檢索(含 rehydrate 回水)。

Outcome: 蒸餾產出的筆記可被四段任一命中;摘要不足時 rehydrate 讀回原文;
index.db 整檔刪除重建等價。

Candidate scope:
- [ ] `core/vindex.py`:FTS5 + vec0 表、rebuild/upsert、search_fts/search_vec
- [ ] `core/retrieve.py`:四段級聯(index-first → FTS5 → vec → rehydrate),統一 hit 格式
- [ ] consolidate 管線尾接 vindex.upsert
- [ ] config:EMBED_MODEL/EMBED_DIM/EMBED_BASE_URL
- [ ] pytest(mock embedding):四段各自命中、級聯 fallback、rebuild 等價、
      命中觸發 health.on_hit(回血閉環)
- [ ] 手動 QA:真 embedding 一次 + 端到端(events→蒸餾→檢索→rehydrate)

Forbidden scope:
- recall 子 agent 問答契約(part-004)

Verification target:
- Unit: `python -m pytest tests/ -q`
- Manual QA: 見 manifest;Phase 3 gate 在此驗收

Done gate:
- Phase 3 gate:低健康 events 蒸餾後出現在 vault 且可檢索;rehydrate 沿 source_ids 讀回原文
