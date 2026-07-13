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

### 技術(INTERFACES §5.2 已定)

- `channels/dashboard.py`:FastAPI app + 內嵌單頁 HTML(一個檔案,零 build)
- 資料存取:`sqlite3.connect("file:...?mode=ro", uri=True)`(物理唯讀,
  同 octools 慣例);vault 讀取走 ltm(本就唯讀函式)
- 啟動:`python -m channels.dashboard` → uvicorn 綁 127.0.0.1:7777
- 依賴:fastapi + uvicorn 進 optional-dependencies `[dashboard]`

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

1. FastAPI 只註冊 GET 路由(方法級)
2. SQLite `mode=ro` URI(連線級——寫入嘗試 = sqlite 錯誤)
3. 測試斷言:POST 各端點 → 405;dashboard 模組 import 不含 stm 寫入函式呼叫

## Verification Targets

- 各 API 回真資料(對測試 DB);空 DB 回空陣列不炸
- POST/PUT/DELETE → 405
- `mode=ro` 實證:dashboard 的連線嘗試寫 → sqlite 錯誤
- directives 表不存在時(part-006 未跑) → /api/directives 回空(容錯)
- 手動 QA:開瀏覽器 localhost:7777,五+1 版塊有真資料

## Unit Test Strategy

fastapi TestClient(不起真 server);測試 DB 塞假資料。

## Risks

- fastapi/uvicorn 依賴較重——optional extra 隔離,核心不受影響
- 單頁 HTML 內嵌 py 檔會長——可接受(零 build 換單檔;超過 ~300 行再拆 static)

## Open Questions

無。
