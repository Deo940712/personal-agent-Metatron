# AGENTS.md

## What this repo is

**Codename: Metatron** — the Heavenly Scribe orchestrator. Sub-agents are named
after angels in Metatron's court (see "Angel naming registry" section below).
Angel names are display-layer only; code identifiers (module names, role_type,
--job flags) keep their technical names for API stability.

A personal schedule + knowledge-base assistant agent (parts 001-005 + 002.5 + 004.5 all done,
314 tests green; next: part-006 stdio MCP then part-003.5 dashboard). The full architecture decision record is in
[ARCHITECTURE.md](ARCHITECTURE.md) — read it before implementing anything.
Interface layer design authority: [INTERFACES.md](INTERFACES.md).
Memory system implementation spec (probe-verified platform behavior — READ before
touching transcript/health/vindex/consolidate/retrieve):
[docs/MEMORY-zh.md](docs/MEMORY-zh.md) / [docs/MEMORY-en.md](docs/MEMORY-en.md).
Predecessor project (patterns to reuse):
[threads-sync](https://github.com/Deo940712/threads-sync).

`.codegraph/` and `.omo/` are external tooling state, not project code — ignore them.
Not a git repo yet. User communicates in zh-TW (Traditional Chinese); reply in Chinese.

## Known issues (read before touching core/)

[KNOWN_ISSUES.md](KNOWN_ISSUES.md) tracks audited bugs with reproduction commands
(7 confirmed crashes as of 2026-07-13, B1–B4 HIGH). Fix status is tracked per-item.
Testing lesson recorded there: every validator MUST have boundary tests
(empty/None/out-of-range/bool-as-int) — enum-only tests missed all 7 crashes.

## Beacon workflow (mandatory)

Work is governed by `.beacon/` (beacon-dev-workflow skill). Before coding: read
`.beacon/CURRENT.md` → the active part's `DESIGN.md` → `TODO.md`. Only the slice
promoted into CURRENT is executable; BACKLOG is never execution permission.
**Continuous loop**: after archiving a slice, run the adversarial audit gate
(probe scripts, evidence-based) then auto-continue to the next slice — clean →
continue; findings → KNOWN_ISSUES.md + fixes-before-features; design flaw →
amend DESIGN/PLAN in place then continue. Pause only at PART completion, user
decisions, missing DESIGN, or Hard Stops. See skill `references/continuous-loop.md`.
Verify with `powershell -ExecutionPolicy Bypass -File .beacon/verification/UnitTestCore.ps1 -Part part-XXX -Slice slice-XXX`
(direct `&` invocation is blocked by execution policy on this machine).
Phase plan lives in `.beacon/PLAN.md` (mirrors ARCHITECTURE.md build order).

## Non-negotiable design rules

- **Stateless agent core.** No long-lived session, no accumulated context. Every
  invocation: read DB1 → act → write back → exit. Do not introduce
  conversation-history persistence in the core.
- **Storage roles (ARCHITECTURE.md §2/§5).** DB1 SQLite = System of Record (6 tables,
  DDL in §5.1 is authoritative). DB2 Obsidian vault = human knowledge interface
  (append-only, semantic/ + episodic/). Cold transcript JSONL = raw records, never
  deleted. Vector index = derived, rebuildable, never holds unique data.
- **Memory lifecycle = health metabolism, NOT hard TTL.** Hits heal, disuse decays,
  zero → trash → archive. Schedule/identity/preferences immune. Forgetting means
  "not auto-loaded", never physical deletion.
- **Subagents propose, writer.py disposes.** Subagents NEVER write DBs directly; all
  writes go through writer.py validation (target exists, tags in controlled vocab,
  evidence verbatim in source, never override manual edits). Proposal envelope: §3.1.
- **Tool registry (§3.2):** the ONLY write-capable tool is `writer.apply`; everything
  else is read-only. schedule/curator/librarian/coding_tracker are pure-function
  subagents (no tools — inputs collected deterministically first); only recall gets
  a read-only tool whitelist.
- **Danger gates (§3.2, borrowed from Hermes Agent):** hardline blocklist (physical
  deletion of vault/cold-storage/DB1, bypassing writer, overriding manual_tags —
  never executable, no override); confirm-required (schedule writes, librarian
  batch maintenance, supersedes); auto-allowed (read-only, done marks, events
  append). Confirmation timeout = deny (fail-closed).
- **Librarian maintenance (§4.3, borrowed from Hermes Curator):** two-phase
  (deterministic scan free, LLM consolidation opt-in), snapshot before apply,
  never deletes (archive to vault/.archive/), pinned/manual notes exempt,
  dry-run report first.
- **Every distilled note carries `source_ids`** pointing back to cold-storage entries
  (rehydrate path). Compression must never lose the way back to raw text.
- **`vault/agent/` is the agent's own knowledge store** (§4.2): profile/ (user
  preferences), ops/ (operational lessons), sop/ (learned procedures — explicit save
  only, never auto-generated). Same frontmatter schema, decay-immune, loaded via
  progressive disclosure (INDEX one-liners only — never inline the whole folder).
- **Skills are independent CLI pipelines** (threads-sync pattern): each idempotent,
  runnable standalone, resumable after interrupt. Core only routes and reads/writes
  DBs. Do not couple skills to each other or to the core.
- **All paths/params live in `config.py`.** Never hardcode `C:\Users\...`.
  `DATA_DIR = C:\Users\tcart\my-agent-data` (local, outside OneDrive). Timestamps:
  UTC epoch seconds (INTEGER) in DB1 + cold storage; human-readable strings only in
  vault frontmatter.
