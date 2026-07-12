# 記憶系統技術文件(part-003)

> 語言:繁體中文|English: [MEMORY-en.md](MEMORY-en.md)
> 設計權威:[ARCHITECTURE.md](../ARCHITECTURE.md) §4/§5/§6;本文件是實作層技術規格,
> 含探針實證的平台行為(2026-07-13,Windows / Python 3.12 / SQLite 3.45 / sqlite-vec 0.1.9)。

## 1. 系統總覽

```
events (DB1)                     vault (DB2)                index.db (衍生物)
alive ──decay──> trash ──14天──> 蒸餾 ──> episodic/*.md ──> FTS5 + vec0
  │                │                        │ source_ids
  │                └─原文落地─> transcript/ <┘ (rehydrate 回水)
  └─檢索命中─> 回血(on_hit)
```

四個儲存角色(§2):DB1 = System of Record;vault = 人類知識介面;
transcript = 原始記錄(永不刪);index.db = 可整檔刪除重建的衍生物。

## 2. 冷儲存 transcript(`core/transcript.py`)

### 2.1 檔案格式

```
data/transcript/
├── 2026-07.jsonl        # 按月輪替(檔名 = fromtimestamp(ts) 的 %Y-%m)
└── 2026-07.jsonl.idx    # 索引:entry_id<TAB>byte_offset<TAB>length
```

JSONL 每行(§5.3):

```jsonc
{"entry_id": "evt:123", "ts": 1752300000, "kind": "event_raw", "payload": {...}}
// entry_id 命名空間:evt:<events.id> | raw:<pipeline>:<post_id>
// kind: event_raw | sync_raw | llm_io
```

### 2.2 API

| 函式 | 行為 |
|---|---|
| `append(db_dir, entry_id, kind, payload, ts)` | 寫 JSONL 一行 + 同步寫 .idx 一行;回傳 entry_id |
| `read_by_ids(db_dir, entry_ids)` | 經 .idx O(1) seek;缺 id 回報不拋錯 |
| `read_by_time(db_dir, start_ts, end_ts)` | 跨月檔線性掃(月檔內 ts 有序) |
| `read_by_keyword(db_dir, keyword, limit)` | 全檔線性掃(實測 10k 行 17ms,個人量級足夠) |
| `rebuild_idx(db_dir, month)` | .idx 從 JSONL 全量重掃(中斷自癒;.idx 是衍生物) |

### 2.3 不變量

1. **append-only**:任何函式都不得改寫既有行;無 delete API
2. .idx 壞掉/落後 → `rebuild_idx` 重建,JSONL 是唯一真相
3. 寫入順序:先 JSONL flush,再 .idx——中斷最壞情況 = .idx 少行(可重建),
   絕不出現 .idx 指向不存在的資料

## 3. 健康值代謝(`core/health.py`)

### 3.1 參數(config.py,可調)

| 常數 | 初值 | 意義 |
|---|---|---|
| `HEALTH_DECAY_PER_DAY` | 0.05 | 線性日衰減(1.0 → 0 需 20 天) |
| `TRASH_RETENTION_DAYS` | 14 | trash 保留期(期內被引用可復活) |

事件生命週期:寫入(health=1.0)→ 無人問津 20 天 → trash → 14 天 → 蒸餾封存。
合計約 34 天(探針 P7 實證)。

### 3.2 API 與狀態機

| 函式 | 行為 |
|---|---|
| `decay(db, now_ts)` | 全表批次:`health -= 天數×衰減率`(自 last_accessed_at 或 created_at 起算);`immune=1` 跳過 |
| `to_trash(db, now_ts)` | `alive ∧ health≤0 ∧ immune=0` → `state='trash', trashed_at=now`;**同時把原文 append 進 transcript**(回水指標從此有效) |
| `on_hit(db, event_ids, now_ts)` | 檢索命中:health=1.0、last_accessed_at=now;trash 內命中 → 復活回 alive |
| `due_for_distill(db, now_ts)` | 撈 `trash ∧ trashed_at ≤ now - 保留期` |
| `mark_archived(db, event_ids)` | 蒸餾完成後標 archived(不再進任何主動載入) |

狀態機(§4.1):`alive ⇄ trash → archived`;免疫類別(行程/身分/偏好/手動標記)
永不衰減;archived = 遺忘 = 不主動載入 ≠ 刪除(原文永在 transcript)。

## 4. 檢索索引(`core/vindex.py`)

### 4.1 平台行為(探針實證,勿憑直覺改)

| 實證 | 後果 |
|---|---|
| sqlite-vec **每條連線都要 `enable_load_extension` + load**(P1) | vindex 自帶 `_connect()`,不共用 `stm.connect` |
| vec0 **不支援 INSERT OR REPLACE**(P2:UNIQUE constraint failed) | upsert = `DELETE WHERE rowid` + `INSERT` |
| vec0 rowid **只接受 INTEGER**(P3),note_id 是字串 `YYYYMMDD-slug` | 需 `note_map` 對映表 |
| FTS5 **unicode61 對中文完全不命中**;trigram 需 **≥3 字**;trigram 表 **LIKE 可用**;英文正常(P4) | tokenizer 用 trigram;查詢 <3 字降級 LIKE |
| embedding **binary blob(float32 LE)roundtrip OK**(P5) | 存 `struct.pack(f"{dim}f", *vec)`,不存 JSON 字串 |

