# Memory System Technical Specification (part-003)

> Language: English | 繁體中文: [MEMORY-zh.md](MEMORY-zh.md)
> Design authority: [ARCHITECTURE.md](../ARCHITECTURE.md) §4/§5/§6. This document is the
> implementation-level spec, including probe-verified platform behavior
> (2026-07-13, Windows / Python 3.12 / SQLite 3.45 / sqlite-vec 0.1.9).

## 1. System Overview

```
events (DB1)                     vault (DB2)                index.db (derived)
alive ──decay──> trash ──14d──> distill ──> episodic/*.md ──> FTS5 + vec0
  │                │                          │ source_ids
  │                └─raw dump──> transcript/ <┘ (rehydrate)
  └─retrieval hit─> heal (on_hit)
```

Four storage roles (§2): DB1 = System of Record; vault = human knowledge
interface; transcript = raw records (never deleted); index.db = derived,
fully rebuildable.

## 2. Cold Storage Transcript (`core/transcript.py`)

### 2.1 File Format

```
data/transcript/
├── 2026-07.jsonl        # monthly rotation (filename = %Y-%m of fromtimestamp(ts))
└── 2026-07.jsonl.idx    # index: entry_id<TAB>byte_offset<TAB>length
```

One JSONL line per entry (§5.3):

```jsonc
{"entry_id": "evt:123", "ts": 1752300000, "kind": "event_raw", "payload": {...}}
// entry_id namespaces: evt:<events.id> | raw:<pipeline>:<post_id>
// kind: event_raw | sync_raw | llm_io
```

### 2.2 API

| Function | Behavior |
|---|---|
| `append(db_dir, entry_id, kind, payload, ts)` | Write one JSONL line + one .idx line synchronously; returns entry_id |
| `read_by_ids(db_dir, entry_ids)` | O(1) seek via .idx; missing ids reported, never raised |
| `read_by_time(db_dir, start_ts, end_ts)` | Linear scan across monthly files (ts ordered within a file) |
| `read_by_keyword(db_dir, keyword, limit)` | Full linear scan (measured: 10k lines in 17ms — fine at personal scale) |
| `rebuild_idx(db_dir, month)` | Rebuild .idx by rescanning JSONL (crash self-healing; .idx is derived) |

### 2.3 Invariants

1. **Append-only**: no function may rewrite existing lines; no delete API exists
2. Corrupt/stale .idx → `rebuild_idx`; the JSONL is the single source of truth
3. Write order: JSONL flush first, then .idx — worst case after a crash is a
   short .idx (rebuildable); the .idx never points at data that doesn't exist

## 3. Health Metabolism (`core/health.py`)

### 3.1 Parameters (config.py, tunable)

| Constant | Initial | Meaning |
|---|---|---|
| `HEALTH_DECAY_PER_DAY` | 0.05 | linear daily decay (1.0 → 0 in 20 days) |
| `TRASH_RETENTION_DAYS` | 14 | trash retention (referenced within = revived) |

Event lifecycle: written (health=1.0) → untouched for 20 days → trash → 14 days
→ distilled/archived. Total ≈ 34 days (probe P7).

### 3.2 API and State Machine

| Function | Behavior |
|---|---|
| `decay(db, now_ts)` | Whole-table batch: `health -= days × rate` (from last_accessed_at or created_at); skips `immune=1` |
| `to_trash(db, now_ts)` | `alive ∧ health≤0 ∧ immune=0` → `state='trash', trashed_at=now`; **also appends the raw event into transcript** (rehydrate pointer valid from this moment) |
| `on_hit(db, event_ids, now_ts)` | Retrieval hit: health=1.0, last_accessed_at=now; a hit inside trash revives to alive |
| `due_for_distill(db, now_ts)` | Select `trash ∧ trashed_at ≤ now - retention` |
| `mark_archived(db, event_ids)` | After distillation; archived rows never auto-load again |

State machine (§4.1): `alive ⇄ trash → archived`. Immune categories
(schedule/identity/preferences/manually pinned) never decay.
Archived = forgotten = not auto-loaded ≠ deleted (raw text lives in transcript forever).

## 4. Retrieval Index (`core/vindex.py`)

### 4.1 Platform Behavior (probe-verified — do not "fix" by intuition)

| Finding | Consequence |
|---|---|
| sqlite-vec **must be loaded per connection** (P1: `no such module: vec0` otherwise) | vindex owns its `_connect()`; does not share `stm.connect` |
| vec0 **does not support INSERT OR REPLACE** (P2: UNIQUE constraint failure) | upsert = `DELETE WHERE rowid` + `INSERT` |
| vec0 rowid **accepts INTEGER only** (P3); note ids are strings `YYYYMMDD-slug` | `note_map` mapping table required |
| FTS5 **unicode61 never matches CJK**; trigram needs **≥3 chars**; LIKE works on trigram tables; English works fine (P4) | tokenizer = trigram; queries <3 chars degrade to LIKE |
| embedding **binary blob (float32 LE) roundtrips fine** (P5) | store `struct.pack(f"{dim}f", *vec)`, not JSON strings |

