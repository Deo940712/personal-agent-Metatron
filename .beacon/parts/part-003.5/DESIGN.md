# part-003.5 DESIGN

## Goal

唯讀網頁儀表板(INTERFACES.md §5 為介面權威):FastAPI + 單頁 htmx、
綁 127.0.0.1:7777、SQLite `mode=ro` 物理唯讀。一眼總覽:今日行程/專案進度/
管線健康/記憶狀態/事件流。

## Non-goals

- 任何寫入(寫入會繞過預覽+確認流;嘗試寫 → 405)
- 登入/認證(本機自用;遷 VPS 後要遠端看再加 Tailscale,同 MCP slice-2 哲學)
- 前端框架(React 等——一頁儀表板上框架就是肥大的開始;htmx/原生 fetch)

## 執行順序(與 part-006 的協調)

part-006 slice-1 先行(改 stm.py 加 directives 表);本 part 後行。
Files-scope 無重疊(channels/dashboard.py + tests/test_dashboard.py 全新檔),
但儀表板可順帶顯示 directives 佇列(第八表就位後)——多一個版塊,零成本。

## Chosen Design

### 技術(2026-07-16 定案:零依賴 stdlib http.server)

**傳輸選型修訂**:原 DESIGN 指定 FastAPI + uvicorn,但兩者未安裝且為重依賴。
使用者定案改用 Python 標準庫 `http.server`——對齊專案最小依賴哲學(pyproject 僅
openai + sqlite-vec),同 part-006-slice-002 選手寫 JSON-RPC 而非 mcp SDK 的先例。
一個唯讀單頁儀表板不需要 web 框架;stdlib 零 build、零新依賴、可完整單元測試。

- `channels/dashboard.py`:`http.server.BaseHTTPRequestHandler` + 內嵌單頁 HTML
  (一個檔案,零 build);純函式 route dispatch 可單元測試(不起真 server)
- 資料存取:`sqlite3.connect("file:...?mode=ro", uri=True)`(物理唯讀,
  同 octools 慣例);vault 讀取走 ltm(本就唯讀函式)
- 啟動:`python -m channels.dashboard` → `http.server` 綁 127.0.0.1:7777
- 依賴:**無新依賴**(標準庫)

### API(INTERFACES §5.3 + directives 版塊)

| 端點 | 回傳 | 來源 |
|---|---|---|
| `GET /api/today` | 今日行程 + 未完結待辦 | schedule, tasks |
| `GET /api/projects` | 專案進度(track 的產出) | projects |
| `GET /api/runs?limit=20` | 最近執行 | agent_runs |
| `GET /api/pipelines` | 各管線 last_run cursor | cursors |
| `GET /api/memory` | events 狀態統計 + registry 筆數 + inbox 待整理數 | events, vault |
| `GET /api/events?limit=50` | 最近事件流 | events |
| `GET /api/directives` | 指令佇列(part-006 表就位後) | directives |
| `GET /health` | {ok: true} | — |
| 其他方法(POST/PUT/DELETE) | **405** | — |

### 唯讀保證(三層)

1. handler 只處理 GET(`do_GET`);`do_POST`/`do_PUT`/`do_DELETE` 一律回 405(方法級)
2. SQLite `mode=ro` URI(連線級——寫入嘗試 = sqlite 錯誤)
3. 測試斷言:POST 各端點 → 405;dashboard 模組不呼叫任何 stm 寫入函式

## Verification Targets

- 各 API 回真資料(對測試 DB);空 DB 回空陣列不炸
- POST/PUT/DELETE → 405
- `mode=ro` 實證:dashboard 的連線嘗試寫 → sqlite 錯誤
- directives 表不存在時(part-006 未跑) → /api/directives 回空(容錯)
- 手動 QA:開瀏覽器 localhost:7777,五+1 版塊有真資料

## Unit Test Strategy

純函式 `route(method, path, query, db)` -> `(status, content_type, body)`(不起真
server);測試 DB 塞假資料。另以標準庫 `http.client` 對 in-process server 做一次
端到端 smoke(可選)。

## Risks

- 單頁 HTML 內嵌 py 檔會長——可接受(零 build 換單檔;超過 ~300 行再拆 static)
- stdlib http.server 是單執行緒——本機自用單使用者足夠;需並發再評(VPS 階段)

## Open Questions

無。
