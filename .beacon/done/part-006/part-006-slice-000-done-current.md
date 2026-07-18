# DONE: part-006-slice-000 能力工具基座

Completed: 2026-07-15
Design authority: `.beacon/parts/part-006/DESIGN.md`

## Goal delivered

使用者可見能力已收斂到 `core/tools/` typed capability layer；CLI／Discord／未來
MCP 共用 contracts/catalog，低階 `stm`／SQL／writer dispatch 保持 private。

## Verification evidence

- `python -m pytest tests/test_tools.py tests/test_chat.py tests/test_recall.py -q`
  → **47 passed**
- `python -m pytest tests/ -q` → **326 passed**
- `powershell -ExecutionPolicy Bypass -File .beacon/verification/UnitTestCore.ps1 -Part part-006 -Slice slice-000 -Strict`
  → PASS
- Fresh-process CLI smoke：`stm init`、`schedule list`、`tasks list`、`projects show`
  → exit 0；DB1 現有七表可讀

## Boundary retained

- `application.invoke`、pending atomic claim、strict recall contract 留在 slice-001。
- MCP stdio/directives 留在 slice-002；HTTP/Tailscale 留在 slice-003。
- writer 仍是 deterministic shared-state commit boundary；未新增第二個 apply path。