### 4.2 Schema (index.db, separate file)

```sql
CREATE TABLE note_map (               -- TEXT note_id ↔ INT rowid (vec0 requirement)
  rowid    INTEGER PRIMARY KEY AUTOINCREMENT,
  note_id  TEXT NOT NULL UNIQUE
);
CREATE VIRTUAL TABLE notes_fts USING fts5(
  note_id, title, summary, tags, tokenize='trigram'
);
CREATE VIRTUAL TABLE notes_vec USING vec0(
  embedding float[1536]               -- dim = config.EMBED_DIM
);
CREATE TABLE meta (                   -- embed-model change ⇒ full rebuild
  key TEXT PRIMARY KEY, value TEXT    -- embed_model / embed_dim / built_at
);
```

### 4.3 API

| Function | Behavior |
|---|---|
| `upsert(idx_db, note_id, title, summary, tags, vector?)` | get/create rowid in note_map → DELETE+INSERT in both FTS5 and vec0; vector=None updates FTS only |
| `search_fts(idx_db, query, limit)` | ≥3 chars (or English tokens) → MATCH; <3 chars → LIKE fallback. Returns `[(note_id, score)]` |
| `search_vec(idx_db, vector, k)` | KNN; returns `[(note_id, distance)]` |
| `rebuild(idx_db, vault_path, embed_fn)` | Full rebuild: scan vault frontmatter → repopulate (used on model change / corruption) |

Invariants: index.db holds no unique data; a change of `meta.embed_model`
forces rebuild; vectorized content = title+summary+tags (full text is served
by FTS/rehydrate).

## 5. Distillation Pipeline (`core/consolidate.py`)

### 5.1 Flow (§6.3)

```
decay → to_trash (raw dump) → due_for_distill → group by day (≤50 per group)
  → LLM distill (consolidator contract) → field-level validation (5 rules)
  → ltm writes notes (with source_ids) → mark_archived → vindex.upsert
  → agent_runs stats
```

### 5.2 Field-Level Validation (5 rules; skip per group, never fail the batch)

1. `kind` ∈ {episodic, preference}
2. `tags` ⊆ controlled vocabulary (INDEX.md)
3. `source_event_ids` ⊆ actual ids of this batch (**LLM must not fabricate sources**)
4. `confidence` ≥ 0.6 (below ⇒ skip, conservative)
5. `summary` non-empty and ≤500 chars

On failure → skip that group + log `proposal_rejected` to events + continue.
The affected events stay in trash (retried next run) — **distillation failure
can never lose data**.

### 5.3 Output

- `kind=episodic` → `vault/episodic/YYYYMMDD-<slug>.md` (frontmatter per §5.2:
  source=consolidation, period, source_ids, distilled_at, model, tags)
- `kind=preference` → `vault/agent/profile/` (decay-immune; source_ids provenance)

## 6. Four-Stage Cascade Retrieval (`core/retrieve.py`)

```
① index-first   match INDEX.md registry one-liners    zero cost, explainable
② FTS5          trigram full-text (CJK≥3 / LIKE)      zero embedding cost
③ vector KNN    sqlite-vec (semantic paraphrase)      one embed call
④ rehydrate     read raw text via source_ids          exact numbers/names
```

Unified return: `[{note_id, path, score, stage}]`.
**Hit closes the loop**: any stage hit → `health.on_hit(source events)` —
frequently-asked memories decay slower (§4.1 metabolism).

## 7. Failure Modes and Recovery

| Failure | Recovery |
|---|---|
| index.db corrupt/deleted | `vindex.rebuild` — derived artifact, zero data loss |
| .idx inconsistent with JSONL | `transcript.rebuild_idx` |
| LLM fails all night | events remain in trash, re-picked next run; agent_runs status=error is auditable |
| Embedding model changed | meta mismatch → forced rebuild + golden queries (backlog-007) |
| vault note frontmatter manually broken | ltm parse failure → skip that note + log to events; never crashes the whole vault |

## 8. Known Limitations

- FTS5 trigram: 2-char CJK queries fall back to LIKE (no ranking); prefer ≥3-char tags
- Decay is linear, not an Ebbinghaus curve — sufficient at personal scale, tunable via config
- Transcript keyword search is a linear scan — 17ms per 10k lines; consider FTS
  only if a single month exceeds ~100k lines (YAGNI)
- sqlite-vec vec0 is brute-force KNN (no ANN index) — imperceptible below ~10k notes
