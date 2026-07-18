"""part-011 todo 2:consolidate 尾端 routine producer。

completed 事件（含 transcript source_id）→ window-read → extract_routine →
routine facet via writer（durable transcript evidence）。死程式碼 extract_routine
從此有 caller。

關鍵耦合:completed 事件會被代謝/蒸餾,producer 必須讀 alive+trash 視窗,
evidence 指向 transcript source_id（永久）。
"""

from datetime import datetime

import json

import pytest

import config
from core import consolidate, health, ltm, stm, transcript

DAY = 86_400


def _local_completed(db, tdir, title, when_dt):
    """在指定本地時間寫一筆 completed 事件 + transcript(模擬 writer done 路徑)。"""
    ts = int(when_dt.timestamp())
    summary = f"完成 tasks:{title}"
    eid = stm.event_append(db, "user", "completed", summary,
                           target=f"tasks:{title}")
    entry_id = f"evt:{eid}"
    transcript.append(tdir, entry_id, "event_raw",
                      {"summary": summary, "title": title}, ts)
    con = stm.connect(db)
    con.execute("UPDATE events SET source_ids = ?, ts = ? WHERE id = ?",
                (json.dumps([entry_id]), ts, eid))
    con.commit()
    con.close()
    return eid


@pytest.fixture()
def env(tmp_path):
    db = tmp_path / "state.db"
    stm.init(db)
    return {"db": db, "vault": tmp_path / "vault", "tdir": tmp_path / "transcript"}


def test_routine_producer_creates_facet(env):
    """≥3 完成事件跨 ≥3 天(視窗內),主時段 morning → routine facet 建立。"""
    (env["tdir"]).mkdir(parents=True, exist_ok=True)
    base = datetime(2026, 7, 10, 9, 0)         # 本地 09:00 = morning
    for d in range(4):
        _local_completed(env["db"], env["tdir"], f"t{d}",
                         base.replace(day=10 + d))
    now = int(base.replace(day=15).timestamp())   # 完成後幾天(視窗內,夜間 job 情境)
    consolidate.run_routine_producer(env["db"], env["tdir"], now_ts=now)
    facet = stm.facet_get_active(env["db"], "routine", "active_bucket")
    assert facet is not None
    assert facet["value"] == "morning"
    # evidence_ids 是 transcript entry id(durable)且可回水
    eids = json.loads(facet["evidence_ids"])
    assert all(e.startswith("evt:") for e in eids)
    entries, missing = transcript.read_by_ids(env["tdir"], eids)
    assert missing == []


def test_routine_producer_too_few_no_facet(env):
    (env["tdir"]).mkdir(parents=True, exist_ok=True)
    base = datetime(2026, 7, 10, 9, 0)
    for d in range(2):                          # 只 2 筆,不足門檻
        _local_completed(env["db"], env["tdir"], f"t{d}", base.replace(day=10 + d))
    now = int(base.replace(day=15).timestamp())
    consolidate.run_routine_producer(env["db"], env["tdir"], now_ts=now)
    assert stm.facet_get_active(env["db"], "routine", "active_bucket") is None


def test_routine_producer_reads_trashed_events(env):
    """completed 事件已被代謝進 trash,producer 仍在視窗內讀到（不遺漏）。"""
    (env["tdir"]).mkdir(parents=True, exist_ok=True)
    base = datetime(2026, 7, 10, 9, 0)
    for d in range(4):
        _local_completed(env["db"], env["tdir"], f"t{d}", base.replace(day=10 + d))
    now = int(base.replace(day=15).timestamp())
    health.decay(env["db"], now_ts=now)
    health.to_trash(env["db"], now_ts=now, transcript_dir=env["tdir"])
    # producer 仍應讀到（window 含 trash）
    consolidate.run_routine_producer(env["db"], env["tdir"], now_ts=now)
    assert stm.facet_get_active(env["db"], "routine", "active_bucket") is not None


def test_routine_producer_reinforces_not_duplicates(env):
    """第二次跑 → reinforce（evidence_count 增）,不重複建立。"""
    (env["tdir"]).mkdir(parents=True, exist_ok=True)
    base = datetime(2026, 7, 10, 9, 0)
    for d in range(4):
        _local_completed(env["db"], env["tdir"], f"t{d}", base.replace(day=10 + d))
    now = int(base.replace(day=15).timestamp())
    consolidate.run_routine_producer(env["db"], env["tdir"], now_ts=now)
    fid = stm.facet_get_active(env["db"], "routine", "active_bucket")["id"]
    count1 = stm.facet_get(env["db"], fid)["evidence_count"]
    # 再加幾筆 morning 完成 + 再跑
    for d in range(4, 7):
        _local_completed(env["db"], env["tdir"], f"t{d}", base.replace(day=10 + d))
    consolidate.run_routine_producer(env["db"], env["tdir"], now_ts=now)
    active = [f for f in stm.facet_list(env["db"])
              if f["facet_key"] == "active_bucket"]
    assert len(active) == 1                     # 仍只一個 active
    assert stm.facet_get(env["db"], fid)["evidence_count"] > count1


def test_consolidate_run_invokes_routine_producer(env, monkeypatch):
    """consolidate.run 尾端會呼叫 routine producer（掛鉤點）。"""
    called = {"n": 0}
    orig = consolidate.run_routine_producer

    def spy(db, tdir, now_ts=None):
        called["n"] += 1
        return orig(db, tdir, now_ts=now_ts)
    monkeypatch.setattr(consolidate, "run_routine_producer", spy)
    consolidate.run(db=env["db"], vault=env["vault"], transcript_dir=env["tdir"],
                    now_ts=int(datetime(2026, 7, 20).timestamp()),
                    _api=lambda s, u, m, j: '{"groups": []}')
    assert called["n"] == 1
