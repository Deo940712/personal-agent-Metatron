# part-013-slice-000 — router +2 intent(directive + knowledge_list)(done 2026-07-19)

Snapshot of CURRENT at completion.

## Goal(達成)

真機兩缺口修復:①Discord 能留開發指令(directive intent);②知識庫可瀏覽總覽
(knowledge_list intent,非問答式)。

## Delivered

- `core/router.py` + `agents/router.md`:INTENTS 加 `directive` + `knowledge_list`;
  契約 few-shot 各補例(directive=留開發指令、knowledge_list=瀏覽總覽);
  knowledge 契約澄清為「問答」對照 knowledge_list「瀏覽」。
- `core/tools/memory.py`:`list_knowledge`——確定性知識庫總覽(筆記數 + tag 分布
  top10 + 最近 5 篇;**tag 統計走 vindex.all_tags 零檔案 I/O**,避免掃 808 篇
  frontmatter 卡住;吃 context.idx_db)。
- `core/vindex.py`:`all_tags(idx_db)`——從 notes_fts 展平 tags(容錯)。
- `core/chat.py` `_dispatch_routed`:directive→`stm.directive_add`(project=註冊
  首個 or 'general';回「已記下」)、knowledge_list→`list_knowledge`;
  **移除過廣的「知識」快徑前綴**(否則「知識庫列表」被吃成 recall)——`查 `/
  `search `/`recall `/`找筆記` 保留為明確快徑。

## Verification

- Unit: `python -m pytest tests/test_router.py tests/test_router_wiring.py -q` → 全綠
- Regression: `python -m pytest tests/ -q` → **895 passed**(基線 888 + 7)
- Manual QA(真庫 808 篇):list_knowledge **0.15s** 回總覽——ai-agents×134 /
  claude×128 / dev-frontend×104 / …(從卡住優化到瞬回,關鍵=走索引不掃檔案)。

## DESIGN Verification Targets 對照(五條)

- [x] 「留個指令:修 X」→ directive 入佇列(directives pending 讀得到)
- [x] 「我知識庫有什麼」→ tag 分布 + 最近幾篇(非單則問答)
- [x] 「知識庫列表」不再誤判 unclear(移除「知識」快徑前綴)
- [x] 快徑不變;寫入仍確認;router 失敗 fallback
- [x] knowledge_list 零 LLM(router 一次分類後,列表確定性)

## Notes

- knowledge_list 從 O(n) 讀 frontmatter(808 篇卡住)改走 vindex.all_tags——
  索引本來就存 tags,零檔案 I/O。真庫實測 0.15s。
- directive project 預設 'general';多專案「留給 X:...」語法留未來。
