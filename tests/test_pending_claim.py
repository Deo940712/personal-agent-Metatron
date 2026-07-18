"""part-006-slice-001 裂縫2:pending 原子認領。

`chat.confirm` 舊路徑「讀 → 檢查 status → apply → 標 done」有競態:雙擊或跨介面
同時確認會落地兩次。`stm.pending_claim` 用單一原子 UPDATE
(`SET status='applying' WHERE id=? AND status='pending'`)保證只有一個呼叫者
拿到 rowcount==1;其餘拿到 False,不得執行落地。
"""

import sqlite3
import threading

import pytest

from core import chat, stm, writer

PROPOSAL = {
    "agent": "schedule", "proposal_type": "schedule_change", "target": "new",
    "payload": {"action": "add", "fields": {"title": "開會", "start_at": 1_800_000_000}},
    "confidence": 0.9, "evidence": ["明天開會"],
}


@pytest.fixture()
def db(tmp_path):
    path = tmp_path / "state.db"
    stm.init(path)
    return path


# ── claim 基本語意 ───────────────────────────────────────────────────

def test_claim_pending_succeeds_once(db):
    pid = stm.pending_add(db, PROPOSAL, "preview")
    assert stm.pending_claim(db, pid) is True
    assert stm.pending_get(db, pid)["status"] == "applying"


def test_second_claim_fails(db):
    pid = stm.pending_add(db, PROPOSAL, "preview")
    assert stm.pending_claim(db, pid) is True
    assert stm.pending_claim(db, pid) is False           # 已 applying → 認領失敗


def test_claim_missing_returns_false(db):
    assert stm.pending_claim(db, 999) is False


def test_claim_already_done_returns_false(db):
    pid = stm.pending_add(db, PROPOSAL, "preview")
    assert stm.pending_set_status(db, pid, "done")
    assert stm.pending_claim(db, pid) is False           # 非 pending → 不可認領


def test_applying_is_terminal_for_set_status(db):
    """認領後 set_status 只能從 pending 轉出,applying 不再被 pending 路徑改動。"""
    pid = stm.pending_add(db, PROPOSAL, "preview")
    stm.pending_claim(db, pid)
    assert stm.pending_set_status(db, pid, "cancelled") is False
    assert stm.pending_get(db, pid)["status"] == "applying"


# ── applying 是合法 schema 狀態(CHECK 不擋)──────────────────────────

def test_applying_status_accepted_by_schema(db):
    pid = stm.pending_add(db, PROPOSAL, "preview")
    stm.pending_claim(db, pid)
    # 直接讀 DB 確認 CHECK 沒擋掉 applying(否則 claim 的 UPDATE 會拋)
    con = stm.connect(db)
    try:
        row = con.execute(
            "SELECT status FROM pending_proposals WHERE id=?", (pid,)).fetchone()
    finally:
        con.close()
    assert row[0] == "applying"


# ── 併發:N 執行緒同時 claim,只有一個成功 ─────────────────────────────

def test_concurrent_claims_exactly_one_wins(db):
    pid = stm.pending_add(db, PROPOSAL, "preview")
    results: list[bool] = []
    lock = threading.Lock()
    barrier = threading.Barrier(8)

    def worker():
        barrier.wait()                                   # 儘量同時觸發
        try:
            won = stm.pending_claim(db, pid)
        except sqlite3.OperationalError:
            won = False                                  # 鎖競爭視為未認領,不得算成功
        with lock:
            results.append(won)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert sum(1 for r in results if r) == 1             # 恰好一個認領成功


# ── claim → 落地閉環:認領成功才 apply ───────────────────────────────

def test_claim_then_apply_lands_once(db):
    pid = stm.pending_add(db, PROPOSAL, "preview")
    assert stm.pending_claim(db, pid)
    got = stm.pending_get(db, pid)
    r = writer.confirm_and_apply(got["proposal"], db)
    assert r.ok and stm.schedule_list(db)[0]["title"] == "開會"


# ── pending_finish:從 applying 收尾(claim 後的終態轉移)──────────────

def test_finish_from_applying_to_done(db):
    pid = stm.pending_add(db, PROPOSAL, "preview")
    stm.pending_claim(db, pid)
    assert stm.pending_finish(db, pid, "done") is True
    assert stm.pending_get(db, pid)["status"] == "done"


def test_finish_from_applying_to_cancelled(db):
    pid = stm.pending_add(db, PROPOSAL, "preview")
    stm.pending_claim(db, pid)
    assert stm.pending_finish(db, pid, "cancelled") is True
    assert stm.pending_get(db, pid)["status"] == "cancelled"


def test_finish_requires_applying_state(db):
    """未認領(仍 pending)不可 finish;避免繞過 claim 直接收尾。"""
    pid = stm.pending_add(db, PROPOSAL, "preview")
    assert stm.pending_finish(db, pid, "done") is False
    assert stm.pending_get(db, pid)["status"] == "pending"


def test_finish_rejects_illegal_status(db):
    pid = stm.pending_add(db, PROPOSAL, "preview")
    stm.pending_claim(db, pid)
    with pytest.raises(ValueError):
        stm.pending_finish(db, pid, "pending")           # 只能轉 done/cancelled


# ── chat.confirm 端到端:雙擊只落地一次(裂縫2 的使用者可見保證)────────

def test_chat_confirm_double_click_lands_once(db):
    pid = stm.pending_add(db, PROPOSAL, "preview")
    replies: list[chat.Reply] = []
    lock = threading.Lock()
    barrier = threading.Barrier(2)

    def click():
        barrier.wait()
        try:
            r = chat.confirm(pid, True, db=db)
        except sqlite3.OperationalError:
            return                                       # 鎖競爭:視為未落地
        with lock:
            replies.append(r)

    threads = [threading.Thread(target=click) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # 只建立一筆行程,不論兩次點擊競爭結果如何
    assert len(stm.schedule_list(db)) == 1
    assert stm.pending_get(db, pid)["status"] == "done"


def test_chat_confirm_second_click_reports_handled(db):
    pid = stm.pending_add(db, PROPOSAL, "preview")
    first = chat.confirm(pid, True, db=db)
    second = chat.confirm(pid, True, db=db)
    assert "已建立" in first.text
    assert "已" in second.text and "重發" in second.text  # 第二次:已處理提示
    assert len(stm.schedule_list(db)) == 1
