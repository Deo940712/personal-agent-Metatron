# CURRENT

Part: part-020
Slice: slice-005
Status: active — promoted 2026-08-03 after slice-004 verification and audit
Design authority: `.beacon/parts/part-020/DESIGN.md`
TODO source: `.beacon/parts/part-020/TODO.md#slice-005`

## Goal

Close part-020 with a deterministic cross-check that all reliability slices have evidence, issue dispositions are honest, and part-021 prerequisites are met.

## Allowed Scope

- [ ] Add `scripts/probes/probe_part_020_closure.py` (new) to validate design/TODO/evidence/issues consistency.
- [ ] Update `KNOWN_ISSUES.md` only when originating slice evidence supports fixed/mitigated status.
- [ ] Review/update part-020 DESIGN/TODO documentation if the closure probe finds a contradiction introduced by part-020.

## Files-scope

- `scripts/probes/probe_part_020_closure.py` (new)
- `KNOWN_ISSUES.md`
- `.beacon/parts/part-020/DESIGN.md`
- `.beacon/parts/part-020/TODO.md`

## Forbidden Scope

- Do not implement part-021 daemon/watchdog or scheduler cutover.
- Do not alter vault, transcript, vector index, or production DB.
- Do not mark an issue fixed/mitigated without its originating slice regression and operational evidence.
- Do not modify `.beacon/CURRENT.md` outside this active slice status and verification evidence.

## Verification Plan

- Unit: `python -m pytest tests/ -q`.
- Closure QA: `python scripts/probes/probe_part_020_closure.py --design .beacon/parts/part-020/DESIGN.md --todo .beacon/parts/part-020/TODO.md --issues KNOWN_ISSUES.md --evidence-root .beacon/done`.
- The probe must assert archived verification reports for slices 001–004, required issue dispositions, part-021 dependency, and no unverified fixed status.

## Done Gate

- Closure probe exits 0 and emits deterministic evidence.
- Full regression passes.
- B7 remains mitigated unless internal `db=None` removal is evidenced; B10/W1/W2/M2 retain only evidence-backed statuses.
- part-020 is ready to archive and part-021 remains planned/non-executable.
