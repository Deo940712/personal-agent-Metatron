"""健康值代謝(docs/MEMORY-zh.md §3;ARCHITECTURE §4.1)。

狀態機:alive ⇄ trash → archived。免疫(immune=1)永不衰減。
archived = 遺忘 = 不主動載入 ≠ 刪除(原文永在 transcript)。

進 trash 時原文即落地 transcript(回水指標從此有效,不等蒸餾)。
"""

from __future__ import annotations

import json
from pathlib import Path

import config
from core import stm, transcript

_DAY = 86_400


def decay(db: Path | None, now_ts: int | None = None) -> int:
    """全表批次衰減:health -= 閒置天數 × 衰減率(自 last_accessed_at 或
    created_at 起算)。immune / 非 alive 跳過。回傳受影響列數。

    冪等基準:以「絕對閒置時間」重算,重複執行同一時刻結果相同。
    """
    ts = now_ts or stm.now()
    con = stm.connect(db)
    try:
        cur = con.execute(
            """UPDATE events SET health = MAX(0.0, 1.0 -
                 ((? - COALESCE(last_accessed_at, created_at)) / ?) * ?)
               WHERE state = 'alive' AND immune = 0""",
            (ts, float(_DAY), config.HEALTH_DECAY_PER_DAY))
        con.commit()
        return cur.rowcount
    finally:
        con.close()


def to_trash(db: Path | None, now_ts: int | None = None,
             transcript_dir: Path | None = None) -> list[int]:
    """alive ∧ health≤0 ∧ immune=0 → trash + 原文落地 transcript。

    回傳進 trash 的 event ids。落地成功才轉狀態(整筆 try:落地失敗該筆跳過,
    下輪重試——寧可晚進 trash,不可有 trash 無原文)。
    """
    ts = now_ts or stm.now()
    con = stm.connect(db)
    try:
        rows = con.execute(
            "SELECT * FROM events WHERE state = 'alive' AND health <= 0 AND immune = 0"
        ).fetchall()
        cols = [d[0] for d in con.execute("SELECT * FROM events LIMIT 0").description]
    finally:
        con.close()

    moved: list[int] = []
    for row in rows:
        event = dict(zip(cols, row))
        entry_id = f"evt:{event['id']}"
        try:
            transcript.append(transcript_dir, entry_id, "event_raw",
                              {k: event[k] for k in
                               ("ts", "actor", "action", "target", "summary")},
                              event["ts"])
        except OSError:
            continue  # 落地失敗:跳過,維持 alive,下輪重試
        con = stm.connect(db)
        try:
            con.execute(
                """UPDATE events SET state = 'trash', trashed_at = ?,
                   source_ids = COALESCE(source_ids, ?) WHERE id = ?""",
                (ts, json.dumps([entry_id]), event["id"]))
            con.commit()
        finally:
            con.close()
        moved.append(event["id"])
    return moved


def on_hit(db: Path | None, event_ids: list[int],
           now_ts: int | None = None) -> int:
    """檢索命中:回血至 1.0 + 更新 last_accessed_at;trash 內命中 → 復活。
    archived 不復活(已蒸餾,原文走 rehydrate)。回傳受影響列數。"""
    if not event_ids:
        return 0
    ts = now_ts or stm.now()
    marks = ",".join("?" * len(event_ids))
    con = stm.connect(db)
    try:
        cur = con.execute(
            f"""UPDATE events SET health = 1.0, last_accessed_at = ?,
                state = 'alive', trashed_at = NULL
                WHERE id IN ({marks}) AND state IN ('alive', 'trash')""",
            (ts, *event_ids))
        con.commit()
        return cur.rowcount
    finally:
        con.close()


def due_for_distill(db: Path | None, now_ts: int | None = None) -> list[dict]:
    """撈 trash 保留期到期者(蒸餾對象)。"""
    ts = now_ts or stm.now()
    cutoff = ts - config.TRASH_RETENTION_DAYS * _DAY
    con = stm.connect(db)
    try:
        cur = con.execute(
            "SELECT * FROM events WHERE state = 'trash' AND trashed_at <= ? "
            "ORDER BY ts", (cutoff,))
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]
    finally:
        con.close()


def mark_archived(db: Path | None, event_ids: list[int]) -> int:
    """蒸餾完成 → archived(永不再主動載入)。回傳受影響列數。"""
    if not event_ids:
        return 0
    marks = ",".join("?" * len(event_ids))
    con = stm.connect(db)
    try:
        cur = con.execute(
            f"UPDATE events SET state = 'archived' WHERE id IN ({marks}) "
            f"AND state = 'trash'", event_ids)
        con.commit()
        return cur.rowcount
    finally:
        con.close()
