# part-021 TODO: Resident Daemon Control Center

> Status: planned (non-executable)
> DESIGN: `.beacon/parts/part-021/DESIGN.md`
> Parent: part-020 Reliability & Operability Foundation
> Promotion rule: part-019 remains the only executable CURRENT. Each slice below becomes executable only after part-020 is complete and that one slice is promoted into `.beacon/CURRENT.md` with its files-scope and verification commands copied exactly.

## slice-001: Supervisor Scheduler Core

**Status**: planned; promotion prerequisite is completed/archived part-020, available DB1 `job_runs` APIs and schema, and explicit promotion of slice-001 into `.beacon/CURRENT.md`.

**Goal**: Implement the resident schedule loop using DB1 `job_runs` as the authoritative lock/status store while spawning only the six existing CLI jobs.

**Files-scope**:
- `core/daemon.py` (new)
- `tests/test_daemon.py` (new)
- `core/stm.py`
- `tests/test_job_runs.py`

**Implementation contract**:
- Define the six-job allowlist and exact `python -m core.agent --job <name>` argv construction.
- Acquire/release run state atomically through part-020 `job_runs` APIs; do not create a daemon-local lock authority.
- Implement deterministic startup handling: lateness within configured grace runs once; lateness beyond grace records `missed` and waits for the next interval.
- Preserve each spawned job's existing deterministic validated write path; user/agent proposal mutations remain writer+confirm and the daemon adds no bypass.

**Verification commands and artifacts**:
- `python -m pytest tests/test_daemon.py tests/test_job_runs.py -q`
- `python -m pytest tests/ -q`
- `python -m core.daemon --once --dry-run --now 1893456000 --state-out "$env:TEMP\metatron-daemon-slice-001.json"`
- Artifact `%TEMP%\metatron-daemon-slice-001.json` must deterministically contain the fixed evaluation time, six allowlisted job names, each planned/next time, startup decision, and zero spawned subprocesses.

**Done gate**:
- Tests cover allowlist rejection, exact argv, atomic overlap, both grace boundaries, one-time catch-up, missed recording, tick idempotency, and subprocess result persistence.
- Dry-run artifact is stable across two identical invocations after removing only its generated timestamp field, if any.

---

## slice-002: Watchdog and Hidden Bootstrap

**Status**: planned; promotion prerequisite is archived slice-001 evidence and explicit promotion of slice-002 into `.beacon/CURRENT.md`.

**Goal**: Register one liveness-only Task Scheduler watchdog that checks every 60 seconds and launches the daemon hidden with exponential backoff.

**Files-scope**:
- `tools/register_watchdog.ps1` (new)
- `tools/run_daemon_hidden.vbs` (new)
- `tests/test_watchdog_contract.py` (new)

**Implementation contract**:
- Watchdog may check daemon liveness and launch the hidden runner only; it cannot invoke domain jobs.
- Persist exponential-backoff state outside the repository under a documented `DATA_DIR` path and reset it after a successful liveness check.
- Registration must be idempotent and expose a non-mutating inspection mode.

**Verification commands and artifacts**:
- `python -m pytest tests/test_watchdog_contract.py -q`
- `powershell -ExecutionPolicy Bypass -File tools\register_watchdog.ps1 -WhatIf -ContractOut "$env:TEMP\metatron-watchdog-contract.json"`
- `python -c "import json,os,pathlib; p=pathlib.Path(os.environ['TEMP'])/'metatron-watchdog-contract.json'; d=json.loads(p.read_text(encoding='utf-8')); assert d['interval_seconds']==60; assert d['domain_jobs']==[]; assert d['backoff']['strategy']=='exponential'; assert not pathlib.Path(d['backoff']['state_path']).is_relative_to(pathlib.Path.cwd())"`
- Artifact `%TEMP%\metatron-watchdog-contract.json` records task name, exact 60-second interval, hidden runner path, liveness command, empty domain-job list, and external backoff-state path without changing Task Scheduler.

**Done gate**:
- Contract tests and `-WhatIf` artifact prove liveness-only behavior, exact cadence, idempotent registration intent, hidden launch, and external exponential-backoff state.

---

## slice-003: Read-only Job Status UI

**Status**: planned; promotion prerequisite is archived slice-002 evidence, populated part-020 `job_runs` test fixtures, and explicit promotion of slice-003 into `.beacon/CURRENT.md`.

