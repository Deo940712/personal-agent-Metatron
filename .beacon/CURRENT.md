# CURRENT

Part: part-005
Slice: slice-001
Status: active
Design authority: `.beacon/parts/part-005/DESIGN.md`
TODO source: `.beacon/parts/part-005/TODO.md#part-005-slice-001-octools--scanners三源唯讀掃描`

## Goal

三個確定性掃描器(git/beacon/opencode),全唯讀、全容錯。

## Allowed Scope

- [ ] `core/octools.py`:recent_sessions(mode=ro、毫秒轉秒、directory 正規化)、
      session_todos(完成率)、schema 容錯
- [ ] `core/scanners.py`:git_scan(subprocess 容錯、無 upstream 容忍)、
      beacon_scan(CURRENT 兩形態 parser、缺 .beacon → None)
- [ ] `tests/test_scanners.py`:tmp git repo 實測、假 opencode.db(同 schema)、
      假 CURRENT.md、boundary(非 git 目錄/壞 db/空表)

## Forbidden Scope

- LLM / track 管線(slice-002);MCP(part-006)
- 寫入任何被掃描的目標(全唯讀鐵律)

## Files-scope

core/octools.py, core/scanners.py, tests/test_scanners.py

## Expected Output

對本專案跑三掃描器回真實資料;壞輸入(非 git 目錄/壞 db/缺 .beacon)不 crash。

## Verification Plan

- Unit: `python -m pytest tests/test_scanners.py -q`
- Regression: `python -m pytest tests/ -q`(280 不壞)

## Current Blockers

None

## Recovery Incident

None
