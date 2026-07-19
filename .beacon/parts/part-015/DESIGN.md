# part-015 DESIGN — 知識庫 CRUD + 三層下鑽檢索 + INDEX 中文化

## Goal

三個使用者需求:
1. **CRUD**:Discord 對話新增/修改/刪除知識庫筆記(寫入走 writer 確認)
2. **三層下鑽**:主題 → 筆記 → 內容,逐層點進去(不只問答)
3. **INDEX 中文化**:INDEX.md 說明文字改中文(tag 保持英文——系統識別碼)

## Non-goals

- 不 tag 中文化(808 篇 tags + curator 詞彙表工程大,決定只改說明)
- 不繞過 writer(CRUD 全走提案→驗證→確認;delete 也要確認)
- 不做多輪對話狀態(下鑽是單則回覆帶選項,不是 session 記憶)
- 不物理刪原始記錄(delete = vault 檔+索引+registry+黑名單;transcript 永存)

## Chosen Design

### 一、知識庫 CRUD(走 writer,Discord 對話)

新 proposal type `note_write`(action: create | edit | delete):

```jsonc
{ "proposal_type": "note_write",
  "payload": {
    "action": "create|edit|delete",
    "note_id": "...",          // edit/delete 必填
    "title": "...",            // create/edit
    "body": "...",             // create/edit
    "tags": [...]              // create/edit(受控詞彙表)
  } }
```

- router 加 3 intent:`note_create` / `note_edit` / `note_delete`
- **全部需確認**(§3.2 寫入閘門;delete 尤其)
- writer `apply_note_write`:
  - create → `ltm.write_note`(semantic)+ vindex.upsert
  - edit → `ltm.update_note_frontmatter` + 改 body + vindex 重 upsert
  - delete → 三處刪(vault/index/registry)+ 黑名單(復用 delete_note.py 邏輯)
- 新 ltm 原語 `delete_note(vault, note_id, idx_db)`(把 delete_note.py 的核心
  抽進 ltm,writer 與 CLI 共用)

### 二、三層下鑽檢索(主題→筆記→內容)

無狀態下鑽:每層回「選項 + 下一步指令」,使用者用 id/序號點進去。

```
L1 主題:「瀏覽知識庫」→ list_knowledge(現有,tag 分布)
   → 回:「輸入主題名看該類筆記,如『看 rag-knowledge』」
L2 筆記:「看 <tag>」→ browse_topic(tag) → 列該 tag 前 N 篇標題 + id
   → 回:「輸入 id 看內容,如『看筆記 20260702-xxx』」
L3 內容:「看筆記 <id>」→ open_note(id) → 該篇 frontmatter 摘要 + 內文
```

- router 加 2 intent:`browse_topic`(argument=tag)、`open_note`(argument=id)
- 或快徑:「看 <tag>」「看筆記 <id>」前綴直達(零 LLM)——傾向快徑(明確)
- 全確定性讀取,零 LLM;無狀態(每層獨立指令,不需記住上一步)

### 三、INDEX 中文化

`core/ltm.py` `_INDEX_TEMPLATE`:標題/說明改中文;tag 清單不變。
既有 vault 的 INDEX.md 開頭已生成(英文)——需一次性遷移(改開頭說明段,
保留 Registry 那 807 行不動)。

## Verification Targets

- Discord「新增筆記:標題X 內容Y」→ 預覽 → 確認 → 入知識庫 + 可檢索
- 「改筆記 <id>:...」→ 確認 → 更新;「刪筆記 <id>」→ 確認 → 三處刪+黑名單
- 「看 rag-knowledge」→ 列該 tag 筆記;「看筆記 <id>」→ 內容
- 下鑽零 LLM(快徑);CRUD 全走確認
- INDEX.md 說明中文;tag 仍英文
- delete 走 writer 與 delete_note.py 行為一致(黑名單+三處)

## Unit Test Strategy

pytest;note_write proposal 驗證 + writer 三 action 落地(真 vault/index);
router 新 intent mock 分類;browse_topic/open_note 確定性讀取測真;
INDEX 中文化字串斷言。

## Manual QA Strategy

Discord:新增一篇→查得到→改→刪(確認黑名單);「看 claude」列 claude 筆記→
「看筆記 <id>」開內容。

## Risks

- delete 破壞性:走確認 + 黑名單可稽核 + transcript 原文永存(可回水)——
  不做物理不可逆刪除
- create 的 tag 需在受控詞彙表:writer 驗證(同 classify_note 規則)
- 下鑽無狀態:使用者需帶 id/tag,不能「上一個」——可接受(指令明確)

## Open Questions

- create 的 body 從 Discord 多行輸入:Discord 訊息可含換行,直接吃——slice 定
- browse_topic 分頁:tag 下可能上百篇(如 ai-agents×134)——先列前 20 + 提示,
  slice 定
