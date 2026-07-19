# part-013 DESIGN — 對話層補兩個意圖(directive + knowledge_list)

## Goal

真機使用後兩個體感缺口:
1. Discord 問「留開發指令給下次 session」→ router 沒有 directive 意圖 → 回「不確定」
2. 問「我知識庫有什麼」→ recall 是問答式,只回一則最相關;缺「列表/瀏覽」

part-013 給 router 加兩個 intent + 對應能力。**寫入紀律不變**。

## Non-goals

- 不改寫入紀律(directive_push 本來就無副作用,只入佇列)
- 不做知識庫全文瀏覽器(列表 = tag 統計 + 最近幾篇,不是分頁全列)
- 不讓 knowledge_list 走 LLM(確定性讀 registry,零成本)

## Chosen Design

### router 加兩個 intent

```
現有七 intent + 兩個:
- directive:留開發指令給下次 session
  例:「留個指令:修 dev_status」「下次記得跑測試」「提醒下次 session 做 X」
  → argument = 指令內容 → directive_push(預設 project=當前註冊專案 / 或 'general')
- knowledge_list:瀏覽知識庫有什麼(不是問答)
  例:「我知識庫有什麼」「知識庫列表」「有哪些主題」「最近存了什麼」
  → 確定性:tag 統計 top-N + 最近 M 篇標題(零 LLM)
```

### directive intent 落地

- router 分類 directive → argument = 指令原文
- chat 分派 → `stm.directive_add(db, project, text)`
- project:若有註冊專案取第一個;否則 'general'(先簡單,不追問)
- directive 無副作用(只入佇列),免確認;回「已記下,下次 session 開場會讀到」

### knowledge_list intent 落地

- 確定性讀 `ltm.registry_entries` + 各筆 note frontmatter 的 tags
- 輸出:總筆記數 + tag 分布(top 10)+ 最近 5 篇標題
- 零 LLM;新增 `core/tools/memory.py:list_knowledge(context)`

### 對話層邊界(不變)

- 快徑保留;router 仍單次 cheap LLM;寫入意圖仍 preview→confirm
- directive/knowledge_list 皆無需確認(前者只入佇列、後者唯讀)

## Verification Targets

- 「留個指令:修 X」→ directive 入佇列;`directives pending` 讀得到
- 「我知識庫有什麼」→ 列 tag 分布 + 最近幾篇(不是單則問答)
- 「知識庫列表」不再誤判成 unclear
- 快徑不變;寫入仍確認;router 失敗 fallback 不中斷
- knowledge_list 零 LLM(mock 斷言)

## Unit Test Strategy

pytest;router mock 兩新 intent 分類;directive 入佇列測真;knowledge_list
確定性測真(種幾筆筆記 → 驗 tag 統計 + 最近篇)。

## Manual QA Strategy

Discord:「留個指令:下次修 dev_status」→ 確認 directives pending 有;
「我知識庫有什麼」→ 列出 tag 分布(threads 808 篇的真實主題)。

## Risks

- directive project 預設 'general':多專案時可能留錯專案——先簡單,未來可加
  「留給 X 專案:...」語法(router argument 解析)
- knowledge_list tag 統計掃全 registry:808 篇 O(n) 讀 frontmatter——個人量級
  可接受(<1 秒);超大庫再加快取
