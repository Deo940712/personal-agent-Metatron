# Metatron Memory Architecture Contract

> 繁體中文: [MEMORY-zh.md](MEMORY-zh.md)  
> System-level authority: [ARCHITECTURE.md](../ARCHITECTURE.md); capability policy:
> [TOOLS.md](TOOLS.md). This document records both implemented contracts and candidates
> that still require empirical evaluation.

## 1. Contract and Decision Status

### 1.1 Status labels

| Label | Meaning |
|---|---|
| `[IMPLEMENTED]` | The code, store, or flow exists now and has test or probe evidence |
| `[CANDIDATE]` | An option that may be evaluated; it is not authorized or selected |
| `[PLANNED]` | A concrete PART/slice exists, but the behavior is not complete |
| `[NON-GOAL]` | Explicitly excluded; this is not a synonym for “undecided” |

### 1.2 Current conclusion

- `[IMPLEMENTED]` Four physical storage roles, health lifecycle, distillation,
  four-stage retrieval, and rehydration.
- `[IMPLEMENTED]` Every core invocation is independent. Continuity comes from
  authoritative stores, not an accumulated replay of an entire chat.
- `[CANDIDATE]` Task Capsule, task-scoped warm set, and LLM-managed paging. The
  A/B/C/D comparison is defined, but **multi-layer context is undecided**.
- `[NON-GOAL]` A resident conversation brain, automatic whole-chat replay without
  validation, physical deletion of raw evidence, or raw SQL/DB/file write primitives
  held by an LLM.

**MEM-01 — Stateless core.** A UI may keep a long connection or conversation, but
each message creates an independent core run. The UI session is not authoritative
memory, and “the latest session” cannot identify the active task.

**MEM-07 — Honest decision state.** A is implemented; B, C, and D are
`[CANDIDATE]`. Documentation, code, and interfaces must neither present candidates as
adopted nor turn an undecided option into a permanent rejection.

## 2. Identity, Lifetime, and Authority

### 2.1 Identities are not interchangeable

| Identity | Lifetime | Current realization |
|---|---|---|
| UI/session id | One channel or developer-tool interaction | May exist externally; not a core SoR |
| `run_id` | One invocation or job execution | `[IMPLEMENTED]` as `agent_runs.id` |
| `task_id` | User work spanning multiple runs | `[IMPLEMENTED]` personal todos use `tasks.id`; development uses a Beacon slice id; no generic capsule id exists |
| `job_id` | A resumable background work instance | `[PLANNED]` no generic persisted schema; current correlation uses run trigger/cursor |
| `pending_id` | One mutation awaiting confirmation | `[IMPLEMENTED]` as `pending_proposals.id` |
| `source_id` | Location of raw evidence | `[IMPLEMENTED]` transcript namespace such as `evt:123` |
| `evidence_id` | Standalone evidence object | `[PLANNED]` no separate schema; current code uses `source_ids` and evidence strings |

One UI session can contain many runs; one task/job can span runs and interfaces; one
pending item can be created through one interface and confirmed through another.
These identities are orthogonal, not one nested session tree.

### 2.2 Authority is domain-specific

| Domain | Authority | Non-authoritative / derived |
|---|---|---|
| Schedules, todos, projects, events, pending items, run audit | DB1 SQLite | UI cache, LLM summaries |
| Human-maintained knowledge and agent profile/SOP | Obsidian vault + manual edits | vector/FTS index |
| Raw evidence | transcript JSONL | distilled summaries, embeddings |
| Development workflow and code state | Beacon artifacts + git | OpenCode session summaries |
| Retrieval acceleration | No independent authority; rebuilt from vault | `index.db` itself |

**MEM-02 — Domain-specific authority.** DB1 is not the single global SoR for every
domain. Each datum is resolved by the authority table above. OpenCode sessions are
observational signals only.

**MEM-06 — Summaries are not persistence.** UI/model compaction, handoff text, and
chat summaries remain observational context until explicitly promoted through an
authoritative checkpoint or proposal path.

## 3. Implemented Storage and Lifecycle

### 3.1 Four physical storage roles

