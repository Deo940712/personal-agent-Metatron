# part-014 TODO

Design authority: `.beacon/parts/part-014/DESIGN.md`

### part-014-slice-000: dev_plan MCP 工具 + 儀表板常駐腳本

Status: done (2026-07-19; snapshot: `.beacon/done/part-014/part-014-slice-000-done-current.md`)
899 tests 綠(基線 895 + 4);dev_plan 真機讀到 part-011 session 7/7 todo;儀表板常駐實測。

- [x] `core/mcp/tools.py`：`_h_dev_plan` + 註冊(第 11 工具;路徑 fallback;
      recent_sessions + session_todos)
- [x] `tools/run_dashboard.cmd`：儀表板包裝(任意 cwd 可起)
- [x] `tools/schedule_jobs.ps1`：MyAgent-dashboard 常駐 task(ONSTART)
- [x] tests：dev_plan 註冊/路徑 fallback/無 session 空/tools-list 11 工具(5 tests)
