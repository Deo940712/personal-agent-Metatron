-- Task Capsule 隔離 store schema (part-003.2-slice-001, Todo 7).
-- append-only revisions + one current materialized row per task + observation
-- provenance + idempotency ledger. 完全獨立於 production DB1;不共用任何表。

-- 每次 put 追加一列;永不 UPDATE/DELETE(audit 完整)。
CREATE TABLE IF NOT EXISTS capsule_revision (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  task_id       TEXT    NOT NULL,
  version       INTEGER NOT NULL,
  capsule_json  TEXT    NOT NULL,
  idempotency_key TEXT  NOT NULL,
  created_at    INTEGER NOT NULL,
  UNIQUE (task_id, version)
);
CREATE INDEX IF NOT EXISTS idx_revision_task ON capsule_revision(task_id, version);

-- 每個 task 一列;讀取用。CAS 靠此表的 version 比較。
CREATE TABLE IF NOT EXISTS capsule_current (
  task_id       TEXT    PRIMARY KEY,
  version       INTEGER NOT NULL,
  capsule_json  TEXT    NOT NULL,
  updated_at    INTEGER NOT NULL
);

-- idempotency ledger:重複 key 回同一結果,不重複寫。
CREATE TABLE IF NOT EXISTS idempotency_ledger (
  idempotency_key TEXT PRIMARY KEY,
  task_id       TEXT    NOT NULL,
  version       INTEGER NOT NULL,
  created_at    INTEGER NOT NULL
);

-- observation provenance:記 session/source → task 的關聯。刪 session 觀測
-- 不 cascade 刪 capsule(它們是獨立表,無 FK 指向 capsule)。
CREATE TABLE IF NOT EXISTS observation (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  task_id       TEXT    NOT NULL,
  source_kind   TEXT    NOT NULL,
  source_id     TEXT    NOT NULL,
  captured_at   INTEGER NOT NULL,
  authority_class TEXT  NOT NULL,
  version_or_hash TEXT  NOT NULL,
  payload_json  TEXT    NOT NULL,
  created_at    INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_observation_source ON observation(source_id);
CREATE INDEX IF NOT EXISTS idx_observation_task ON observation(task_id);
