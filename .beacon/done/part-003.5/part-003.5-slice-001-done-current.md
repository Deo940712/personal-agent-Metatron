# DONE: part-003.5-slice-001 唯讀網頁儀表板

Completed: 2026-07-16
Design authority: `.beacon/parts/part-003.5/DESIGN.md`

## Goal delivered

127.0.0.1:7777 唯讀網頁儀表板,七版塊一眼總覽:今日行程/待辦、專案進度、最近執行、
管線游標、記憶狀態、事件流、指令佇列。零新依賴、三層唯讀保證。

## 技術選型決策(DESIGN 修訂)

原 DESIGN 指定 FastAPI + uvicorn,但兩者未安裝且為重依賴。使用者定案改用 Python
**標準庫 `http.server`**——對齊專案最小依賴哲學(pyproject 僅 openai + sqlite-vec),
同 part-006-slice-002 選手寫 JSON-RPC 而非 mcp SDK 的先例。一個唯讀單頁儀表板不需
web 框架。DESIGN 已更新記錄此決策與理由。

## 三層唯讀保證(全部實證)

1. **方法級**:handler 只處理 GET;POST/PUT/DELETE/PATCH → 405。
2. **連線級**:SQLite `mode=ro` URI——寫入嘗試 = sqlite OperationalError。
3. **靜態**:dashboard 模組不呼叫任何 stm 寫入函式(測試 + 探針斷言)。

## Verification evidence

- 目標測試 `test_dashboard.py` → **30 passed**(8 API 真資料、空 DB 容錯、
  directives 缺失容錯、非 GET 405、404、mode=ro 唯讀實證、無 stm 寫入呼叫)
- `python -m pytest tests/ -q` → **608 passed**(原 578 + 新增 30,零回歸)
- `UnitTestCore.ps1 -Part part-003.5 -Slice slice-001` → PASS
- Ruff 全清、LSP 零 error
- **端到端 smoke(真 HTTP server + http.client)**:GET /health、GET /(HTML)、
  GET /api/today、GET /api/directives 回真資料;POST/DELETE → HTTP 405
- **對抗式探針(實跑)5/5 通過**:
  1. mode=ro 連線 INSERT/UPDATE/DELETE 全拒,資料不變
  2. 所有非 GET 方法 → 405(無寫入路徑)
  3. directives 表缺失 → 空 list,不 crash
  4. dashboard 原始碼零 stm 寫入函式引用(靜態)
  5. 未知路徑 404;壞 query 參數安全 fallback

## 交付檔案

channels/dashboard.py(http.server + route 純函式 + 8 GET API + 內嵌單頁 HTML)、
tests/test_dashboard.py、.beacon/parts/part-003.5/DESIGN.md(技術選型修訂)、
.beacon/verification/manifest.json

## Boundary retained

- 純消費既有讀取函式;未改 core/。無寫入端點、無認證、無前端框架。
- 綁 127.0.0.1(本機自用,不上公網;遠端看留 Tailscale,同 MCP 哲學)。
- 無新依賴(標準庫);dirty worktree 無關變更未動;無 git commit。

## 手動 QA(待使用者)

- `python -m channels.dashboard` → 瀏覽器開 http://127.0.0.1:7777,七版塊真資料。