- **Reminders/schedule writes are deterministic code, not LLM.** LLM only parses
  natural language into candidates and explains conflicts; triggering, recurrence
  expansion, and DB writes are plain Python. Mutations need user preview+confirm.
- **No hierarchical memory paging** (STM→MTM→LPM à la MemoryOS) and no knowledge
  graph / hooks / GWM subsystems — rejected as overengineering; see ARCHITECTURE.md §12.

## Inherited threads-sync conventions (keep them)

- Incremental sync with SQLite dedupe + cursor resume; stop after N *consecutive*
  already-seen items, not the first hit.
- Capture GraphQL responses via Playwright interception; never scrape the DOM.
- Login = import real-Chrome cookies (`import_session.py` pattern); in-Playwright
  login is blocked by Meta anti-scripting.
- Media must be downloaded locally (CDN URLs expire); reference relative paths.
- `data/` (state.db, playwright session, cookies) is secret-bearing — never commit.
- Low frequency, jittered delays; no anti-detection evasion.

## Build order (respect the phase gates in ARCHITECTURE.md §10)

DONE: 1, 2, 2.5, 3, 4 (threads runner + curator + recall), 4.5 (topic traces /
supersede / RRF), 5 (coding_tracker, live three-source gate passed).
NEXT (user-decided order): 6-slice-1 (stdio MCP + directives 8th table — touches
shared stm.py first) → 3.5 (read-only dashboard, zero overlap, shows directives
panel too) → 6-slice-2 (Tailscale HTTP, gated on VPS).
Key facts for future sessions:
- OpenCode session store confirmed readable: `~/.local/share/opencode/opencode.db`
  (SQLite, WAL; tables session/message/part/todo) — open `mode=ro` only.
- threads-sync is VENDORED (skills/threads_sync_vendor, pinned commit, zero-edit
  black box); integration is env vars THREADS_SYNC_VAULT/DATA only.
- `directives` table (8th, part-006) = remote command queue; session-start rule
  will be: run `python -m core.stm directives pending` and obey before other work.

## Open decisions — ask the user before committing to one

Full list in ARCHITECTURE.md §11. Highlights:

- Vector index: sqlite-vec (leaning) vs LanceDB vs Chroma
- ~~LLM provider~~ DECIDED: OpenAI-compatible API (`openai` pkg + configurable
  base_url; cheap/strong model tiers; keys via env vars)
- ~~Subagent framework~~ DECIDED: hand-rolled thin layer (single chat.completions
  call + agents/*.md prompt contracts + JSON proposal parsing; no LangGraph/SDK)
- Scheduler: Windows Task Scheduler (leaning) vs resident daemon; cron after VPS move
- ~~Reminder channel~~ DECIDED: Discord DM (INTERFACES.md §4); console during dev
- Health metabolism parameters (decay rate, heal amount, trash retention) — tune in part-003
- Channels are thin adapters with ZERO business logic; all share
  `invoke(text, trigger, reply_to)`; writes never bypass writer+confirm regardless of source

## Angel naming registry

The orchestrator `core/agent.py` is codenamed **Metatron** (Heavenly Scribe).
Sub-agents in `agents/` carry angelic display names; internal code identifiers
(`role_type='schedule'`, `--job remind`, module `core/consolidate.py`, etc.) are
UNCHANGED — refactoring stable APIs for cosmetics is not worth the churn.

### Active (mapped to existing agents)

| Angel | Role | Code identifier | Reason |
|---|---|---|---|
| **Metatron** | Orchestrator (this repo's identity) | `core/agent.py` | Heavenly Scribe, statutes all angels — matches Orchestrator |
| **Sandalphon** | Schedule / intent parsing | `agents/schedule.md`, `role_type='schedule'` | Metatron's twin, weaves human prayers — only human-facing agent |
| **Jophiel** | Curator (vault ingestion beautifier) | `agents/curator.md`, `role_type='classify_note'` | Angel of Beauty — aesthetic gate before knowledge lands |
| **Raziel** | Consolidator (nightly distillation, MEM write side) | `agents/consolidator.md`, `--job consolidate` | "Book of Raziel" — writes cosmic knowledge into vault |
| **Zerachiel** | Recall (RAG retrieval, MEM read side) | `agents/recall.md`, `role_type='agentic'` | Angel of memory / testimony — reads back what Raziel wrote |
| **Uriel** | Coding tracker (project foresight) | `agents/coding_tracker.md`, `--job track` | "Light of God" — sees the whole picture, foretold the flood |

### Reserved (mapped to backlog agents, docs-only until built)

| Angel | Future role | Backlog id | Notes |
|---|---|---|---|
| **Anael** | Vault maintenance (orphans / broken links / dedupe) | backlog-017 (`librarian`) | Angel of Order — keeps the library in harmony |

### Archived (angel names user proposed but no matching agent exists yet)

Kept for future use; do NOT create agents for these without a real design need.

| Angel | Proposed role | Why archived |
|---|---|---|
| **Michael** | Guardrail / danger gate | Currently lives inside `writer.py` — no independent agent |
| **Camael** | Red-team / adversarial tester | Adversarial audit currently runs as beacon slice gate, not a persistent agent |
| **Raphael** | Debug / retry | Retry is currently a code-level top-level guard, not an agent |
| **Ophanim** | Monitoring / log analysis | `agent_runs` table + planned dashboard cover this without an agent |
| **Cassiel** | Cron / scheduling | Scheduling is a Windows Task Scheduler job (`--job remind`), not a subagent |
| **Azrael** | Cleanup / GC / process termination | Metabolism/GC is a code-level cron in `core/metabolize.py`, not an agent |

When any archived name gets promoted to active, move the row to the "Active"
table above and add a real `agents/<name>.md` contract in the same commit.
