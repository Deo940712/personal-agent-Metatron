# MY AGENT — Personal Schedule + Knowledge-Base Assistant

> [繁體中文](README.md) | English

A **stateless** personal AI assistant: manages schedules and todos, curates saved
social-media posts (Threads / X / FB) into an Obsidian knowledge base, and tracks
vibe-coding project progress. Schedule things and receive reminder pushes via
Discord when out; use CLI and Obsidian at home.

**Core philosophy: discard the context window.** No long chat sessions — every
invocation reads the database, acts, writes back, and dies. Continuity comes from
structured memory, not conversation history.

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

**Planned memory upgrades (part-004.5, backed by 2026 papers)**: topic-continuity
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

### The write law: agents propose, code validates, a single writer lands

Subagents **never write to databases directly**. All writes go through `writer.py`:
seven validation rules (target exists, tags in controlled vocabulary, evidence
verbatim, legal enums…) plus three-tier danger gates (physical deletion is
impossible / writes require user confirmation / read-only auto-allowed).
Confirmation timeout = deny (fail-closed).

### Subagent roster

| Subagent | Duty | Input | Output | Status |
|---|---|---|---|---|
| **schedule** | Natural language → schedule/todo proposals ("meeting tomorrow 2pm, remind me 30 min before"); rrule recurrence | User utterance + active items | `schedule_change` / `task_change` proposal | ✅ |
| **consolidator** | Nightly distillation: expired events → daily-log summaries (episodic) / user preferences (agent/profile); every decision passes field-level validation, sources must not be fabricated | Batch of due events | Distill groups (kind/title/summary/tags/source_ids/confidence) | ✅ |
| **curator** | Post scoring (0-10 gate), classification, cross-source dedup, vault intake, linking; Chinese FIRE card-splitting | Inbox note batch | `classify_note` proposal | 📋 part-004 |
| **librarian** | Vault caretaker: orphans / broken links / duplicates / tag sprawl / INDEX drift; two-phase (deterministic scan + opt-in LLM consolidation), snapshot-rollback, never deletes | Deterministic vault.scan report | `vault_maintenance` proposal (dry-run first) | 📋 part-004+ |
| **coding_tracker** | Vibe-coding progress from three read-only signals (git log + `.beacon/CURRENT.md` parsing + OpenCode sessions) → per-project phase/blockers/next | Project path list | `project_update` proposal | 📋 part-005 |
| **recall** | Knowledge-base Q&A: four-stage cascade retrieval; answers must cite sources, no source = no claim | Query string | Cited answer | 📋 part-004 |
| sync-{threads,x,fb} | Platform capture pipelines (**non-LLM**, pure CLI: Capture→State→Transform→Output, idempotent, resumable) | cursor | new_count, status | 📋 part-004 |

Two subagent types: **pure-function** (single LLM call, no tools, replayable —
schedule/consolidator/curator/librarian/coding_tracker) and **agentic** (read-only
tool whitelist, iterative retrieval — recall only). The only write-capable tool in
the whole system is `writer.apply`.

## Interfaces

| Interface | Scenario | R/W | Status |
|---|---|---|---|
| **CLI** | Development, scheduled jobs | R+W | ✅ |
| **Obsidian** | Knowledge reading/editing (the vault is the UI) | R+W | ✅ (free) |
| **Discord bot** | On the go: scheduling (preview → ✅ button → land) + reminder DM push; private server, user-id whitelist | R+W (via writer + confirm) | ✅ code-complete |
| Web dashboard | At-home overview + system health (127.0.0.1, read-only) | RO | 📋 part-003.5 |
| MCP server | Query the assistant from inside OpenCode/Claude Code | RO-first | 📋 part-006 |

Interfaces are thin adapters with zero business logic, sharing
`invoke(text, trigger, reply_to)`. Design: [INTERFACES.md](INTERFACES.md).

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
| Memory hallucination | Hard provenance rule: every note carries its source; recall makes no claim without one; raw text is rehydratable |
| LLM decision pollution | Every distillation decision passes field-level validation (no fabricated source_ids); failures skipped and logged |
| Rogue subagent writes | Proposal protocol + single writer + danger gates; confirmation timeout fail-closed |
| Data loss | Raw text append-only, never deleted; failed distillations stay in trash for retry; index is rebuildable |
| Silent breakage | `agent_runs` audits every invocation; a top-level guard guarantees no run stays stuck in `running` |

## Development

```bash
python -m pytest tests/ -q     # 210 tests
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
| [docs/MEMORY-en.md](docs/MEMORY-en.md) | Memory system implementation spec (APIs, invariants, failure recovery) |
| [KNOWN_ISSUES.md](KNOWN_ISSUES.md) | Audit findings and fix records |

## Progress

- ✅ part-001 Foundation (schema + CRUD CLI)
- ✅ part-002 Orchestrator + writer + schedule agent + remind
- ✅ part-002.5 Discord bot (two-stage confirmation + DM push)
- ✅ part-003 Memory core (cold storage / metabolism / distillation / cascade retrieval)
- 📋 part-004 Sync skills (threads/x/fb → vault) + curator + recall
- 📋 part-004.5 Memory upgrades (topic traces / supersede / RRF)
- 📋 part-005 coding_tracker (git + beacon + opencode signals)
- 📋 part-003.5 dashboard / part-006 MCP server

Predecessor project: [threads-sync](https://github.com/Deo940712/threads-sync)
(saved Threads posts → Obsidian; this project reuses its pipeline patterns and will
integrate it as the first sync skill).