### 4.2 schema(index.db,獨立檔)

```sql
CREATE TABLE note_map (               -- TEXT note_id ↔ INT rowid(vec0 需求)
  rowid    INTEGER PRIMARY KEY AUTOINCREMENT,
  note_id  TEXT NOT NULL UNIQUE
);
CREATE VIRTUAL TABLE notes_fts USING fts5(
  note_id, title, summary, tags, tokenize='trigram'
);
CREATE VIRTUAL TABLE notes_vec USING vec0(
  embedding float[1536]               -- dim = config.EMBED_DIM
);
CREATE TABLE meta (                   -- 換 embedding 模型 = 全量重建的依據
  key TEXT PRIMARY KEY, value TEXT    -- embed_model / embed_dim / built_at
);
```

### 4.3 API

| 函式 | 行為 |
|---|---|
| `upsert(idx_db, note_id, title, summary, tags, vector?)` | note_map 取/建 rowid → FTS5 與 vec0 各 DELETE+INSERT;vector=None 只更新 FTS |
| `search_fts(idx_db, query, limit)` | ≥3 字(或含英文詞)→ MATCH;<3 字 → LIKE 降級。回 `[(note_id, score)]` |
| `search_vec(idx_db, vector, k)` | KNN;回 `[(note_id, distance)]` |
| `rebuild(idx_db, vault_path, embed_fn)` | 整檔重建:掃 vault frontmatter → 全量重灌(換模型/壞檔時用) |

不變量:index.db 不存唯一資料;`meta.embed_model` 變 → 必須 rebuild;
向量化對象 = title+summary+tags(全文靠 FTS/rehydrate)。

## 5. 蒸餾管線(`core/consolidate.py`)

### 5.1 流程(§6.3)

```
decay → to_trash(原文落地) → due_for_distill → 按天分組(每組≤50)
  → LLM 蒸餾(consolidator 契約) → 欄位級驗證(五條) → ltm 寫筆記(帶 source_ids)
  → mark_archived → vindex.upsert → agent_runs 統計
```

### 5.2 欄位級驗證(五條;逐組跳過,不整批失敗)

1. `kind` ∈ {episodic, preference}
2. `tags` ⊆ INDEX.md 受控詞彙表
3. `source_event_ids` ⊆ 本批次實際 id(**LLM 不得虛構來源**)
4. `confidence` ≥ 0.6(低於即跳過,保守)
5. `summary` 非空且 ≤500 字

不合格 → 該組跳過 + events 記 `proposal_rejected` + 繼續下一組。
該批 events 維持 trash(下輪重試),**永不因蒸餾失敗而丟失**。

### 5.3 產出

- `kind=episodic` → `vault/episodic/YYYYMMDD-<slug>.md`(frontmatter §5.2:
  source=consolidation、period、source_ids、distilled_at、model、tags)
- `kind=preference` → `vault/agent/profile/`(免疫衰減;source_ids 溯源)

## 6. 四段級聯檢索(`core/retrieve.py`)

```
① index-first   INDEX.md registry 一行描述比對     零成本,可解釋
② FTS5          trigram 全文(中文≥3字/LIKE降級)   零 embedding 成本
③ 向量 KNN      sqlite-vec(語意「換句話說」)       一次 embed 呼叫
④ rehydrate     沿 source_ids 讀 transcript 原文    需要確切數字/名字時
```

統一回傳:`[{note_id, path, score, stage}]`。
**命中閉環**:任一段命中 → `health.on_hit(來源 events)`——常被問到的記憶
衰減變慢(§4.1 代謝)。

## 7. 故障模式與恢復

| 故障 | 恢復 |
|---|---|
| index.db 壞/誤刪 | `vindex.rebuild`——衍生物,零資料損失 |
| .idx 與 JSONL 不一致 | `transcript.rebuild_idx` |
| 蒸餾 LLM 整晚失敗 | events 停在 trash,下輪重撈;agent_runs status=error 可查 |
| 換 embedding 模型 | meta 檢查不符 → 強制 rebuild + golden queries(backlog-007) |
| vault 筆記被手動改壞 frontmatter | ltm 解析失敗 → 跳過該篇 + events 記錄,不炸全庫 |

## 8. 已知限制

- FTS5 trigram:2 字中文查詢走 LIKE(無排名);詞彙表 tag 建議 ≥3 字
- decay 是線性而非 Ebbinghaus 曲線——個人量級夠用,參數可調(config)
- transcript keyword 搜尋是線性掃——月檔 10k 行 17ms,若未來單月 >100k 行
  再考慮 FTS 化(YAGNI)
- sqlite-vec 全表暴力 KNN(vec0 無 ANN 索引)——萬篇筆記內無感