| Store | Role | Rebuildability |
|---|---|---|
| DB1 `state.db` | Mutable structured state and audit | Cannot be replaced by an index; back up by domain |
| DB2 vault | Human-readable, manually correctable knowledge | Manual content may be unique; not assumed rebuildable |
| transcript JSONL + `.idx` | Raw append-only evidence | JSONL is truth; `.idx` is rebuildable |
| `index.db` | Derived FTS5 + sqlite-vec index | Fully rebuilt from the vault |

**MEM-03 — Raw evidence is append-only.** The transcript has no delete API. JSONL is
flushed before `.idx`; a crash can at worst leave a short index, recoverable through
`rebuild_idx()`.

**MEM-04 — The index is not authoritative.** `index.db` must hold no unique data. A
model/dimension change or corruption requires a complete rebuild.

### 3.2 Health metabolism

```text
alive ⇄ trash → archived
```

- A new event starts at `health=1.0`.
- `[IMPLEMENTED]` `HEALTH_DECAY_PER_DAY=0.05`: roughly 20 untouched days to zero.
- `[IMPLEMENTED]` `TRASH_RETENTION_DAYS=14`: a hit during trash revives the event.
- Schedule, identity, preference, and manually pinned categories are immune.
- Archived means no longer auto-loaded, not deleted; raw text remains in transcript.

### 3.3 Distillation flow

```text
decay → to_trash (raw text to transcript) → due_for_distill
→ group by day (≤50) → LLM distillation → field validation
→ vault note (source_ids) → mark_archived → vindex.upsert
```

Validation (`core/consolidate.py`) requires `kind ∈ {episodic, preference}`, controlled
tags, `source_event_ids` drawn only from the current batch, confidence ≥0.6, a non-empty
summary of at most 500 characters, a non-empty title, and a non-empty topic of at most
30 characters (the part-004.5 cross-day linking field); supersedes is optional but, when
present, must point to a real, not-yet-superseded profile note. A bad group is skipped
while its events remain in trash for a later retry.

**MEM-05 — Compression remains rehydratable.** Every distilled note must retain
`source_ids`. Compression cannot sever the path to raw evidence or make a failed
distillation lose data.

## 4. Implemented Retrieval and Context Assembly

### 4.1 Retrieval (strong-hit short-circuit + RRF fusion + rehydrate)

`[IMPLEMENTED]` (part-004.5, `core/retrieve.py`):

1. Strong index short-circuit: when a query has at least 2 tokens (or all tokens for a
   single-token query) matching one note's title/summary, return immediately at zero
   FTS/embedding cost.
2. Otherwise draw candidates from three stages — INDEX registry, FTS5 trigram (CJK ≥3
   chars MATCH, shorter queries LIKE), and sqlite-vec KNN (one embedding call) — then
   fuse the ranking with RRF (`RRF_K=60`).
3. Rehydrate is a later on-demand step following `source_ids` for exact names, dates,
   numbers, or dispute checks; it is not a peer ranking stage.

Any hit calls `health.on_hit`, healing frequently used source events.

### 4.2 Current context model

`[IMPLEMENTED]` Each run reloads required DB1 state, prompt contracts, and on-demand
retrieval results. Chain-of-thought and the complete working context are discarded at
the end. `vault/agent/` is progressively disclosed: registry one-liners first, full
notes only when needed.

If context pressure occurs, preserve system policy, the current user instruction,
authoritative constraints, and directly relevant evidence first. Low-scoring hits,
duplicate tool output, and reloadable full text are evicted or replaced with references
first. Exact token caps require measurement and remain configurable rather than invented.

## 5. Multi-Layer Memory Options Under Evaluation

### 5.1 Four different concepts

- Storage tier: where data lives among DB1, vault, transcript, and index.
- Retrieval stage: which search step serves one query.
- Context continuity: how task state resumes across runs.
- Agent-managed paging: whether an LLM moves data among STM/MTM/LPM itself.

The first two are implemented; that does not imply adoption of the latter two.

### 5.2 Options A/B/C/D

