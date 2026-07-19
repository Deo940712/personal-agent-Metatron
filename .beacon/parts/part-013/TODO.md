# part-013 TODO

Design authority: `.beacon/parts/part-013/DESIGN.md`

## SLICE Map

### part-013-slice-000: router +2 intent + directive/knowledge_list 落地

Status: done (2026-07-19; snapshot: `.beacon/done/part-013/part-013-slice-000-done-current.md`)
895 tests 綠(基線 888 + 7);真庫 808 篇 knowledge_list 0.15s 實測。

- [x] router + agents/router.md 加 directive + knowledge_list 兩 intent
- [x] memory.list_knowledge（vindex.all_tags 零檔案 I/O;筆記數+tag top10+最近5篇）
- [x] vindex.all_tags
- [x] chat 分派 directive→directive_add / knowledge_list→list_knowledge;
      移除過廣「知識」快徑前綴
- [x] tests：兩 intent 分類、directive 入佇列、knowledge_list 零 LLM+統計、
      「知識庫列表」不再 unclear（7 tests）
