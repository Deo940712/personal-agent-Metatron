# part-003.5 TODO

Design authority: `.beacon/parts/part-003.5/DESIGN.md`
執行順序:part-006 slice-1 之後(stm 第八表先就位)。

## SLICE Map

### part-003.5-slice-001: 唯讀儀表板(FastAPI + htmx 單頁)

Status: planned

Goal: 127.0.0.1:7777 唯讀儀表板,六版塊(含 directives)。

Outcome: 瀏覽器開 localhost:7777 見真資料;任何寫入方法 405。

Candidate scope:
- [ ] `channels/dashboard.py`:FastAPI app、8 個 GET API、內嵌單頁 HTML(htmx)
- [ ] 唯讀三層保證(GET-only 路由、mode=ro 連線、測試斷言)
- [ ] pyproject:`[dashboard]` optional extra(fastapi + uvicorn)
- [ ] `tests/test_dashboard.py`:TestClient——各 API 真資料/空 DB/405/mode=ro 實證/
      directives 表缺失容錯
- [ ] 手動 QA:瀏覽器實開(需 pip install fastapi uvicorn)

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
