# part-004.5 DESIGN

## Goal

記憶強化(backlog-022/023/024,依 2026 論文實證):①主題連續性蒸餾(Membox)
②矛盾偵測+supersede 執行(Mneme)③RRF 跨段融合檢索(Cognis)。完成後:同主題
跨天筆記自動串連、新舊偏好衝突時舊筆記標記+雙側可查、檢索不再「前段命中
就短路」而是多段候選融合排序。

## Non-goals

- Membox 完整 Topic Loom(滑動視窗即時斷句)——我們的 events 粒度已比對話粗,
  蒸餾時一次性主題標記已足夠,不做即時流式偵測
- cross-encoder rerank(backlog-025,觸發條件制,golden queries 出問題才做)
- per-category 衰減速率(backlog-026,觸發條件制,真實使用數據才調)
- Obsidian 手動開筆記回血(無 hook,known limitation,不動)

## 現有實作基礎(2026-07-13 現況)

| 模組 | 現況 | 本 part 改動點 |
|---|---|---|
| `consolidate.py` | `_group_by_day` 純按天;`_validate_group` 五條 | 分組加主題;驗證加第六條(supersedes);preference 蒸餾前注入既有 profile |
| `ltm.py` | `write_note`/`read_note`/`update_note_frontmatter` 無 supersede 支援 | 加 `mark_superseded`;write_note 支援 `supersedes` 欄位 |
| `retrieve.py` | `search()` 前段命中即返回(index→FTS→vec 依序 early-return) | 改三段並行取候選→RRF 合分;保留 index-first 強命中短路 |
| `writer.py` | 無 `supersede_note` proposal_type | 新增落地函式(供 consolidate 內部呼叫,不透過提案信封——蒸餾本身已是受信任管線) |

## Chosen Design

### 1. 主題連續性蒸餾(backlog-022)

`_group_by_day` 改兩階段分組:

```
按天分組(不變)→ 每天內容摘要送 LLM 標 topic(蒸餾契約新增 topic 欄位,
必填,自由文字如 "架構設計"/"RAG研究")→ 蒸餾筆記 frontmatter 加 topic 欄位
→ consolidate 收尾時掃「近 30 天內 topic 相同」的既有 episodic 筆記,
自動加雙向 related 連結(輕量 trace,非獨立資料結構)
```

不引入 Topic Loom 的即時斷句與 Trace Weaver 圖結構——`topic` 只是蒸餾契約
多一個欄位 + 收尾時的字串比對連結,零新模組。

驗證第六條:`topic` 非空字串(<=30 字)。

### 2. 矛盾偵測 + supersede 執行(backlog-023)

```
consolidate 蒸餾 preference 前:注入既有 agent/profile/ 的 INDEX 一行描述
(漸進揭露,§4.2 既定規則)→ LLM 若判斷新事實與某既有筆記矛盾/更新,輸出
{"supersedes": "<既有 note_id>"}(可選欄位)
→ 驗證:supersedes 若給,該 id 必須存在於 registry 且非已 superseded
→ 落地(ltm.write_note 已支援 frontmatter 任意欄位,新筆記帶 supersedes)
→ writer 新函式 mark_superseded(vault, old_id, new_id):舊筆記補
  superseded_by 欄位(update_note_frontmatter),不刪、不改內容
```

recall.md 契約加規則:讀到帶 `superseded_by` 的筆記 → 提醒使用者有更新版,
優先引用新版(§4.4 已在 agents/recall.md 埋了「查 superseded_by」的 TODO,
本 part 落地執行)。matrix 化雙側保留:兩篇都留在 vault,recall 讀到矛盾
(同 topic 兩篇分數相近)時在答案中並列說明,不擅自二選一斷言。

### 3. RRF 跨段融合(backlog-024)

`retrieve.search` 改寫:

```python
def search(...):
    idx_hits = _stage_index(...)          # 強命中(≥2 token 命中)→ 短路,零成本路徑保留
    if strong_index_hit(idx_hits, query):
        return idx_hits[:limit]

    fts_hits = _stage_fts(..., limit=limit*2)   # 候選池放大
    vec_hits = _stage_vec(..., limit=limit*2) if embed_fn else []
    fused = _rrf_fuse([idx_hits, fts_hits, vec_hits], k=60)  # RRF 標準常數
    return fused[:limit]
```

`_rrf_fuse`:對每個候選清單,依名次算 `1/(k+rank)`,同 note_id 跨清單加總,
排序取前 limit。純函數,~20 行,無外部依賴。

回血閉環(`_heal_sources`)不變,對融合後的 top-k 結果調用。

## Verification Targets

- 主題分組:同 topic 跨天筆記產生雙向 related;topic 驗證(空/超長拒絕)
- supersede:蒸餾產生 supersedes → 舊筆記 superseded_by 落地;supersedes
  指不存在 id → 驗證拒絕;recall 讀到 superseded_by 時的行為(mock)
- RRF:三段候選給定排名,驗證融合分數與排序符合 RRF 公式;強命中仍短路
  (零向量呼叫);全 miss 回空
- 迴歸:254 既有測試不壞(retrieve/consolidate 介面簽名盡量不變)

## Unit Test Strategy

pytest,LLM/embedding 全 mock。RRF 用手算固定排名驗證公式正確性
(不依賴真實檢索結果的模糊斷言)。

## Manual QA Strategy

無(本 part 全確定性可測;真 LLM 效果需 golden queries,backlog-007 待建)。

## Risks

- topic 字串自由文字,同義不同字(「RAG」vs「檢索增強」)不會被連結——
  已知限制,精確 clustering 需要 embedding 比對主題,本輪不做(過度工程)
- supersede 鏈過長(A→B→C)recall 需追多層——契約只要求查一層
  superseded_by,深鏈場景記已知限制

## Open Questions

無——三項設計已由使用者原話定案,細節皆為程式面決定。
