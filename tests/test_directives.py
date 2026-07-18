"""part-006-slice-002:DB1 第八表 directives(遠端下指令佇列)。

遠端下指令 → DB1 directives(pending)→ 下次 OpenCode session 開場讀取 → consume。
狀態:pending / consumed / cancelled。CRUD idempotent;consume 只從 pending 轉出。
"""

import pytest

from core import stm


@pytest.fixture()
def db(tmp_path):
    path = tmp_path / "state.db"
    stm.init(path)
    return path


# ── schema:directives 是第八表 ───────────────────────────────────────

def test_directives_table_created(db):
    assert "directives" in stm.existing_tables(db)


def test_init_idempotent_with_directives(db):
    stm.init(db)                                          # 二次不炸
    assert "directives" in stm.existing_tables(db)


# ── add / list ───────────────────────────────────────────────────────

def test_directive_add_returns_id(db):
    did = stm.directive_add(db, "my-agent", "curator 做完先跑 audit")
    assert isinstance(did, int) and did >= 1


def test_directive_list_pending(db):
    stm.directive_add(db, "my-agent", "task A")
    stm.directive_add(db, "my-agent", "task B")
    pending = stm.directive_list(db, status="pending")
    assert len(pending) == 2
    assert {d["text"] for d in pending} == {"task A", "task B"}
    assert all(d["status"] == "pending" for d in pending)


def test_directive_list_filters_by_project(db):
    stm.directive_add(db, "proj-a", "A")
    stm.directive_add(db, "proj-b", "B")
    a = stm.directive_list(db, project="proj-a")
    assert len(a) == 1 and a[0]["text"] == "A"


def test_directive_list_all_statuses(db):
    d1 = stm.directive_add(db, "p", "x")
    stm.directive_consume(db, d1)
    stm.directive_add(db, "p", "y")
    assert len(stm.directive_list(db)) == 2               # 無 status filter = 全部
    assert len(stm.directive_list(db, status="pending")) == 1


# ── consume:pending → consumed(記 consumed_at)────────────────────────

def test_directive_consume_marks_consumed(db):
    did = stm.directive_add(db, "p", "do it")
    assert stm.directive_consume(db, did) is True
    got = [d for d in stm.directive_list(db) if d["id"] == did][0]
    assert got["status"] == "consumed" and got["consumed_at"] is not None


def test_directive_consume_only_from_pending(db):
    did = stm.directive_add(db, "p", "x")
    stm.directive_consume(db, did)
    assert stm.directive_consume(db, did) is False        # 已 consumed → 不再動


def test_directive_consume_missing_returns_false(db):
    assert stm.directive_consume(db, 999) is False


# ── cancel:pending → cancelled ───────────────────────────────────────

def test_directive_cancel(db):
    did = stm.directive_add(db, "p", "x")
    assert stm.directive_cancel(db, did) is True
    got = stm.directive_list(db)[0]
    assert got["status"] == "cancelled"


def test_directive_cancel_only_from_pending(db):
    did = stm.directive_add(db, "p", "x")
    stm.directive_consume(db, did)
    assert stm.directive_cancel(db, did) is False         # consumed 不可 cancel


# ── 空文字拒絕 ───────────────────────────────────────────────────────

def test_directive_add_rejects_empty_text(db):
    with pytest.raises(ValueError):
        stm.directive_add(db, "p", "   ")


def test_directive_add_rejects_empty_project(db):
    with pytest.raises(ValueError):
        stm.directive_add(db, "", "x")


# ── 跨行程持久(無狀態)───────────────────────────────────────────────

def test_directive_survives_reconnect(db):
    did = stm.directive_add(db, "p", "persist me")
    # 新連線(模擬新 process)
    got = [d for d in stm.directive_list(db) if d["id"] == did]
    assert got and got[0]["text"] == "persist me"
