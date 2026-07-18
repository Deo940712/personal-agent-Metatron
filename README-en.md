# MY AGENT — Personal Schedule + Knowledge-Base Assistant

> [繁體中文](README.md) | English

A **stateless** personal AI assistant: manages schedules and todos, curates saved
social-media posts (Threads / X / FB) into an Obsidian knowledge base, and tracks
vibe-coding project progress. Schedule things and receive reminder pushes via
Discord when out; use CLI and Obsidian at home.

**Core philosophy: the core does not accumulate conversational state.** A Discord or
OpenCode UI may keep a long session, but every message creates an independent run:
read authority → act → write through validation → exit. Continuity comes from
structured DB1/Beacon/vault/transcript state and on-demand retrieval, not automatic
replay of an entire chat.

## Architecture Overview

```
User (CLI / Discord / Dashboard / MCP)
        │
        ▼
┌─────────────────────────────────────┐
│ Orchestrator (stateless, per-call)  │
│ read state → dispatch → synthesize  │
│ → write back → die                  │
└──────┬─────────────────────┬────────┘
       │ scoped tasks         │ structured proposals
       ▼                      ▼
   subagents ──proposals──▶ writer.py (sole write gate: validate then land)
       │                      │
       ▼                      ▼
┌──────────────┐   ┌───────────────────────┐
│ DB1 state.db  │   │ DB2 Obsidian vault     │
│ SQLite        │   │ Markdown knowledge     │
│ System of     │   │ semantic/ episodic/    │
│ Record (7 tbl)│   │ agent/ (agent's own)   │
└──────┬────────┘   └──────────▲────────────┘
       │  nightly distillation  │
       │  (health metabolism)   │
       └──────────┬─────────────┘
                  ▼
   Cold-storage transcript (raw text, never deleted, rehydratable)
   Vector index index.db (derived, fully rebuildable)
```

Four storage layers, each with one job:

| Store | Role |
|---|---|
| **DB1** `state.db` (SQLite) | System of Record: schedule, tasks, projects, events, cursors, pending confirmations |
| **DB2** Obsidian vault (Markdown) | Human knowledge interface: the notes you read and edit |
| **Cold storage** transcript (JSONL + index) | Raw record layer: pre-distillation text, append-only, never deleted |
| **Vector index** index.db (sqlite-vec + FTS5) | Derived artifact: delete and rebuild anytime, holds no unique data |

## Memory System (the centerpiece)

Memory is split into four layers by nature and managed by a **health-metabolism**
lifecycle (borrowing from memory-river / MemGPT / Mem0 / Hermes; full rationale in
[ARCHITECTURE.md](ARCHITECTURE.md) §12):