| Option | Status | Mechanism | Benefit | Risk |
|---|---|---|---|---|
| A Current | `[IMPLEMENTED]` | Stateless run, rebuild from authority, retrieve on demand | Simplest, replayable, small pollution surface | Long tasks may repeat reads or lose non-authoritative intermediate decisions |
| B Task Capsule | `[CANDIDATE]` | A + goal/constraints/decisions/completed/open-loops/next-action/evidence refs | Clear cross-run resume | Schema, versioning, staleness, and conflict management |
| C Controlled warm set | `[CANDIDATE]` | B + task-scoped cache loaded/evicted by deterministic assembly | Fewer repeated searches within one task | Cache invalidation, synchronization, observability cost |
| D LLM-managed paging | `[CANDIDATE]` | C + LLM chooses STM↔MTM↔LPM movement | May help very long exploratory tasks | Extra rounds, latency, tokens, non-reproducibility, pollution, recovery complexity |

**MEM-08 — Minimal capsule.** If B is adopted, it stores structured checkpoints and
evidence references only, never chain-of-thought, full chat history, or large content
that can be reloaded from authority.

**MEM-09 — Disposable warm set.** If C is adopted, the warm set is limited to one
task, has provenance and invalidation rules, and can be reconstructed from authority
plus L3/L4 retrieval after loss.

**MEM-10 — Evidence gate for paging.** D may enter design only if, on real workloads,
it beats C on correctness, resume quality, p95 latency, token/tool-call cost, and
pollution rate. Architectural novelty is not evidence.

> **External evidence note (backlog-032)**: DeepSeek Engram (arXiv 2601.07372)
> U-curve experiments on a 27B model show that over-allocating resources to memory
> degrades dynamic, context-dependent reasoning. This provides external quantitative
> support for the restraint rules in this section (capsule minimality, discardable
> warm set, evidence gate for paging, and the problem-triggered-escalation
> discipline): pushing more memory into context is not free. Caveat: the paper's
> 75-80%/20-25% split is a **model-parameter budget** allocation and does not
> transfer numerically to an external memory system; this project borrows only the
> qualitative conclusion that too much memory hurts reasoning.

## 6. Agent Tools, Isolation, and Mutation Authority

### 6.1 Calling a tool is not write authority

Current capability permissions are `read`, `propose`, `auto_apply`, `apply`, and
`job`. A subagent may call an allowlisted scoped capability directly; Metatron need
need not relay each call. The LLM still receives no raw SQL, DB connection, arbitrary
vault/file write, or bare `writer.apply` primitive.

Recommended responsibility split:

```text
Metatron/orchestrator = control plane: routing, dispatch, cross-agent conflicts, synthesis
Capability gateway   = policy plane: allowlist, scope, budget, timeout, audit
Deterministic writer = data-plane commit boundary: validate / confirm / commit
```

**MEM-11 — Orthogonal permissions.** “May call this capability” and “may mutate
shared state” are separate decisions. Interface exposure, agent allowlist, and
permission remain separate policy fields.

**MEM-12 — No raw write primitive.** An LLM-controlled agent never gets raw SQL, a
DB connection, arbitrary file writing, or any path that bypasses validators.

**MEM-13 — One deterministic commit boundary per path.** Agent- and user-initiated
proposal mutations pass `writer.apply` validation; trusted internal job pipelines
(for example consolidation via `ltm.write_note`, `ltm.mark_superseded`, and
`vindex.upsert`) use their own deterministic validated write paths. Neither bypasses
validation, and neither requires one orchestrator process to synchronously proxy every
operation. An LLM agent gets no raw storage write primitive on any path.

**MEM-14 — Confirmation fails closed.** Schedule/task writes, batch maintenance, and
other risky mutations require preview→confirm. Decline or timeout means no commit.
`auto_apply` is reserved for explicitly low-risk operations and still validates.

### 6.2 When an agent gets iterative tools

Grant iterative tools only when the next step genuinely depends on the previous
result, sources cannot be known in advance, or several pieces of evidence must be
compared. Recall qualifies. If deterministic code can collect all input first, as for
schedule parsing, curation, or coding tracking, one pure-function call is cheaper,
testable, and replayable.