**Goal**: Show daemon-managed job state from DB1 without adding controls.

**Files-scope**:
- `channels/dashboard.py`
- `channels/dashboard_page.py`
- `tests/test_dashboard.py`

**Implementation contract**:
- Add a read-only route backed by DB1 `job_runs` for job identity, planned/actual time, status, last success, next expected run, duration, and bounded log detail.
- Render loading, empty, running, success, failed, and missed states.
- Do not infer authority from daemon memory or raw log scraping.

**Verification commands and artifacts**:
- `python -m pytest tests/test_dashboard.py -q`
- `python -c "import json,tempfile; from pathlib import Path; from core import stm; from channels import dashboard; root=Path(tempfile.mkdtemp()); db=root/'state.db'; stm.init(db); status,ctype,body=dashboard.route('GET','/api/jobs',{},db=db,vault=root/'vault'); assert status==200 and ctype=='application/json'; data=json.loads(body); (root/'dashboard-jobs.json').write_text(json.dumps(data,sort_keys=True),encoding='utf-8'); print(root/'dashboard-jobs.json')"`
- The printed `dashboard-jobs.json` is the deterministic API artifact; test fixtures must separately assert every required status and field.

**Done gate**:
- Dashboard tests prove the API reads `job_runs`, all defined states render, missing rows produce a deterministic empty state, and no control route is introduced.

---

## slice-004: Confirm-protected Allowlisted Controls

**Status**: planned; promotion prerequisite is archived slice-003 evidence, resolved loopback endpoint configuration, and explicit promotion of slice-004 into `.beacon/CURRENT.md`.

**Goal**: Add secure trigger/pause/resume controls without opening arbitrary execution or bypassing existing mutation gates.

**Files-scope**:
- `channels/dashboard.py`
- `channels/dashboard_page.py`
- `core/daemon.py` (new)
- `tests/test_dashboard.py`
- `tests/test_daemon.py`

**Implementation contract**:
- Generate/use a random per-install token stored outside the repo under `DATA_DIR`; never embed it in tracked source or page HTML.
- Require token plus exact Origin and Host validation for every state-changing request.
- Allow only trigger of one named allowlisted job, pause scheduling, and resume scheduling. Trigger uses the DB1 lock; pause does not terminate a running subprocess.
- Existing proposal mutations continue through writer+confirm; daemon controls add no raw SQL or writer bypass.

**Verification commands and artifacts**:
- `python -m pytest tests/test_dashboard.py tests/test_daemon.py -q`
- `python -m pytest tests/ -q`
- `python -c "import json,tempfile; from pathlib import Path; from core.daemon import write_security_contract; p=Path(tempfile.mkdtemp())/'daemon-security.json'; write_security_contract(p,origin='http://127.0.0.1:7777',host='127.0.0.1'); d=json.loads(p.read_text(encoding='utf-8')); assert d['token_storage']=='DATA_DIR'; assert d['origin_validation']=='exact'; assert d['host_validation']=='exact'; assert set(d['operations'])=={'trigger','pause','resume'}; print(p)"`
- The printed `daemon-security.json` is a redacted deterministic contract artifact and must contain no token value.

**Done gate**:
- Tests reject missing/incorrect token, Origin, Host, arbitrary job names, and unconfirmed UI actions; tests accept each allowlisted control and prove trigger overlap protection.

---

## slice-005: Migration, Cutover, and rollback

**Status**: planned; promotion prerequisite is archived slice-004 evidence, an approved maintenance window, elevated Task Scheduler access, and explicit promotion of slice-005 into `.beacon/CURRENT.md`.

**Goal**: Replace seven legacy scheduler definitions without any interval in which legacy domain schedules and daemon scheduling are both active, and prove complete rollback.

**Files-scope**:
- `tools/cutover_daemon.ps1` (new)
- `tools/rollback_daemon.ps1` (new)
- `tools/task-backups/` (runtime data outside repo or documented `DATA_DIR` path only; do not create or track this directory in the repository)

**Implementation contract**:
- Export all six domain task XML definitions and the dashboard ONSTART XML definition before changing scheduler state.
- Disable all seven legacy definitions before starting the daemon; then register/enable the watchdog and prove it is the only enabled Metatron scheduler definition.
- Fail closed on inventory, export, disable, health, or postcondition mismatch.
- rollback stops the daemon, disables/removes the watchdog, restores all seven XML definitions, and verifies their normalized names, triggers, actions, and enabled states against the backup manifest.

