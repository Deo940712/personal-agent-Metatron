# part-004 DESIGN

## Goal

知識庫進真資料:threads-sync 接入為第一個 sync skill → curator(評分/分類/去重)
→ recall(問答)。完成後:Threads 已存貼文入 vault、經 curator 正式入庫、
`recall("我存過哪些 RAG 貼文?")` 給出帶引用的答案。

## Non-goals

- x_sync / fb_sync 實作(x_sync 起步靠 xarchive 手動匯出,fb 要先 probe——
  皆獨立 slice 於本 part 之後,backlog-004)
- part-004.5 記憶強化(主題 trace / supersede / RRF)——先有資料才有得強化
- librarian(vault 有量才需要維護,backlog-017)

## 現實探勘(2026-07-13)

| 發現 | 後果 |
|---|---|
| threads-sync 原始碼**不在本機**(只在 GitHub Deo940712/threads-sync) | 遷入 = `git clone` 到 skills/threads_sync,非搬目錄 |
| 既有 vault(14 類 MOC、885 圖)**不在本機** | 不做「遷移既有 vault」;本機 vault 由 ltm.init_vault 全新初始化,threads-sync 的 VAULT_PATH 指到 config.VAULT_PATH。舊 vault 在原機器,之後使用者自行拷貝合併(記 backlog) |
| threads-sync 有自己的 config.py/state.db(獨立 SQLite) | **保持獨立**:skill 管線自帶狀態(threads-sync 的 store.py 管 post_id 去重),不併入 DB1。DB1 cursors 只記「上次成功執行時間/統計」——避免侵入式改造成熟專案 |
| threads-sync 輸出筆記 frontmatter 與 §5.2 有差(無 id/score/content_hash) | 不改 threads-sync 的 Transform;**curator 入庫時補齊**(id/content_hash/score 由 curator 流程產生) |

## Chosen Design

### 資料流(§6.5 統一管線的具體化)

```
threads-sync(獨立 skill,自帶 state.db)
  └─ 產出 .md → vault(tag=inbox,frontmatter 為 threads-sync 格式)
       └─ curator 批次(inbox 掃描):
            確定性前處理(非 LLM):content_hash 計算、跨源 URL/hash 去重、
                                  frontmatter 補齊(id 依 §5.2)
            → LLM 評分+分類(FIRE 拆卡精神:摘要+標籤;backlog-019 完整版後補)
            → classify_note 提案 → writer 驗證(tags ⊆ 詞彙表、score 界內、
                                    evidence 屬實、manual_tags 不覆蓋)
            → 低於閾值:只留 metadata(tag=low-score,不進 INDEX registry)
            → 通過:tag 正式化 + INDEX registry + vindex.upsert
       └─ recall:四段級聯檢索 → 帶引用回答
```

### 模組

| 檔案 | 職責 |
|---|---|
| `skills/threads_sync/` | git clone 的原專案(submodule 或 vendored clone;定 pin commit)。唯一改動:執行時以環境變數/參數覆蓋其 VAULT_PATH 指向 config.VAULT_PATH |
| `skills/runner.py` | skill 執行器:跑 threads-sync 的 1-5 步驟、捕捉 exit code、寫 DB1 cursors(last_run/new_count)+ agent_runs(status 含 login_expired 偵測) |
| `core/curator_pre.py` | 確定性前處理(非 LLM):掃 inbox tag 筆記、算 content_hash、跨源去重(URL 正規化+hash 比對)、補 §5.2 欄位 |
| `agents/curator.md` | LLM 契約:輸入=筆記全文批次;輸出=每篇 {score 0-10, tags ⊆ 詞彙表, summary ≤120字, evidence};閾值/配額規則 |
| `core/curate.py` | curator 管線:pre → LLM 批次 → 驗證 → writer(classify_note 落地=改 frontmatter+registry+vindex)→ 統計 |
| `agents/recall.md` | 代理型契約:唯讀工具白名單(index.search/note.read/vector.search/transcript.rehydrate);回答必附 note_id/url 引用;無來源不得斷言;查 superseded_by(欄位存在即查,執行在 004.5) |
| `core/recall.py` | recall 執行器:多步工具迴圈(上限 N 步)、引用格式化 |
| writer 擴充 | `classify_note` proposal 落地:frontmatter tags/score 更新(manual_tags 守衛)、registry 行更新 |

### 詞彙表擴充

INDEX.md 受控詞彙表加入 threads-sync 的 14 類 taxonomy(ai-agent 等已有,
補齊其餘)+ `low-score`。curator 提案的 tags 必須 ⊆ 詞彙表(writer 規則 2 首度全面生效)。

### 評分閘門(backlog-011 落地)

- score < 4.0(config 可調):tag=low-score,不進 registry/vindex(metadata 保留,原文在 vault)
- 分類配額:單次 curator 批次每 tag 上限 N 篇進 registry(防洪水;Horizon category_groups)

## Verification Targets

- runner:mock threads-sync(假 CLI 腳本)→ cursors/agent_runs 寫入、login_expired 偵測
- curator_pre:content_hash 穩定性、跨源去重(同 URL 兩篇 → 合併)、欄位補齊
- curate(mock LLM):評分閘門(低分不進 registry)、配額、manual_tags 不覆蓋、
  writer 驗證攔截(tags 出詞彙表/score 界外)
- recall(mock LLM+工具):引用存在於答案、無結果時誠實說找不到、步數上限
- 端到端(mock):假貼文 .md → curator → recall 檢索到 → 引用正確
- 手動 QA:真 threads-sync 跑一輪(需原機器的 cookies/session——**可能 blocked**)

## Unit Test Strategy

pytest;LLM/threads-sync 執行全 mock。threads-sync 本體不寫測試(成熟專案,
黑箱對待);runner 的整合點才測。

## Manual QA Strategy

真 threads-sync 需要 Playwright session(在原機器)。本機先用 xarchive 式假資料
(手工 .md 丟 inbox)驗 curator/recall 全流程;真 Threads 同步待 session 遷移
(記 blocked,與 API key 同批)。

## Risks

- threads-sync 的 VAULT_PATH 覆蓋方式要看其 config.py 實作——clone 後探勘,
  最壞情況 fork 改一行
- curator LLM 批次大小 vs 貼文長度(串文可達數千字)——每批 ≤10 篇,超長截斷至
  前 2000 字(evidence 仍需在截斷內)
- 詞彙表 14 類是否仍符合你現在的興趣——slice 中列出讓使用者確認

## Open Questions

- threads-sync 以 submodule 還是 vendored clone 進 repo?
  → 傾向 **vendored clone(pin commit,直接放 skills/)**:單人專案,submodule
  的間接性沒必要;要更新時手動拉。slice-001 實作時定案。
