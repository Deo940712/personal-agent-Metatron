"""part-003-slice-001:健康值代謝(decay 數學、immune、狀態機、
trash 落地 transcript、到期撈取、復活)。"""

import json

import pytest

import config
from core import health, stm, transcript

DAY = 86_400


@pytest.fixture()
def db(tmp_path):
    path = tmp_path / "state.db"
    stm.init(path)
    return path


@pytest.fixture()
def tdir(tmp_path):
    return tmp_path / "transcript"


def add_event(db, ts, *, immune=False, summary="事件"):
    return stm.event_append(db, "user", "decision", summary, immune=immune)


def get_event(db, eid):
    con = stm.connect(db)
    try:
        cur = con.execute("SELECT * FROM events WHERE id = ?", (eid,))
        cols = [d[0] for d in cur.description]
        return dict(zip(cols, cur.fetchone()))
    finally:
        con.close()


# ── decay 數學 ────────────────────────────────────────────────────────

def test_decay_linear_from_created_at(db):
    eid = add_event(db, 0)
    created = get_event(db, eid)["created_at"]
    health.decay(db, now_ts=created + 10 * DAY)          # 閒置 10 天
    assert get_event(db, eid)["health"] == pytest.approx(1.0 - 10 * 0.05)


def test_decay_is_idempotent_at_same_instant(db):
    eid = add_event(db, 0)
    ts = get_event(db, eid)["created_at"] + 6 * DAY
    health.decay(db, now_ts=ts)
    h1 = get_event(db, eid)["health"]
    health.decay(db, now_ts=ts)                          # 同時刻重跑
    assert get_event(db, eid)["health"] == h1            # 絕對重算,冪等


def test_decay_floors_at_zero(db):
    eid = add_event(db, 0)
    created = get_event(db, eid)["created_at"]
    health.decay(db, now_ts=created + 100 * DAY)
    assert get_event(db, eid)["health"] == 0.0           # 不出現負數


def test_decay_skips_immune(db):
    eid = add_event(db, 0, immune=True)
    created = get_event(db, eid)["created_at"]
    health.decay(db, now_ts=created + 100 * DAY)
    assert get_event(db, eid)["health"] == 1.0           # 免疫不動


def test_decay_uses_last_accessed_when_present(db):
    eid = add_event(db, 0)
    created = get_event(db, eid)["created_at"]
    health.on_hit(db, [eid], now_ts=created + 10 * DAY)  # 第 10 天被命中
    health.decay(db, now_ts=created + 15 * DAY)          # 只閒置 5 天
    assert get_event(db, eid)["health"] == pytest.approx(1.0 - 5 * 0.05)


# ── to_trash + transcript 落地 ───────────────────────────────────────

def zero_out(db, eid, now):
    health.decay(db, now_ts=now)                          # 衰減到 0


def test_to_trash_dumps_raw_to_transcript(db, tdir):
    eid = add_event(db, 0, summary="重要決定")
    created = get_event(db, eid)["created_at"]
    now = created + 30 * DAY
    zero_out(db, eid, now)
    moved = health.to_trash(db, now_ts=now, transcript_dir=tdir)
    assert moved == [eid]

    ev = get_event(db, eid)
    assert ev["state"] == "trash" and ev["trashed_at"] == now
    assert json.loads(ev["source_ids"]) == [f"evt:{eid}"]      # 回水指標已設

    entries, missing = transcript.read_by_ids(tdir, [f"evt:{eid}"])
    assert missing == [] and entries[0]["payload"]["summary"] == "重要決定"


def test_to_trash_skips_immune_and_healthy(db, tdir):
    healthy = add_event(db, 0)
    immune = add_event(db, 0, immune=True)
    created = get_event(db, healthy)["created_at"]
    health.decay(db, now_ts=created + 100 * DAY)
    moved = health.to_trash(db, now_ts=created + 100 * DAY, transcript_dir=tdir)
    assert healthy in moved and immune not in moved


# ── on_hit 回血/復活 ─────────────────────────────────────────────────

def test_on_hit_heals_and_revives_from_trash(db, tdir):
    eid = add_event(db, 0)
    created = get_event(db, eid)["created_at"]
    now = created + 30 * DAY
    zero_out(db, eid, now)
    health.to_trash(db, now_ts=now, transcript_dir=tdir)

    n = health.on_hit(db, [eid], now_ts=now + DAY)
    assert n == 1
    ev = get_event(db, eid)
    assert (ev["state"], ev["health"], ev["trashed_at"]) == ("alive", 1.0, None)


def test_on_hit_does_not_revive_archived(db, tdir):
    eid = add_event(db, 0)
    created = get_event(db, eid)["created_at"]
    now = created + 30 * DAY
    zero_out(db, eid, now)
    health.to_trash(db, now_ts=now, transcript_dir=tdir)
    health.mark_archived(db, [eid])
    assert health.on_hit(db, [eid]) == 0                  # archived 不復活
    assert get_event(db, eid)["state"] == "archived"


def test_on_hit_empty_list_noop(db):
    assert health.on_hit(db, []) == 0


# ── due_for_distill / mark_archived ──────────────────────────────────

def test_due_for_distill_respects_retention(db, tdir):
    eid = add_event(db, 0)
    created = get_event(db, eid)["created_at"]
    trash_time = created + 30 * DAY
    zero_out(db, eid, trash_time)
    health.to_trash(db, now_ts=trash_time, transcript_dir=tdir)

    not_yet = trash_time + (config.TRASH_RETENTION_DAYS - 1) * DAY
    assert health.due_for_distill(db, now_ts=not_yet) == []          # 未滿保留期

    due_time = trash_time + config.TRASH_RETENTION_DAYS * DAY
    due = health.due_for_distill(db, now_ts=due_time)
    assert [e["id"] for e in due] == [eid]                            # 到期


def test_mark_archived_only_from_trash(db, tdir):
    alive = add_event(db, 0)
    assert health.mark_archived(db, [alive]) == 0                     # alive 不可直跳
    assert get_event(db, alive)["state"] == "alive"


def test_full_lifecycle(db, tdir):
    """整條生命週期:alive → decay → trash(落地)→ 到期 → archived。"""
    eid = add_event(db, 0, summary="生命週期測試")
    created = get_event(db, eid)["created_at"]

    t_trash = created + 21 * DAY
    health.decay(db, now_ts=t_trash)
    health.to_trash(db, now_ts=t_trash, transcript_dir=tdir)

    t_due = t_trash + config.TRASH_RETENTION_DAYS * DAY
    due = health.due_for_distill(db, now_ts=t_due)
    assert [e["id"] for e in due] == [eid]

    health.mark_archived(db, [eid])
    assert get_event(db, eid)["state"] == "archived"
    assert stm.event_query(db) == []                       # 遺忘 = 不主動載入
    entries, _ = transcript.read_by_ids(tdir, [f"evt:{eid}"])
    assert entries[0]["payload"]["summary"] == "生命週期測試"   # ≠ 刪除