Each scope should carry `allowed_tools`, read scope, allowed proposal types,
`max_tool_calls`, token/time budget, and expiry. Numeric limits come from measurement.

## 7. Trust, Provenance, Conflict, and Correction

At minimum, distinguish system policy, direct user input, internally verified state,
external untrusted content, and LLM inference. A web page, post, or tool output is data,
not instruction. Before long-term promotion, retain URL/time/hash/source id and pass
curator/writer validation.

**MEM-16 — Isolate untrusted content.** `external_untrusted` content cannot rewrite
agent policy, gain tool authority, or become an authoritative fact without validation.
Prompt injection inside it is quoted data.

When old and new preferences or knowledge conflict, retain both and express correction
through `superseded_by`, time, and provenance. Retrieval surfaces the superseding note.
Suspected poisoning is quarantined, down-ranked, or excluded from active retrieval while
raw evidence remains intact.

## 8. Concurrency, Idempotency, Observability, and Recovery

`agent_runs` records start/finish/status/summary/error, and the top-level guard prevents
a run from staying `running` forever. Independent skills remain idempotent and resumable;
cursors are recovery points.

**MEM-15 — Concurrency protection.** Any future capsule, pending, or shared-state
concurrent update must use version compare-and-swap, atomic claim, or an idempotency
key. A stale patch must never silently overwrite a newer version.

| Failure | Recovery |
|---|---|
| Corrupt/deleted `index.db` | `vindex.rebuild` |
| `.idx` behind JSONL | `transcript.rebuild_idx` |
| Distillation LLM failure | events stay in trash for retry |
| Broken vault frontmatter | skip and log the note; do not crash the vault |
| Duplicate pending confirmation | `[PLANNED]` atomic claim in part-006 slice-001; not claimed solved yet |
| UI session interruption | rebuild from DB1/Beacon/vault authority, not full-chat replay |

## 9. Probe-Verified Implementation Reference

### 9.1 Transcript API

- `append(db_dir, entry_id, kind, payload, ts)`: JSONL before `.idx`.
- `read_by_ids`: seek through `.idx`; report missing ids without raising.
- `read_by_time`: linear scan across monthly files.
- `read_by_keyword`: linear scan; measured around 17ms for 10k lines.
- `rebuild_idx`: rebuild the derived index from JSONL.

### 9.2 sqlite-vec / FTS5 facts

| Probe | Verified behavior | Design consequence |
|---|---|---|
| P1 | sqlite-vec extension must load for every connection | dedicated `vindex._connect()` |
| P2 | vec0 does not support `INSERT OR REPLACE` | upsert = DELETE + INSERT |
| P3 | vec0 rowid accepts INTEGER only | `note_map` maps text note ids |
| P4 | `unicode61` misses CJK; trigram needs ≥3 chars | short queries use LIKE |
| P5 | float32 little-endian blob roundtrips correctly | embeddings are not JSON strings |

Known limits: two-character CJK LIKE has no ranking; transcript keyword search is
linear; vec0 is brute-force KNN and remains acceptable below roughly ten thousand notes.
Upgrade only after observed thresholds, not preemptively.

## 10. Evaluation Plan and Decision Gates

Compare A with B first. Test C only if B remains insufficient; D comes last. Workloads
should include a feature spanning three runs, next-day resume, two parallel subagents,
a user changing constraints, superseded preferences, raw-evidence verification, and a
cancelled then reopened task.

Measure restoration of goal/constraints/next action, repeated searches, context tokens,
LLM/tool calls, p50/p95 latency, stale-state load rate, rejected unproven promotions,
concurrent conflicts, and rebuildability after failure.

**MEM-17 — Problems trigger complexity.** Keep A if it has no reproducible failure.
Stop at B if B solves the problem. Test C only when repeated retrieval or context pressure
is a dominant cost. D must beat C on the same workload.

```text
Does A fail reproducibly? ─no→ keep A
        │yes
        ▼
Is B Task Capsule enough? ─yes→ adopt B
        │no
        ▼
Does C deterministic warm set improve it? ─yes→ adopt C
        │still insufficient
        ▼
Propose D only after LLM paging empirically beats C
```
