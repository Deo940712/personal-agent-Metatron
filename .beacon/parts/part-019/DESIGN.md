# part-019: Evidence 全面整理（批次 Topic 化）

> Status: slice-001 executable；閘門 A 已通過，正在起草並將停在閘門 B
> Created: 2026-07-24
> Parent: `.beacon/parts/part-018/DESIGN.md`（Topic/Evidence 雙層架構）、ARCHITECTURE.md §4
> 使用者需求原文：「那可以幫我把所有的筆記這樣整理嗎」「好」（每批先確認後落地 + 先試整理 30–50 篇）

## 1. 問題陳述

part-018 完成 KB 2.0 雙層架構並以 21 篇貼文做了 5 篇 seed Topic Notes，但 vault 仍有 **786 篇未整理 Evidence**（`note_type: evidence`、無 `consolidated_into`）。若維持現狀：

- Topic-first 檢索只涵蓋 5 個主題，絕大多數知識仍需 `include_evidence` 才能找到，雙層架構紅利無法兌現。
- Evidence 持續從 sync/scout 管線累積，資料孤島會繼續擴大。

## 2. 設計目標

1. **全庫 Topic 化**：786 篇 Evidence 依主題聚合成 Topic Notes，格式與品質對齊 part-018 的五篇 seed。
2. **每批先確認後落地（Anael-lite 半自動）**：分群提案 → 使用者確認 → 草稿 → 【使用者 Gate B：確認調整草稿】 → 使用者確認 → 才寫入。不做全自動合併。
3. **無損**：Evidence 永不刪除、不移動；只加 `consolidated_into` 反向連結。每批落地前備份、落地後驗證。
4. **可校準**：先 30–50 篇 pilot 確立分群粒度與文風，再放大到全庫。
5. **可持續**：建立新 Evidence 累積後的定期整理觸發，避免再次堆成孤島。

## 3. 非目標

- **不做動態分類系統**：本 part 沿用現有受控標籤與語意分群。（保留為 backlog 想法）
- **不做全自動 Anael**：自主偵測+自動落地是後續 part；本 part 每批都要使用者確認。
- **不做 GUI 編輯器**。（保留為 backlog 想法）
- **不修改 Evidence 檔案路徑與內文**：僅 frontmatter 加連結。
- **不硬湊孤立筆記**：無法合理成群的筆記保留為 evidence，不為了「整理完」而製造假主題。

## 4. 批次流程（每批固定六步）

```
掃描 → 分群提案 →【使用者閘門 A：確認/調整分群】→
草稿 → 【使用者 Gate B：確認調整草稿】（每群一篇 Topic Note）→【使用者閘門 B：確認/調整草稿 → 【使用者 Gate B：確認調整草稿】】→
落地（寫 topic + 標 evidence + INDEX + 重建索引）→ 驗證
```

1. **掃描**：deterministic 腳本輸出所有未整理 evidence 的 metadata（id/title/tags/date/summary）到暫存 JSON（放 TEMP，不入 repo）。
2. **分群提案**：以 tags + 標題語意分群；每群 2–15 篇；孤立篇排除。提案含：群名（topic id 候選）、evidence IDs、一句分群理由、預估類型（目錄型/程序型/事件型/原則型/比較型，沿用 part-018 五篇的類型學）。
3. **草稿 → 【使用者 Gate B：確認調整草稿】**：逐群讀 evidence 全文，產繁中 Topic Note，結構沿用 seed：frontmatter（note_type/topic_status/source_evidence/last_consolidated/consolidation_version/tags/summary）+ 摘要段 + 分節知識 + 限制/來源限制 + 來源證據清單。數字、星數、效能等未驗證宣稱一律保留「來源聲稱」語氣。
4. **落地**：批次腳本（dry-run 先行）寫 Topic Notes、更新 evidence frontmatter、更新 INDEX registry、重建 `index.db`；落地前對該批 evidence 做 `.backup/` 快照。
5. **驗證**：topic schema、evidence 反向連結、registry 路徑可解析、索引筆數 = 累計 topic 數、topic-first 搜尋命中新 topic、`pytest tests/ -q` 全綠。
6. **紀錄**：每批結果（群數、篇數、孤立數）記入 TODO/VERIFICATION。

## 5. Pilot 設計（slice-001）

- **範圍**：30–50 篇未整理 evidence，預期成 4–8 群；選擇標準 = tags/標題訊號最密集、主題邊界最清楚的家族。
- **產出**：分群提案文件 + 經確認的草稿 → 【使用者 Gate B：確認調整草稿】 + 落地 + 驗證。兩道使用者閘門都在 slice 內（自然暫停點）。
- **目前狀態**：`.beacon/parts/part-019/cluster-proposal-pilot.md` 的 7 群 × 49 篇已於 2026-07-25 通過閘門 A；目前逐篇讀全文起草，未修改 vault，草稿 → 【使用者 Gate B：確認調整草稿】完成後停在閘門 B。
- **校準點**（pilot 後回答）：一群理想篇數？文風是否要更精簡/更詳細？哪些主題家族其實該拆或該併？孤立率多少可接受？

## 6. 全庫批次（slice-002）

- pilot 校準後，把剩餘 737 篇按主題家族切成數批（每批 ≤150 篇），重複本文件第 4 節流程。
- 孤立內容留待批次完成後，依固定孤立原因歸入 INDEX 附錄，不建立雜項目錄 (misc Topic)。

## 7. 維護迴圈（slice-003）

- 新 evidence 累積觸發：consolidate/advisor job 或手動掃描，當同主題未整理 evidence ≥ 門檻（初值 5 篇）→ 產「建議整理」提案（沿用 pending/確認機制，不自動落地）。
- 文件：USER-GUIDE 補「整理流程怎麼用」、MEMORY-zh 補維護觸發參數。

## 8. 風險與緩解

| 風險 | 緩解 |
|------|------|
| 錯誤分群把不相干筆記併成一題 | 閘門 A 使用者確認；分群理由必寫；pilot 先校準粒度 |
| Topic 內容把未驗證資訊寫成事實 | 沿用 seed 慣例：數字/宣稱保留「來源聲稱」；每篇必有「來源限制」段 |
| 批次落地中斷造成半套連結 | 批次腳本 idempotent + dry-run + backup + rollback（沿用 part-018 migration 模式） |
| 786 篇全讀進 context 爆炸 | metadata 掃描 → 只對入選群讀全文；每批 ≤150 篇 |
| 文風漂移（與 seed 五篇不一致） | 草稿 → 【使用者 Gate B：確認調整草稿】前先讀 seed 五篇；閘門 B 使用者把關 |
| LLM 輔助分群/起草的 key 不可用 | 降級為 agent 親讀親寫（本 part 不依賴外部 LLM 才能進行） |

## 9. 驗證標準（Definition of Done）

- [ ] Pilot 30–50 篇完成兩道閘門並落地，索引與搜尋行為正確
- [ ] 全庫 786 篇處理完畢：成群者已連結 topic，孤立者明示保留原因
- [ ] 每批 `pytest tests/ -q` 全綠、索引重建為累計 topic-only、registry 無 missing path
- [ ] 維護觸發機制與文件落地
- [ ] 使用者對各批品質確認（每批閘門 B 為準）
