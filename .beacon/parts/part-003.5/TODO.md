# part-003.5 TODO

Design authority: `.beacon/parts/part-003.5/DESIGN.md`
執行順序:part-006 slice-1 之後(stm 第八表先就位)。

## SLICE Map

### part-003.5-slice-001: 唯讀儀表板(stdlib http.server + 單頁)

Status: done (2026-07-16; snapshot: `.beacon/done/part-003.5/part-003.5-slice-001-done-current.md`)
608 tests 綠、UnitTestCore PASS、端到端 HTTP smoke + 5 對抗探針通過。技術選型:零依賴 stdlib http.server(非 FastAPI)。

Goal: 127.0.0.1:7777 唯讀儀表板,七版塊(含 directives)。

Outcome: 瀏覽器開 localhost:7777 見真資料;任何寫入方法 405。

Candidate scope:
- [x] `channels/dashboard.py`:**stdlib http.server**、8 個 GET API、內嵌單頁 HTML
      (route 純函式可單元測試)(30 tests)
- [x] 唯讀三層保證(GET-only、mode=ro 連線、無 stm 寫入函式呼叫;全實證)
- [x] pyproject:**無新依賴**(改用標準庫,不需 fastapi/uvicorn extra)
- [x] `tests/test_dashboard.py`:route 純函式——各 API 真資料/空 DB/405/mode=ro 實證/
      directives 表缺失容錯 + 端到端 HTTP smoke + 5 對抗探針
- [ ] 手動 QA:瀏覽器實開(`python -m channels.dashboard`,零安裝)(待使用者環境)

Files-scope: channels/dashboard.py, pyproject.toml, tests/test_dashboard.py

Forbidden scope:
- 任何寫入端點;認證;前端框架
- 改 core/(純消費既有讀取函式)

Verification target:
- Unit: `python -m pytest tests/test_dashboard.py -q`
- Regression: 全綠
- Manual QA: 瀏覽器 localhost:7777

Done gate:
- Phase 3.5 gate:六版塊真資料;寫入嘗試 405;物理唯讀實證