| Layer | Question it answers | Where |
|---|---|---|
| Working State | "Where was I?" | DB1 (tasks / cursors / projects) |
| Episodic | "What happened?" | DB1 events → distilled into vault `episodic/` |
| Semantic | "What do I know?" | vault `semantic/` (post knowledge) + `agent/` (agent's own preferences / lessons / SOPs) |
| Procedural | "How do I do it?" | `agents/*.md` contracts + `skills/` code |

**Health metabolism**: a retrieval hit heals a memory; disuse decays it; at zero it
enters trash (14-day retention, revivable if referenced) → then gets LLM-distilled
into vault notes. **Forgetting = no longer auto-loaded, never deletion** — raw text
lives forever in cold storage, and every distilled note carries `source_ids` so the
agent can "rehydrate" the exact original text anytime.

**Four-stage cascade retrieval**:
```
① index-first  (INDEX one-liners, zero cost)
② FTS5         (CJK trigram full-text, zero embedding cost)
③ vector KNN   (sqlite-vec, semantic paraphrase)
④ rehydrate    (read raw text via source_ids, for exact numbers/names)
```

Implementation spec (full APIs, invariants, failure recovery):
[docs/MEMORY-en.md](docs/MEMORY-en.md)

### Multi-layer memory: still under evaluation

Storage tiers, retrieval stages, cross-run task checkpoints, and LLM-managed
STM→MTM→LPM paging are different mechanisms. Only **A: stateless reconstruction plus
on-demand retrieval** is implemented. **B: Task Capsule**, **C: task-scoped warm set**,
and **D: LLM-managed paging** remain candidates, evaluated A→B→C→D on real long-running
work; if an earlier option is sufficient, complexity stops there.

**Memory upgrades (part-004.5, done, backed by 2026 papers)**: topic-continuity
distillation (Membox: same-topic events woven into cross-day traces instead of
per-day fragments), contradiction detection + supersede execution (Mneme: keep
both sides, co-surface at retrieval, check superseded_by before citing), and RRF
cross-stage fusion retrieval (Cognis). Deferred (trigger-based): cross-encoder
reranking (when golden queries show ranking issues) and per-category decay rates
(after 1-2 months of real usage data).

## All Agents and Their Duties

**Topology: Orchestrator + stateless subagents** (the production standard that
LangGraph / Claude Agent SDK / OpenAI Agents SDK converged on in 2026). Subagents
receive scoped input, return a structured proposal, and vanish.

### The write law: scoped agent tools, code validation, one commit boundary

Subagents may directly call allowlisted read/propose/low-risk auto-apply capabilities;
Metatron does not need to proxy every tool call. The LLM never receives raw SQL, a DB
connection, arbitrary file writing, or bare `writer.apply`. Agent- and user-initiated
proposal mutations cross `writer.apply` validation; trusted internal job pipelines (such
as nightly distillation) use their own deterministic validated write paths; neither
bypasses validation. Risky operations use preview→confirm, and timeout denies. Metatron
is the control plane, not a synchronous data-plane proxy.

### Subagent roster

**Codename: Metatron** (Heavenly Scribe) — the orchestrator itself. Subagents
carry angelic display names; code identifiers stay technical for API stability.
Full registry in [AGENTS.md](AGENTS.md) §Angel naming registry.

| Angel / Subagent | Duty | Input | Output | Status |
|---|---|---|---|---|
| **Sandalphon** — `schedule` | Natural language → schedule/todo proposals ("meeting tomorrow 2pm, remind me 30 min before"); rrule recurrence | User utterance + active items | `schedule_change` / `task_change` proposal | ✅ |
| **Raziel** — `consolidator` | Nightly distillation: expired events → daily-log summaries (episodic) / user preferences (agent/profile); every decision passes field-level validation, sources must not be fabricated | Batch of due events | Distill groups (kind/title/summary/tags/source_ids/confidence) | ✅ |
| **Jophiel** — `curator` | Post scoring (0-10 gate), classification, cross-source dedup, vault intake, linking; Chinese FIRE card-splitting | Inbox note batch | `classify_note` proposal | ✅ |
| **Zerachiel** — `recall` | Knowledge-base Q&A: RRF cascade (index → FTS → vector) + rehydrate; non-empty citations are each verified against the registry (bogus citation drops the whole answer); superseded_by hints. The strict found/not_found contract (a claim must carry a citation) is part-006-slice-001 [PLANNED] | Query string | Cited answer | ✅ |
| **Uriel** — `coding_tracker` | Vibe-coding progress from three read-only signals (git log + `.beacon/CURRENT.md` + OpenCode sessions, beacon = highest authority) → per-project phase/blockers/next | Registered project list | `project_update` proposal | ✅ |
| **Anael** — `librarian` | Vault caretaker: orphans / broken links / duplicates / tag sprawl / INDEX drift; two-phase (deterministic scan + opt-in LLM consolidation), snapshot-rollback, never deletes | Deterministic vault.scan report | `vault_maintenance` proposal (dry-run first) | 📋 backlog-017 |
| sync-{threads,x,fb} | Platform capture pipelines (**non-LLM**, pure CLI: Capture→State→Transform→Output, idempotent, resumable) | cursor | new_count, status | threads ✅ / x,fb 📋 |

Two subagent types: **pure-function** (single LLM call, no tools, replayable —
Sandalphon/Raziel/Jophiel/Anael/Uriel) and **agentic** (currently Zerachiel uses an
iterative read-only tool loop). More agents receive tools only when each next step
genuinely depends on the previous result, with scope/budget/timeout controls. Shared
state still has one deterministic writer commit boundary.

> Michael / Camael / Raphael / Ophanim / Cassiel / Azrael are angel names the
> user proposed but currently have **no matching agent** — archived in
> [AGENTS.md](AGENTS.md) §Angel naming registry (Archived). Names are not
> pre-allocated; a real agent contract must ship in the same commit that
> promotes an archived name.

## Interfaces

| Interface | Scenario | R/W | Status |
|---|---|---|---|
| **CLI** | Development, scheduled jobs | R+W | ✅ |
| **Obsidian** | Knowledge reading/editing (the vault is the UI) | R+W | ✅ (free) |
| **Discord bot** | On the go: scheduling (preview → ✅ button → land) + reminder DM push; private server, user-id whitelist | R+W (via writer + confirm) | ✅ code-complete |
| Web dashboard | At-home overview + system health (127.0.0.1, read-only) | RO | 📋 part-003.5 |
| MCP server | Query the assistant from inside OpenCode/Claude Code | RO-first | 📋 part-006 |

Interfaces are thin adapters with zero business logic. The today/week/project/
todo/done/recall paths now share the typed `core/tools/` capability layer. See
[docs/TOOLS.md](docs/TOOLS.md) for the authoritative feature/agent/interface/
permission/storage matrix and [INTERFACES.md](INTERFACES.md) for interface design.

## Usage

```bash
# Initialize (idempotent)
python -m core.stm init

# Schedule / tasks / projects CRUD
python -m core.stm schedule add "Meeting" --start 2026-07-15T14:00 --remind 2026-07-15T13:30
python -m core.stm schedule list
python -m core.stm tasks add "Buy cat litter" --due 2026-07-16T20:00
python -m core.stm projects set my-agent --phase "part-004" --next "curator"

# Natural language (requires LLM key)
python -m core.agent "meeting with A-Ming tomorrow 2pm, remind 30 min before"

# Scheduled jobs (Windows Task Scheduler / cron)
python -m core.agent --job remind        # due reminders (+ sweeps expired confirmations)
python -m core.agent --job consolidate   # nightly distillation

# Discord bot (requires token, see below)
python -m channels.discord_bot
```

### Environment Variables

| Variable | Purpose |
|---|---|
| `MY_AGENT_LLM_API_KEY` | LLM (OpenAI-compatible: OpenAI / OpenRouter / Groq / Ollama) |
| `MY_AGENT_LLM_BASE_URL` | Optional: non-OpenAI endpoint |
| `MY_AGENT_EMBED_BASE_URL` | Optional: separate embedding endpoint |
| `MY_AGENT_DISCORD_TOKEN` | Discord bot token |
| `MY_AGENT_DISCORD_ALLOWED_USER_ID` | Discord whitelist (comma-separated; empty = deny all) |

All paths live in `config.py` (`DATA_DIR` etc.) — moving machines or migrating to a
VPS means editing one file.

## Reliability by Design

| Risk | Mechanism |
|---|---|
| Memory hallucination | Hard provenance rule: every note carries its source; recall verifies each non-empty citation against the registry (bogus citation drops the whole answer); raw text is rehydratable. Enforcing "a claim must carry a citation" is [PLANNED] |
| LLM decision pollution | Every distillation decision passes field-level validation (no fabricated source_ids); failures skipped and logged |
| Rogue subagent writes | Proposal protocol + single writer + danger gates; confirmation timeout fail-closed |
| Data loss | Raw text append-only, never deleted; failed distillations stay in trash for retry; index is rebuildable |
| Silent breakage | `agent_runs` audits every invocation; a top-level guard guarantees no run stays stuck in `running` |

## Development

```bash
python -m pytest tests/ -q     # 326 tests
```

Workflow: [Beacon](.beacon/PLAN.md) (plan → design → slice → execute → verify →
**adversarial audit** → archive). After each slice, an evidence-based audit runs
(throwaway probe scripts that actually execute suspected failure paths); every
confirmed finding is logged in [KNOWN_ISSUES.md](KNOWN_ISSUES.md) and converted
into a regression test.

| Document | Contents |
|---|---|
| [ARCHITECTURE.md](ARCHITECTURE.md) | System design authority (schemas, flow diagrams, design rationale) |
| [INTERFACES.md](INTERFACES.md) | Interface layer design (CLI/Discord/dashboard/MCP) |
| [docs/TOOLS.md](docs/TOOLS.md) | Capability, agent, interface, permission, and storage matrix |
| [docs/MEMORY-en.md](docs/MEMORY-en.md) | Memory system implementation spec (APIs, invariants, failure recovery) |
| [KNOWN_ISSUES.md](KNOWN_ISSUES.md) | Audit findings and fix records |

## Progress

- ✅ part-001 Foundation (schema + CRUD CLI)
- ✅ part-002 Orchestrator + writer + schedule agent + remind
- ✅ part-002.5 Discord bot (two-stage confirmation + DM push)
- ✅ part-003 Memory core (cold storage / metabolism / distillation / cascade retrieval)
- ✅ part-004 Sync skills (threads runner + curator + recall)
- ✅ part-004.5 Memory upgrades (topic traces / supersede / RRF fusion)
- ✅ part-005 coding_tracker (git + beacon + opencode signals, live gate passed)
- 📋 part-006 stdio MCP (remote dev-loop: dev_status/directives queue) — designed
- 📋 part-003.5 read-only dashboard — designed (after part-006 slice-1)
- 📋 Pending user env: four real-QA batches (LLM key / Discord token / threads session)

Predecessor project: [threads-sync](https://github.com/Deo940712/threads-sync)
(saved Threads posts → Obsidian; this project reuses its pipeline patterns and will
integrate it as the first sync skill).
