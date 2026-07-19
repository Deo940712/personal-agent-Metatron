# part-014-slice-000 — dev_plan MCP 工具 + 儀表板常駐(done 2026-07-19)

Snapshot of CURRENT at completion.

## Goal(達成)

①MCP 加 dev_plan 讀 OpenCode plan/todo;②儀表板設常駐。

## Delivered

- `core/mcp/tools.py`:`_h_dev_plan` + 註冊(**第 11 工具**)——project 解析同
  dev_status(註冊名/路徑 fallback);recent_sessions(limit=3)+ session_todos
  組合;回每 session 的 {title, completed/total, in_progress, items};唯讀 opencode.db
- `tools/run_dashboard.cmd`:儀表板啟動包裝(cwd + python -X utf8;任意 cwd 可起)
- `tools/schedule_jobs.ps1`:加 `MyAgent-dashboard` 常駐 task(ONSTART 開機自啟,
  綁 127.0.0.1:7777);Remove-Jobs 一併清理
- `tests/test_mcp.py`:+5(dev_plan 註冊/路徑 fallback/無 session 空/tools-list 11 工具)

## Verification

- Unit: `python -m pytest tests/test_mcp.py -q` → 22 passed
- Regression: `python -m pytest tests/ -q` → **899 passed**(基線 895 + 4)
- Manual QA(真機):
  - `dev_plan my-agent` → 讀到真 OpenCode session todo:part-011 session 的
    7/7 completed(writer/consolidate/routine loop…)+ Pi Agents 規劃 session
  - run_dashboard.cmd 從任意 cwd 起 → GET / 200(1522 bytes);常駐 task 註冊成功

## Notes

- dev_plan vs dev_status:後者三源活動摘要,前者專門列 session 的 todo 進度細節。
- 儀表板常駐 ONSTART = 開機自啟;現在啟動用 `schtasks /Run /TN MyAgent-dashboard`。
  內網反代 upstream 指 127.0.0.1:7777(認證反代層自理)。
- opencode.db 全程唯讀(mode=ro;octools schema-tolerant 繼承)。
