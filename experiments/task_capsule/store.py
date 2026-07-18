"""隔離 SQLite store(Todo 7)。

native sqlite3 + WAL + FK。append-only revisions + one current materialized row
per task + observation provenance + idempotency ledger + expected-version CAS。
write 時驗證,read 時再 parse/validate;corrupt row → StoreCorruptionError。
raw SQL/connection 不外洩 API。完全獨立於 production DB1。
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from experiments.task_capsule import models as m

_MIGRATION = Path(__file__).with_name("migrations") / "001_init.sql"


class StoreError(ValueError):
    """store 層契約失敗基底。"""


class StaleVersionError(StoreError):
    """expected_version 與 current 不符(CAS 失敗)。"""


class StoreCorruptionError(StoreError):
    """儲存的列無法 parse 回 validated 型別。"""


@dataclass(frozen=True, slots=True)
class Revision:
    task_id: str
    version: int
    capsule: m.Capsule


def _connect(db: Path) -> sqlite3.Connection:
    con = sqlite3.connect(db, timeout=5.0, isolation_level=None)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA foreign_keys=ON")
    con.execute("PRAGMA busy_timeout=5000")
    return con


def init(db: Path) -> None:
    """建 schema(idempotent)。IF NOT EXISTS 使二次呼叫為 no-op。"""
    con = _connect(db)
    try:
        con.executescript(_MIGRATION.read_text(encoding="utf-8"))
    finally:
        con.close()


class Store:
    """單一 experiment DB 的 capsule store。呼叫者只透過方法存取,不碰 SQL。"""

    def __init__(self, db: Path) -> None:
        self._con = _connect(db)

    def close(self) -> None:
        self._con.close()

    # ── read ─────────────────────────────────────────────────────────

    def get_current(self, task_id: str) -> m.Capsule | None:
        row = self._con.execute(
            "SELECT capsule_json FROM capsule_current WHERE task_id = ?",
            (task_id,)).fetchone()
        if row is None:
            return None
        return self._parse_stored(row[0])

    def revision_count(self, task_id: str) -> int:
        row = self._con.execute(
            "SELECT COUNT(*) FROM capsule_revision WHERE task_id = ?",
            (task_id,)).fetchone()
        return int(row[0])

    def revisions(self, task_id: str) -> list[Revision]:
        rows = self._con.execute(
            "SELECT task_id, version, capsule_json FROM capsule_revision "
            "WHERE task_id = ? ORDER BY version", (task_id,)).fetchall()
        return [Revision(r[0], r[1], self._parse_stored(r[2])) for r in rows]

    def _parse_stored(self, raw_json: str) -> m.Capsule:
        try:
            return m.parse_capsule(json.loads(raw_json))
        except (json.JSONDecodeError, m.CapsuleError) as e:
            raise StoreCorruptionError(f"stored capsule is corrupt: {e}") from e

    # ── write（CAS + idempotency + append-only）────────────────────────

    def put(self, capsule: m.Capsule, *, idempotency_key: str,
            expected_version: int | None = None) -> tuple[str, int]:
        """追加一個 capsule revision 並更新 current。回 (task_id, version)。

        expected_version:None = 允許首建(current 必須不存在);否則 current.version
        必須等於 expected_version(CAS)。重複 idempotency_key 回既有結果不重寫。
        """
        task_id = capsule.task_id
        con = self._con
        con.execute("BEGIN IMMEDIATE")
        try:
            # idempotency:同 key 已寫過 → 回既有,不重複
            dup = con.execute(
                "SELECT task_id, version FROM idempotency_ledger WHERE idempotency_key = ?",
                (idempotency_key,)).fetchone()
            if dup is not None:
                con.execute("COMMIT")
                return (dup[0], dup[1])

            cur_row = con.execute(
                "SELECT version FROM capsule_current WHERE task_id = ?",
                (task_id,)).fetchone()
            current_version = cur_row[0] if cur_row else None

            if current_version != expected_version:
                con.execute("ROLLBACK")
                raise StaleVersionError(
                    f"expected_version={expected_version} but current="
                    f"{current_version} for task {task_id}")

            payload = m.to_canonical_json(capsule)
            con.execute(
                "INSERT INTO capsule_revision "
                "(task_id, version, capsule_json, idempotency_key, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (task_id, capsule.version, payload, idempotency_key, capsule.updated_at))
            con.execute(
                "INSERT INTO capsule_current (task_id, version, capsule_json, updated_at) "
                "VALUES (?, ?, ?, ?) "
                "ON CONFLICT(task_id) DO UPDATE SET "
                "version = excluded.version, capsule_json = excluded.capsule_json, "
                "updated_at = excluded.updated_at",
                (task_id, capsule.version, payload, capsule.updated_at))
            con.execute(
                "INSERT INTO idempotency_ledger (idempotency_key, task_id, version, created_at) "
                "VALUES (?, ?, ?, ?)",
                (idempotency_key, task_id, capsule.version, capsule.updated_at))
            con.execute("COMMIT")
            return (task_id, capsule.version)
        except StaleVersionError:
            raise
        except Exception:
            con.execute("ROLLBACK")
            raise

    # ── observation provenance ────────────────────────────────────────

    def add_observation(self, task_id: str, obs: m.Observation) -> None:
        self._con.execute(
            "INSERT INTO observation "
            "(task_id, source_kind, source_id, captured_at, authority_class, "
            "version_or_hash, payload_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (task_id, obs.source_kind, obs.source_id, obs.captured_at,
             str(obs.authority_class), obs.version_or_hash,
             json.dumps(obs.payload, ensure_ascii=False), obs.captured_at))

    def delete_observations_by_source(self, source_id: str) -> int:
        """刪某 session/source 的觀測。不 cascade 刪 capsule(獨立表)。"""
        cur = self._con.execute(
            "DELETE FROM observation WHERE source_id = ?", (source_id,))
        return cur.rowcount
