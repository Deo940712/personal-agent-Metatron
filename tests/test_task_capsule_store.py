"""part-003.2-slice-001 Todo 7:隔離 SQLite store。

native sqlite3 + WAL + FK + append-only revisions + one current materialized row
per task + observation provenance + idempotency ledger + expected-version CAS。
write 時驗證,read 時再 parse/validate;corrupt row → typed error。
session 刪除不 cascade 刪 capsule/decision。raw SQL/connection 不外洩 store API。
"""

import sqlite3
import threading

import pytest

from experiments.task_capsule import models as m
from experiments.task_capsule import store as S


def _capsule(task_id="t1", version=1, next_action="do x", **over):
    base = dict(
        schema_version=1, task_id=task_id, version=version, status="in_progress",
        goal="g", constraints=("c",), decisions=("d",), completed=(),
        failed_attempts=(), open_loops=("o",), next_action=next_action,
        evidence_refs=(), authority_versions=(("k", "v1"),),
        created_at=1_800_000_000, updated_at=1_800_000_000)
    base.update(over)
    return m.parse_capsule(base)


@pytest.fixture()
def db(tmp_path):
    return tmp_path / "capsule.db"


# ── migration idempotency ────────────────────────────────────────────

def test_init_creates_schema(db):
    S.init(db)
    st = S.Store(db)
    assert st.get_current("nope") is None                 # 空庫可查
    st.close()


def test_init_is_idempotent(db):
    S.init(db)
    S.init(db)                                            # 二次 no-op 不炸
    st = S.Store(db)
    st.close()


# ── create / read / update ───────────────────────────────────────────

def test_put_and_get_current(db):
    S.init(db)
    st = S.Store(db)
    st.put(_capsule(version=1), idempotency_key="k1")
    got = st.get_current("t1")
    assert got.task_id == "t1" and got.version == 1
    st.close()


def test_update_with_cas_advances_current(db):
    S.init(db)
    st = S.Store(db)
    st.put(_capsule(version=1), idempotency_key="k1")
    st.put(_capsule(version=2, next_action="do y"), idempotency_key="k2",
           expected_version=1)
    got = st.get_current("t1")
    assert got.version == 2 and got.next_action == "do y"
    st.close()


# ── CAS：stale expected_version 拒絕 ──────────────────────────────────

def test_stale_cas_rejected(db):
    S.init(db)
    st = S.Store(db)
    st.put(_capsule(version=1), idempotency_key="k1")
    st.put(_capsule(version=2), idempotency_key="k2", expected_version=1)
    with pytest.raises(S.StaleVersionError):
        st.put(_capsule(version=2, next_action="z"), idempotency_key="k3",
               expected_version=1)                        # 已是 v2,expected=1 過期
    st.close()


def test_first_put_rejects_wrong_expected(db):
    S.init(db)
    st = S.Store(db)
    with pytest.raises(S.StaleVersionError):
        st.put(_capsule(version=2), idempotency_key="k", expected_version=1)
    st.close()


# ── idempotency：重複 key 回同結果，不重複寫 ─────────────────────────

def test_duplicate_idempotency_key_returns_same(db):
    S.init(db)
    st = S.Store(db)
    r1 = st.put(_capsule(version=1), idempotency_key="dup")
    r2 = st.put(_capsule(version=1), idempotency_key="dup")   # 重試
    assert r1 == r2
    assert st.revision_count("t1") == 1                   # 未重複寫 revision
    st.close()


# ── append-only revision audit ───────────────────────────────────────

def test_revisions_are_append_only(db):
    S.init(db)
    st = S.Store(db)
    st.put(_capsule(version=1), idempotency_key="k1")
    st.put(_capsule(version=2), idempotency_key="k2", expected_version=1)
    st.put(_capsule(version=3), idempotency_key="k3", expected_version=2)
    assert st.revision_count("t1") == 3
    revs = st.revisions("t1")
    assert [r.version for r in revs] == [1, 2, 3]         # 全保留
    st.close()


# ── observation provenance 刪除不影響 capsule ─────────────────────────

def test_session_delete_does_not_cascade_capsule(db):
    S.init(db)
    st = S.Store(db)
    st.put(_capsule(version=1), idempotency_key="k1")
    st.add_observation("t1", m.parse_observation({
        "source_kind": "opencode", "source_id": "ses-1",
        "captured_at": 1_800_000_000, "authority_class": "observational",
        "version_or_hash": "sha:x", "payload": {"s": 1}}))
    st.delete_observations_by_source("ses-1")             # 刪 session 觀測
    assert st.get_current("t1").version == 1              # capsule 仍在
    assert st.revision_count("t1") == 1
    st.close()


# ── corrupt row → typed error ────────────────────────────────────────

def test_corrupt_current_row_raises_typed(db):
    S.init(db)
    st = S.Store(db)
    st.put(_capsule(version=1), idempotency_key="k1")
    st.close()
    # 繞過 API 直接毀損 current row 的 JSON
    con = sqlite3.connect(db)
    con.execute("UPDATE capsule_current SET capsule_json = ? WHERE task_id = ?",
                ("{not valid json", "t1"))
    con.commit()
    con.close()
    st2 = S.Store(db)
    with pytest.raises(S.StoreCorruptionError):
        st2.get_current("t1")
    st2.close()


# ── reopen persistence ───────────────────────────────────────────────

def test_reopen_persists_all_revisions(db):
    S.init(db)
    st = S.Store(db)
    st.put(_capsule(version=1), idempotency_key="k1")
    st.put(_capsule(version=2), idempotency_key="k2", expected_version=1)
    st.close()
    st2 = S.Store(db)
    assert st2.get_current("t1").version == 2
    assert st2.revision_count("t1") == 2
    st2.close()


# ── 併發：兩 writer 同 expected_version，只有一個成功 ──────────────────

def test_concurrent_cas_exactly_one_wins(db):
    S.init(db)
    seed = S.Store(db)
    seed.put(_capsule(version=1), idempotency_key="k1")
    seed.close()

    wins: list[bool] = []
    lock = threading.Lock()
    barrier = threading.Barrier(6)

    def worker(i):
        st = S.Store(db)
        barrier.wait()
        try:
            st.put(_capsule(version=2, next_action=f"w{i}"),
                   idempotency_key=f"cas-{i}", expected_version=1)
            won = True
        except (S.StaleVersionError, sqlite3.OperationalError):
            won = False
        finally:
            st.close()
        with lock:
            wins.append(won)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert sum(1 for w in wins if w) == 1                 # 恰好一個 CAS 成功
    final = S.Store(db)
    assert final.get_current("t1").version == 2
    assert final.revision_count("t1") == 2                # seed + 一個 winner
    final.close()


# ── 不同 task 互不干擾 ───────────────────────────────────────────────

def test_distinct_tasks_isolated(db):
    S.init(db)
    st = S.Store(db)
    st.put(_capsule(task_id="ta", version=1), idempotency_key="a1")
    st.put(_capsule(task_id="tb", version=1), idempotency_key="b1")
    assert st.get_current("ta").task_id == "ta"
    assert st.get_current("tb").task_id == "tb"
    st.close()
