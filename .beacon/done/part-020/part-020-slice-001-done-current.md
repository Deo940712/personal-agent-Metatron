# CURRENT

Part: part-020
Slice: slice-001
Status: active ??promoted 2026-08-03 (part-019 paused at Gate B, archived to `.beacon/done/part-019/`)
Design authority: `.beacon/parts/part-020/DESIGN.md`
TODO source: `.beacon/parts/part-020/TODO.md#slice-001`

## Goal

Harden the existing `http.server` dashboard against malformed inputs (W1), isolate index DB access (W2), and replace localized text-prefix success detection with structured outcomes (M2).

## Allowed Scope

- [ ] Add `Content-Length` boundary checks in `channels/dashboard.py` `_read_json`: reject missing, zero, negative, or >65536 byte body with HTTP 400.
- [ ] Ensure `idx_db` is passed through confirm path via `core/chat.confirm` ??`writer.apply_validated` when custom vault is provided (W2).
- [ ] Add structured `ok`/`code`/`message` fields to POST responses in `route()`; remove `startswith("??)` success inference (M2).
- [ ] Add unit tests covering boundary/malformed Content-Length, idx_db isolation, and structured outcomes.
- [ ] Write operational probe script `scripts/probes/probe_dashboard_post_bounds.py` (new).

## Files-scope

- `channels/dashboard.py`
- `tests/test_dashboard.py`
- `scripts/probes/probe_dashboard_post_bounds.py` (new)

## Forbidden Scope

- Do not migrate to FastAPI or any other framework.
- Do not change runtime code outside `channels/dashboard.py`, `core/chat.py`, `core/tools/tasks.py`, and the listed test/probe files.
- Do not modify vault Topic/Evidence content, DB1 schema, or Windows Task Scheduler tasks.
- W1/W2/M2 may be marked `fixed@020-1` only after focused tests, full regression, and the operational probe pass.

## Verification Plan

- Unit: `python -m pytest tests/test_dashboard.py -q`
- Regression: `python -m pytest tests/ -q`
- Operational QA: `python scripts/probes/probe_dashboard_post_bounds.py` against `http://127.0.0.1:7777` and verify HTTP 400 for invalid/missing/zero/negative/oversize Content-Length

## Done Gate

- W1/W2/M2 fixes are implemented and tests pass
- Full regression `python -m pytest tests/ -q` exits 0
- Operational probe reports correct rejection behavior
- KNOWN_ISSUES.md updated with `fixed@020-1` evidence after repository-level tests and probe pass

