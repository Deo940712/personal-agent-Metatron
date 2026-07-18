# part-003.1 TODO

Design authority: `.beacon/parts/part-003.1/DESIGN.md`

## SLICE Map

### part-003.1-slice-001: 雙語記憶架構契約

Status: active

Goal: 將目前實作、候選多層 context 方案及 agent capability/write authority 寫成
中英文等價、邏輯清楚且可機器驗證的權威文件。

Candidate scope:
- [ ] 重寫 `docs/MEMORY-zh.md` 與 `docs/MEMORY-en.md`
- [ ] 同步 `ARCHITECTURE.md`、`INTERFACES.md`、`docs/TOOLS.md`
- [ ] 同步 `README.md`、`README-en.md`、`AGENTS.md`
- [ ] 新增 `.beacon/verification/CheckMemoryDocs.py`
- [ ] 正向／負向文件探針 + 全 pytest + strict UnitTestCore

Forbidden scope:
- runtime/schema/API/dependency 變更
- 將 Task Capsule、warm set 或 LLM paging 宣稱為已採用
- direct DB/vault write、第二個 writer、常駐 conversation core
- part-006 slice-001+、part-007..010 或 vendored code

Verification target:
- `python .beacon/verification/CheckMemoryDocs.py`
- `python -m pytest tests/ -q`
- `powershell -ExecutionPolicy Bypass -File .beacon/verification/UnitTestCore.ps1 -Part part-003.1 -Slice slice-001 -Strict`

Done gate:
- 雙語章節與 MEM-01～MEM-17 完全一致
- A/B/C/D 狀態與決策門檻無歧義
- tool call 與 mutation authority 分離，且與目前程式一致
- 所有文件檢查與 regression 全綠
