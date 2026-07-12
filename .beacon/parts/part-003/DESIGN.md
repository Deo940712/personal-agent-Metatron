# part-003 DESIGN

## Goal

記憶系統核心:冷儲存 transcript(回水基座)→ 夜間 consolidation(健康值代謝 +
LLM 蒸餾 + 欄位級驗證)→ DB2 vault 寫入(episodic/ + agent/profile/)→
檢索(index-first → FTS5 → 向量 → rehydrate 四段)。
完成後:低健康 events 蒸餾成 vault 筆記且可檢索;摘要不夠精確時能沿
source_ids 讀回原文。

## Non-goals

- curator / librarian / recall 子 agent 的完整版(recall 檢索函式在本 part,
  但問答式 recall agent 契約在 part-004 有貼文資料後)
- sync skills(part-004);Discord(part-002.5)
- golden queries 回歸測試基建(backlog-007,隨貼文入庫後才有真實查詢可測)

## Assumptions

- 向量索引 = sqlite-vec v0.1.9(backlog-001 已定案,本機實測 KNN OK)
- FTS5 可用(本機實測 OK)——插在 index-first 與向量之間,零 embedding 成本
- embedding 走同一 OpenAI 相容端點 `/v1/embeddings`(text-embedding-3-small,
  dim 1536;換 Ollama 時模型名/維度隨 config)
- vault 尚無貼文(threads-sync 遷入在 part-004)——本 part 的 vault 寫入者只有
  consolidation;INDEX.md 由本 part 初始化
- 健康值參數初值(可調,存 config):日衰減 0.05、命中回血至 1.0、
  trash 保留 14 天、免疫類別不衰減

## Design Options

1. 蒸餾單位:逐條 events → 逐筆筆記 —— 碎片化,token 貴
2. **(選定)按天/主題批次蒸餾** —— trash 到期的 events 按日分組,每組一篇
   episodic 筆記;偏好類事實(LLM 標記 kind=preference)另抽進 agent/profile/
3. 向量化對象:全文 vs 摘要 —— **(選定)筆記的 title+summary+tags**(短、穩定,
   全文靠 FTS5/rehydrate 補)

## 探針實證(2026-07-13;設計修正依據)

實跑驗證了 9 個技術假設,4 個需要設計修正:

| # | 發現 | 設計修正 |
|---|---|---|
| P1 | sqlite-vec **每條連線都要 load extension**(未 load → no such module) | vindex.py 自帶 connect helper,不共用 stm.connect |
| P2 | vec0 **不支援 INSERT OR REPLACE**(UNIQUE constraint failed) | upsert = DELETE + INSERT |
| P3 | vec0 rowid **只接受 INT**,note_id 是字串 | index.db 加 mapping 表 `note_map(rowid INTEGER PK, note_id TEXT UNIQUE)` |
| P4 | **FTS5 中文**:unicode61 完全不命中;trigram 3 字以上才命中(2 字查詢 miss),但 trigram 表 LIKE 可用;英文在 trigram 下正常 | FTS5 用 `tokenize='trigram'`;查詢策略:**≥3 字用 MATCH,<3 字降級 LIKE**(封裝在 search_fts 內) |
| P5 | binary blob(struct.pack float32)roundtrip OK | embedding 存二進位,不存 JSON 字串 |
| P6 | .idx 與 JSONL 中斷不一致風險 | 加 `rebuild_idx()`:.idx 可從 JSONL 全量重掃(衍生物哲學) |
| P7 | decay 0.05/day → 20 天歸零 + trash 14 天 = 事件 34 天生命週期 | 參數合理,維持 |
| P8 | transcript keyword 全掃 10k 行 = 17ms | 月檔全掃可行,不需索引 |
| P9 | epoch → 月檔名 OK | 維持 |

## Chosen Design

### 模組

