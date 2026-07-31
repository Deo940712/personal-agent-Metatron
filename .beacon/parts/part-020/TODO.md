# PART 020: Reliability & Operability Foundation TODO

> Status: planned
> DESIGN: `.beacon/parts/part-020/DESIGN.md`
> Parent: part-019 Evidence 批次 Topic 化

## Slices

### slice-001: Dashboard Structured Result & Body/Index Isolation (W1/W2/M2)
**Goal**: Harden the existing `http.server` dashboard against malformed inputs and isolate index DB access, without migrating to a new framework.

**Outcome**: Dashboard handles oversized payloads safely, isolates `idx_db` correctly, and returns structured outcomes.

**Candidate Scope**:
- Add `Content-Length` boundary checks (W1).
- Ensure `idx_db` is correctly passed and isolated (W2).
- Introduce structured outcome fields for responses (M2).
- Add unit tests for malicious inputs.
- Add operational probe scripts for `Content-Length` limits.

**Forbidden Scope**:
- Do not migrate to FastAPI or any other framework.
- Do not change runtime code outside the dashboard module.
- This slice cannot run until promoted into CURRENT; its promoted CURRENT artifact may update only its own execution status.

**Files-scope**:
- `channels/dashboard.py`
- `channels/dashboard_page.py` (only if UI needed)
- `tests/test_dashboard.py`
- `scripts/probes/probe_dashboard_post_bounds.py` (new)

**Verification Target**:
- **Unit**: `pytest tests/test_dashboard.py` passes.
- **Regression**: Full test suite passes (`pytest tests/ -q`).
- **Operational QA**: Run `python scripts/probes/probe_dashboard_post_bounds.py` against a local instance and verify it rejects invalid/missing/zero/negative/oversize content length with HTTP 400 Bad Request per KNOWN_ISSUES.

**Done Gate**:
- W1/W2/M2 vulnerabilities are mitigated in the existing server.
- Tests and probes confirm the mitigations work.
- Issues can move to fixed/mitigated only after evidence from this slice, otherwise stay planned/open.

---

### slice-002: DB Path Safety (B7/B10)
**Goal**: Enforce explicit DB path existence checks to prevent silent creation of empty databases in wrong directories.

**Outcome**: `connect()` requires explicit path validation, preventing B7/B10 issues.

**Candidate Scope**:
- Introduce `require_exists` parameter in DB `connect()` functions.
- Force internal modules to pass the `db` connection explicitly rather than relying on implicit paths.
- Add boundary unit tests for DB path safety.
- Add operational probe scripts for invalid DB paths.

**Forbidden Scope**:
- Do not change schema.
- This slice cannot run until promoted into CURRENT; its promoted CURRENT artifact may update only its own execution status.

**Files-scope**:
- `core/stm.py`
- `tests/test_known_issues.py`
- `tests/test_db_path_safety.py` (new, only if justified)
- `scripts/probes/probe_db_b7.py` (new)

**Verification Target**:
- **Unit**: `pytest tests/test_known_issues.py` passes.
- **Regression**: Full test suite passes (`pytest tests/ -q`).
- **Operational QA**: Run `python scripts/probes/probe_db_b7.py` and verify it fails fast with a clear error when given a non-existent path, rather than creating a new DB.

**Done Gate**:
- `connect()` safely rejects invalid paths.
- All internal modules use the updated connection pattern.
- Issues can move to fixed/mitigated only after evidence from this slice, otherwise stay planned/open.

---

### slice-003: Backup, Restore, and Doctor Drill
**Goal**: Establish and verify non-destructive operational restore procedures and RPO/RTO targets.

**Outcome**: Documented and tested backup/restore procedures.

**Candidate Scope**:
- Create or update backup/restore scripts.
- Create a "doctor" script to verify system health and DB integrity.
- Document the restore drill process.

**Forbidden Scope**:
- Do not modify runtime application code.
- This slice cannot run until promoted into CURRENT; its promoted CURRENT artifact may update only its own execution status.

**Files-scope**:
- `scripts/backup.py` (new)
- `scripts/restore.py` (new)
- `scripts/doctor.py` (new)
- `docs/OPERATIONS.md` (new)

