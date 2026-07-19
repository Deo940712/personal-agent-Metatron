# part-014 DESIGN — MCP dev_plan 工具 + 儀表板常駐

## Goal

真機兩需求:
1. MCP 能讀 OpenCode 的 plan/todo(opencode.db todo 表有 86 session/109 todo,
   但缺專用工具撈出來)——加 `dev_plan` MCP 工具
2. 後台管理(唯讀儀表板,七版塊)存在但沒常駐——設成排程常駐 + 內網反代

## Non-goals

- 不改 opencode.db(唯讀,永不寫)
- 不做 plan 編輯(只讀 OpenCode 自己的 todo)
- 儀表板仍純唯讀(GET-only + mode=ro,不因常駐而開寫入)

## Chosen Design

### dev_plan MCP 工具

octools 已有 `recent_sessions(directory)` + `session_todos(session_id)`——組合:

```
dev_plan(project) →
  1. 解析 project(註冊名 → repo_path,或直接路徑)——同 dev_status
  2. recent_sessions(repo, limit=3) 取最近 sessions
  3. 各 session_todos(sid) 取 todo 進度
  4. 回:每 session 的 {title, todo total/completed/in_progress, items[:5]}
```

- 唯讀,無副作用,免確認
- 回答「我這專案的 plan 做到哪了」——比 dev_status(只活動摘要)更細

### 儀表板常駐

- 加進 `tools/schedule_jobs.ps1`:一個常駐 task(開機自啟,綁 127.0.0.1:7777)
- 或獨立 `tools/run_dashboard.cmd`(同 run_job.cmd 模式)
- 內網反代 upstream 指向 127.0.0.1:7777(使用者反代自理認證)
- 儀表板本身不變(part-003.5 已完成;三層唯讀保證)

## Verification Targets

- dev_plan(已註冊專案) → 回最近 sessions 的 todo 進度
- dev_plan(直接路徑) → 同 dev_status 的路徑 fallback
- dev_plan 唯讀(不寫 opencode.db)
- 無 opencode session 的專案 → 空進度不 crash
- 儀表板常駐腳本 idempotent 註冊/移除

## Unit Test Strategy

pytest;dev_plan mock octools(recent_sessions/session_todos);MCP tools.call
整合;唯讀驗證(mode=ro)。儀表板常駐是 ops 腳本(手動 QA)。

## Manual QA Strategy

MCP:`dev_plan` 對 MY AGENT 專案 → 讀到真 OpenCode session 的 todo 進度。
儀表板:跑常駐腳本 → 反代/localhost 開 → 七版塊有真資料。

## Risks

- opencode.db schema 版本變(OpenCode 升級)——octools 已 schema-tolerant(缺表/
  缺欄回空,不 crash),繼承此容錯
- 儀表板常駐佔一個 port——127.0.0.1 本機自用,反代對外
