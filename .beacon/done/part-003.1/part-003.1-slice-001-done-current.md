# DONE: part-003.1-slice-001 雙語記憶架構契約

Completed: 2026-07-15
Design authority: `.beacon/parts/part-003.1/DESIGN.md`

## 交付物

- `docs/MEMORY-zh.md` / `docs/MEMORY-en.md`:章節拓撲一致、`MEM-01`~`MEM-17`
  各一次、`[IMPLEMENTED]/[CANDIDATE]/[PLANNED]/[NON-GOAL]` 狀態一致。
- 多層記憶決策模型:A(現況,已實作)/ B(Task Capsule)/ C(受控 warm set)/
  D(LLM 自主 paging)分離;B/C/D 均為候選,D 不被永久否決。
- 工具權限與 writer 邊界:capability call 與 shared-state mutation authority 分離;
  agent/user proposal 走 `writer.apply`,受信任內部 job 走各自 deterministic
  validated write path;LLM 不持有 raw storage write primitive。
- 同步 `ARCHITECTURE.md`/`INTERFACES.md`/`docs/TOOLS.md`/`README*`/`AGENTS.md`。
- 新增 `.beacon/verification/CheckMemoryDocs.py`(標準函式庫、strict typing、
  117 純 LOC、含 stale-phrase 防漂移守衛)。

## Verification evidence

- `python .beacon/verification/CheckMemoryDocs.py` → `MEMORY_DOCS_OK`
- 四個負向探針(缺 invariant / 重複 invariant / 章節不符 / 斷鏈)全部非零退出
- `ruff check` clean;`lsp_diagnostics` 無錯誤
- `python -m pytest tests/ -q` → **326 passed**
- strict UnitTestCore part-003.1/slice-001 → PASS

## Review 修正(8 阻塞項全修)

1. ARCHITECTURE 八表 → 七表 + directives [PLANNED](含 DDL 標註)
2. 記憶契約 §4.1 補 RRF 融合 + 強命中短路 + RRF_K=60(中英)
3. recall 嚴格 found/not_found 引用契約標為 [PLANNED](README/README-en)
4. 「所有 shared-state mutation 經 writer」修正為 agent/user proposal 經 writer、
   內部 job 走各自 validated path(MEMORY/README/AGENTS/TOOLS)
5. README-en part-004.5 Planned → done
6. 測試數 314 → 326(README/README-en/ARCHITECTURE)
7. PLAN/ARCHITECTURE 的 `application.invoke` slice-0 → slice-001 [PLANNED]
8. 蒸餾欄位驗證補 title / topic(≤30 字)(中英)

## 未決 / 移交

- 多層記憶仍待以真實 workload 比較 A/B/C/D,再決定是否採 B。
- ECC(https://github.com/affaan-m/ECC)研究兩次逾時,無 source-backed 結論;
  留待有網路研究環境再評估,不影響本契約。