**Verification commands and artifacts**:
- `powershell -ExecutionPolicy Bypass -File tools\cutover_daemon.ps1 -WhatIf -BackupRoot "$env:TEMP\metatron-task-backups" -ReportPath "$env:TEMP\metatron-cutover-report.json"`
- `python -c "import json,os,pathlib; d=json.loads((pathlib.Path(os.environ['TEMP'])/'metatron-cutover-report.json').read_text(encoding='utf-8')); assert d['legacy_count']==7; assert len(d['exports'])==7; assert d['disable_before_daemon_start'] is True; assert d['remaining_enabled_tasks']==['MyAgent-watchdog']"`
- `powershell -ExecutionPolicy Bypass -File tools\rollback_daemon.ps1 -WhatIf -BackupRoot "$env:TEMP\metatron-task-backups" -ReportPath "$env:TEMP\metatron-rollback-report.json"`
- `python -c "import json,os,pathlib; d=json.loads((pathlib.Path(os.environ['TEMP'])/'metatron-rollback-report.json').read_text(encoding='utf-8')); assert d['restored_count']==7; assert d['watchdog_enabled'] is False; assert d['normalized_xml_match'] is True"`
- Deterministic artifacts are the seven XML exports, backup manifest, `metatron-cutover-report.json`, and `metatron-rollback-report.json`; real cutover repeats the same commands without `-WhatIf` only inside the promoted slice's approved maintenance window.

**Done gate**:
- Dry-run contract proves export/disable/start ordering and seven-item recovery before real scheduler mutation.
- Real operational QA records pre/post `schtasks /Query /FO LIST /V` inventories, daemon health, watchdog-only topology, and a successful seven-definition restore drill.

---

## slice-006: Operations Documentation and Audit Closure

**Status**: planned; promotion prerequisite is archived slice-005 cutover and restore evidence and explicit promotion of slice-006 into `.beacon/CURRENT.md`.

**Goal**: Publish exact operating procedures and close part-021 with a machine-executable contract probe.

**Files-scope**:
- `docs/OPERATIONS.md` (new)
- `docs/DAEMON.md` (new)
- `scripts/probes/probe_part_021_closure.py` (new)
- `.beacon/parts/part-021/DESIGN.md`
- `.beacon/parts/part-021/TODO.md`
- `KNOWN_ISSUES.md` (only for evidence-backed findings discovered during audit)

**Implementation contract**:
- Document installation, token location/rotation, daemon start/stop/status, pause/resume semantics, missed-run grace, log/status lookup, cutover, rollback, seven-XML restore, and watchdog backoff recovery.
- Probe actual configured paths and DB1 `job_runs`; do not accept prose-only completion.
- Record only reproduced audit findings and convert confirmed runtime defects to regression tests before closure.

**Verification commands and artifacts**:
- `python scripts/probes/probe_part_021_closure.py --report "$env:TEMP\metatron-part-021-closure.json"`
- `python -m pytest tests/test_daemon.py tests/test_job_runs.py tests/test_watchdog_contract.py tests/test_dashboard.py -q`
- `python -m pytest tests/ -q`
- `python -c "import json,os,pathlib; d=json.loads((pathlib.Path(os.environ['TEMP'])/'metatron-part-021-closure.json').read_text(encoding='utf-8')); assert d['job_runs_authoritative'] is True; assert d['watchdog_interval_seconds']==60; assert d['enabled_scheduler_tasks']==['MyAgent-watchdog']; assert d['legacy_xml_backup_count']==7; assert d['rollback_probe']=='passed'; assert d['security']['token_outside_repo'] and d['security']['origin_host_validated']"`
- Artifact `%TEMP%\metatron-part-021-closure.json` includes command versions, DB schema/API checks, scheduler inventory, seven-backup hash manifest, security checks, missed-run boundary results, cutover ordering, rollback result, and full test summary.

**Done gate**:
- Closure probe and focused/full tests pass with deterministic artifacts.
- DESIGN/TODO match implemented behavior, audit findings are dispositioned, and the part may be archived through the normal Beacon workflow.