**Verification Target**:
- **Unit**: `pytest tests/ -q` (ensure no regressions).
- **Regression**: Full test suite passes (`pytest tests/ -q`).
- **Operational QA**: Use explicit disposable paths only: `python scripts/backup.py --source-db .tmp/part-020-slice-003/source.db --output .tmp/part-020-slice-003/backup.db`; intentionally corrupt only `.tmp/part-020-slice-003/source.db`; restore with `python scripts/restore.py --backup .tmp/part-020-slice-003/backup.db --target-db .tmp/part-020-slice-003/restored.db`; then run `python scripts/doctor.py --db .tmp/part-020-slice-003/restored.db` and require a healthy result. The promoted slice must create and clean this disposable fixture without reading or overwriting production DB paths.

**Done Gate**:
- Backup and restore scripts work non-destructively.
- Doctor script correctly identifies healthy vs. unhealthy states.
- Issues can move to fixed/mitigated only after evidence from this slice, otherwise stay planned/open.

---

### slice-004: Structured Job Observability Baseline
**Goal**: Define the schema and observability contract for scheduled jobs, preparing for the future daemon.

**Outcome**: `job_runs` schema is defined, documented, and migrated in DB1. `core/stm.py` APIs are updated to support it.

**Candidate Scope**:
- Define the `job_runs` schema (identity, correlation/run id, planned/actual time, status, exit/error, duration, log pointer, last success/next expected).
- Document the observability contract.
- Implement DB1 migration for `job_runs`.
- Update `core/stm.py` APIs to interact with `job_runs`.

**Forbidden Scope**:
- Do not change the existing scheduler or hidden VBS tasks.
- This slice cannot run until promoted into CURRENT; its promoted CURRENT artifact may update only its own execution status.

**Files-scope**:
- `docs/SCHEMA.md`
- `docs/OBSERVABILITY.md` (new)
- `core/stm.py`
- `tests/test_job_runs.py` (new)
- `scripts/probes/probe_job_runs_schema.py` (new)

**Verification Target**:
- **Unit**: `pytest tests/test_job_runs.py` passes.
- **Regression**: Full test suite passes (`pytest tests/ -q`).
- **Operational QA**: Run `python scripts/probes/probe_job_runs_schema.py` to verify schema is applied correctly and APIs function as expected.

**Done Gate**:
- `job_runs` schema is fully specified, documented, and migrated.
- `core/stm.py` APIs support `job_runs`.
- Issues can move to fixed/mitigated only after evidence from this slice, otherwise stay planned/open.

---

### slice-005: Documentation and Audit Closure
**Goal**: Finalize documentation and ensure all part-020 objectives are met before transitioning to part-021.

**Outcome**: part-020 is closed, and the system is ready for part-021.

**Candidate Scope**:
- Update `KNOWN_ISSUES.md`; an issue may be marked fixed/mitigated only when the originating implementation slice provides both passing regression evidence and operational-probe evidence for that issue.
- Review all part-020 slices against DESIGN.md.
- Explicitly verify part-021 dependencies are met.

**Forbidden Scope**:
- Do not mark an issue fixed/mitigated from slice-005 closure evidence alone or when its originating slice lacks either regression or operational evidence.
- This slice cannot run until promoted into CURRENT; its promoted CURRENT artifact may update only its own execution status.

**Files-scope**:
- `KNOWN_ISSUES.md`
- `.beacon/parts/part-020/DESIGN.md` (review only)
- `scripts/probes/probe_part_020_closure.py` (new)

**Verification Target**:
- **Unit**: `pytest tests/ -q` (ensure no regressions).
- **Regression**: Full test suite passes (`pytest tests/ -q`).
- **Operational QA**: Run `python scripts/probes/probe_part_020_closure.py --design .beacon/parts/part-020/DESIGN.md --todo .beacon/parts/part-020/TODO.md --issues KNOWN_ISSUES.md --evidence-root .beacon/done` and require exit code 0. The probe must deterministically select the archived part-020 slice evidence and fail when any required originating-slice regression or operational evidence is absent, malformed, or inconsistent with the issue status.

**Done Gate**:
- All documentation is up-to-date.
- **Final Acceptance Gate**: Explicit confirmation that the foundation for part-021 (Supervisor/Watchdog) is complete and verified.
- Issues can move to fixed/mitigated only when their originating implementation slice has both passing regression evidence and operational-probe evidence; otherwise they stay planned/open.