| 檔案 | 職責 |
|---|---|
| `core/transcript.py` | 冷儲存(§5.3):append(JSONL + .idx 同步寫)、read(entry_id / time_window / keyword 三模式)、按月輪替、`rebuild_idx()`(.idx 從 JSONL 重掃——中斷自癒)。**events 原文在進 trash 時即落地**(不等蒸餾——回水指標從 trash 起就有效) |
| `core/health.py` | 代謝(§4.1):decay(全表批次,immune 跳過)、on_hit(回血 + last_accessed_at)、state 轉換(alive→trash→archived,含 trashed_at) |
| `core/ltm.py` | DB2 存取層:vault 筆記寫入(frontmatter 組裝 §5.2、穩定 ID YYYYMMDD-slug 防撞)、INDEX.md registry 維護(append 一行描述)、讀取/解析 frontmatter |
| `core/vindex.py` | 檢索索引:FTS5 表(`tokenize='trigram'`,中文 ≥3 字 MATCH / <3 字 LIKE 降級)+ vec0 表 + `note_map`(TEXT note_id ↔ INT rowid);自帶 connect(每連線 load sqlite-vec);upsert = DELETE+INSERT;embedding 存 binary blob;rebuild 全量重建。獨立檔 index.db |
| `core/consolidate.py` | 夜間 job(§6.3):decay → trash 轉換 → 撈 trash 到期 → transcript 落地 → LLM 蒸餾(批次)→ **欄位級驗證每個決策** → ltm 寫筆記(帶 source_ids)→ events 標 archived → vindex.upsert → agent_runs 統計 |
| `core/retrieve.py` | 四段檢索(§6.4 擴充):① index-first(INDEX registry 一行描述比對)② FTS5 ③ 向量 KNN ④ rehydrate(沿 source_ids 讀 transcript)。回傳統一 hit 格式(id, path, score, stage) |
| `agents/consolidator.md` | 蒸餾 LLM 契約:輸入 events 批次 → 輸出每組 {summary, tags, kind: episodic\|preference, confidence};few-shot |

### 蒸餾決策的欄位級驗證(記憶可靠性 §8 的落實)

LLM 回傳每組決策必過(不合格跳過該組、記 events、繼續下一組——不整批失敗):

1. `kind` ∈ {episodic, preference};2. `tags` ⊆ 受控詞彙表(INDEX.md;初始詞彙表
   由本 part 定義);3. `source_event_ids` ⊆ 本批次實際 id(LLM 不得虛構);
4. `confidence` ∈ [0,1],低於 0.6 → 跳過(保守);5. summary 非空且 ≤500 字。

### vault 初始化(本 part 一併交付)

```
vault/
├── INDEX.md          # 操作規則 + 受控 tag 詞彙表(初始:inbox, ai-agent, coding,
│                     #   schedule, preference, ops, daily-log)+ registry
├── episodic/         # 蒸餾產出
└── agent/profile/    # 偏好類事實
```

### config 新增

`EMBED_MODEL`(text-embedding-3-small)、`EMBED_DIM`(1536)、
`HEALTH_DECAY_PER_DAY`(0.05)、`TRASH_RETENTION_DAYS`(14)、
`DISTILL_MIN_CONFIDENCE`(0.6)。

### B7 完全修復(移交事項)

本 part 觸碰所有 DB 呼叫鏈:core 內部函式 db 參數改必填(僅 CLI 入口容許 None
→ config 解析),KNOWN_ISSUES B7 從 partial → fixed。

## Verification Targets

- transcript:append→read 三模式 roundtrip;.idx 與 JSONL 一致;月輪替
- health:decay 數學、immune 跳過、命中回血、狀態轉換含 trashed_at
- consolidate(mock LLM):全管線——events 進 trash → 落地冷儲存 → 蒸餾 →
  驗證攔截(壞 kind/虛構 source_ids/低 confidence)→ vault 有筆記 → events archived
- retrieve:四段各自可命中 + 級聯(前段 miss 落到後段);rehydrate 讀回原文
- vindex:rebuild 後 FTS/vec 查詢一致;整檔刪除重建等價
- 手動 QA:塞假 events → 跑 consolidate → Obsidian 開 vault 看筆記 → 檢索命中 →
  rehydrate 對照原文

## Unit Test Strategy

pytest;LLM/embedding 全 mock(embedding mock 回固定向量);sqlite-vec 真載入
(本機已驗)。每個 validator 配 boundary 測試(KNOWN_ISSUES 教訓)。

## Manual QA Strategy

真 embedding 端點一次(與真 LLM QA 同時,需 API key);Obsidian 開 vault 目檢
frontmatter 與 INDEX。

## Risks

- sqlite-vec 在 VPS(Linux)的 wheel 相容性——遷移時重驗(backlog-008 checklist)
- 蒸餾批次過大爆 context——按天分組 + 每組上限 50 events,超過再切
- embedding 端點與 LLM 端點可能不同家(Ollama embedding + OpenRouter LLM)——
  config 允許 EMBED_BASE_URL 獨立設定(未設 = 同 LLM_BASE_URL)

## Open Questions

(無——向量索引已定案;健康值參數為 config 可調初值,不需預先精確)
