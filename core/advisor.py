"""主動建議 / subconscious(part-009;ARCHITECTURE §15.1)。

cron 驅動的 tick:讀 world-diff(自 baseline 起的變化)→ 無重要變化 quiet
(零 LLM)→ 有變化才 reflect(slice-001)。本模組 slice-000 只做**確定性**
world-diff 讀取器 + baseline checkpoint;不呼叫 LLM、不推播、不改真實狀態。

鐵律(ARCHITECTURE §15.2):advice 只建議;任何 action 落地走 writer + 確認。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import config
from core import stm

DAY = 86_400

# baseline checkpoint 存 cursors(復用既有機制,不新增 schema)
_BASELINE_PIPELINE = "advisor"
_BASELINE_KEY = "baseline_ts"

# routine 偏離:完成時間落在非主時段桶,累積達此數即視為偏離訊號
_ROUTINE_DEVIATION_MIN = 2


@dataclass(frozen=True, slots=True)
class WorldDiff:
    """自 baseline 起的確定性世界變化。quiet=True 表示無重要變化。"""

    since_ts: int
    now_ts: int
    new_schedule: list[dict] = field(default_factory=list)      # baseline 後新建行程
    overdue_tasks: list[dict] = field(default_factory=list)     # 逾期未完成待辦
    stalled_projects: list[dict] = field(default_factory=list)  # 有 blockers 的專案
    routine_deviation: dict | None = None                       # 作息偏離(part-007)
    stalling_goals: list[dict] = field(default_factory=list)    # 失速 goal facet

    @property
    def quiet(self) -> bool:
        """無任何值得建議的變化 → quiet tick(零 LLM)。"""
        return not (self.new_schedule or self.overdue_tasks
                    or self.stalled_projects or self.routine_deviation
                    or self.stalling_goals)

    def as_summary(self) -> dict:
        return {
            "new_schedule": len(self.new_schedule),
            "overdue_tasks": len(self.overdue_tasks),
            "stalled_projects": len(self.stalled_projects),
            "routine_deviation": self.routine_deviation is not None,
            "stalling_goals": len(self.stalling_goals),
            "quiet": self.quiet,
        }


def get_baseline(db: Path | None) -> int:
    """讀 baseline checkpoint。未設 → 0(首次 tick 看全部)。"""
    raw = stm.cursor_get(db, _BASELINE_PIPELINE, _BASELINE_KEY)
    if raw is None:
        return 0
    try:
        return int(raw)
    except (ValueError, TypeError):
        return 0


def advance_baseline(db: Path | None, ts: int) -> None:
    """推進 baseline 到 ts。tick 成功才呼叫;失敗不推進(下次重看同視窗)。"""
    stm.cursor_set(db, _BASELINE_PIPELINE, _BASELINE_KEY, str(ts))


def _new_schedule_since(db: Path | None, since_ts: int) -> list[dict]:
    """baseline 後新建的 active 行程(created_at > since_ts)。"""
    con = stm.connect(db)
    try:
        return stm._row_dicts(con.execute(
            "SELECT id, title, start_at, remind_at, created_at FROM schedule "
            "WHERE created_at > ? AND status = 'active' ORDER BY start_at",
            (since_ts,)))
    finally:
        con.close()


def _overdue_tasks(db: Path | None, now_ts: int) -> list[dict]:
    """已逾期(due_at < now)且未完成的待辦。"""
    con = stm.connect(db)
    try:
        return stm._row_dicts(con.execute(
            "SELECT id, title, due_at FROM tasks "
            "WHERE due_at IS NOT NULL AND due_at < ? "
            "AND status IN ('pending','in_progress','waiting_user') "
            "ORDER BY due_at",
            (now_ts,)))
    finally:
        con.close()


def _stalled_projects(db: Path | None) -> list[dict]:
    """有 blockers 的專案(coding_tracker 訊號:停滯)。"""
    out = []
    for proj in stm.project_show(db):
        if proj.get("blockers"):
            out.append({"name": proj["name"], "phase": proj.get("phase"),
                        "blockers": proj["blockers"]})
    return out


def _routine_deviation(db: Path | None, since_ts: int) -> dict | None:
    """作息偏離(part-007):有穩定 active_bucket routine facet,但 baseline 後的
    完成事件落在非主時段桶累積達門檻。純確定性讀取。"""
    facet = stm.facet_get_active(db, "routine", "active_bucket")
    if facet is None:
        return None
    expected = facet["value"]
    con = stm.connect(db)
    try:
        rows = con.execute(
            "SELECT ts FROM events WHERE action = 'completed' AND ts > ?",
            (since_ts,)).fetchall()
    finally:
        con.close()
    from core.facets import _bucket_of
    off = [ts for (ts,) in rows
           if _bucket_of(datetime.fromtimestamp(ts).hour) != expected]
    if len(off) >= _ROUTINE_DEVIATION_MIN:
        return {"expected_bucket": expected, "off_bucket_count": len(off),
                "facet_id": facet["id"]}
    return None


def _stalling_goals(db: Path | None) -> list[dict]:
    """失速 goal facet(part-007):有 active goal 但久未有新證據——以
    last_seen_at 早於 baseline 的一半窗當粗略停滯訊號(保守,不過度推斷)。"""
    return [{"key": f["facet_key"], "value": f["value"],
             "last_seen_at": f["last_seen_at"]}
            for f in stm.facet_list(db, facet_class="goal")]


def observe(db: Path | None, now_ts: int | None = None) -> WorldDiff:
    """確定性 world-diff 讀取器(無 LLM)。回 WorldDiff;quiet 屬性判定短路。

    part-008(Knowledge Scout)未建,「新收知識」訊號暫不接線。
    """
    now = now_ts if now_ts is not None else stm.now()
    since = get_baseline(db)
    return WorldDiff(
        since_ts=since,
        now_ts=now,
        new_schedule=_new_schedule_since(db, since),
        overdue_tasks=_overdue_tasks(db, now),
        stalled_projects=_stalled_projects(db),
        routine_deviation=_routine_deviation(db, since),
        stalling_goals=_stalling_goals(db),
    )


# ── reflect:有變化才呼叫 LLM 產建議(part-009-slice-001)────────────────

def _diff_evidence_ids(diff: WorldDiff) -> set[str]:
    """world-diff 中所有可被引用的真實 id(evidence 屬實驗證用)。"""
    ids: set[str] = set()
    ids.update(f"schedule:{s['id']}" for s in diff.new_schedule)
    ids.update(f"task:{t['id']}" for t in diff.overdue_tasks)
    return ids


def _build_reflect_prompt(diff: WorldDiff, db: Path | None) -> str:
    """把 world-diff + 偏好 facets 組成 reflect 的 user 訊息(確定性)。"""
    lines: list[str] = ["世界變化："]
    for s in diff.new_schedule:
        lines.append(f"- 新增行程：schedule:{s['id']}「{s['title']}」")
    for t in diff.overdue_tasks:
        lines.append(f"- 逾期待辦：task:{t['id']}「{t['title']}」")
    for p in diff.stalled_projects:
        lines.append(f"- 停滯專案：{p['name']}（blockers: {', '.join(p['blockers'])}）")
    if diff.routine_deviation:
        rd = diff.routine_deviation
        lines.append(f"- 作息偏離：平常 {rd['expected_bucket']}，"
                     f"最近 {rd['off_bucket_count']} 筆完成落在其他時段")
    for g in diff.stalling_goals:
        lines.append(f"- 目標：{g['key']} = {g['value']}")

    prefs = [f"- {f['facet_class']}/{f['facet_key']} = {f['value']}"
             for f in stm.facet_list(db)
             if f["facet_class"] in ("preference", "routine", "veto", "goal")]
    if prefs:
        lines.append("\n偏好（Personal Model facets）：")
        lines.extend(prefs)
    return "\n".join(lines)


def _validate_advice(raw: dict, valid_ids: set[str]) -> str | None:
    """單條 advice 欄位級驗證。回 None=合格;str=拒絕原因。

    evidence_ids 可為空(如作息偏離無單一 id);若非空則每條必須是 diff 中真實 id。
    """
    if not isinstance(raw, dict):
        return f"advice must be an object, got {type(raw).__name__}"
    if raw.get("priority") not in stm.ADVICE_PRIORITIES:
        return f"illegal priority: {raw.get('priority')!r}"
    for key in ("observation", "suggestion", "dedup_key"):
        v = raw.get(key)
        if not isinstance(v, str) or not v.strip():
            return f"{key} must be a non-empty string"
    if len(raw["observation"]) > 200 or len(raw["suggestion"]) > 200:
        return "observation/suggestion too long (>200)"
    ev = raw.get("evidence_ids", [])
    if not isinstance(ev, list) or not all(isinstance(e, str) for e in ev):
        return "evidence_ids must be a list of strings"
    fabricated = [e for e in ev if e not in valid_ids]
    if fabricated:
        return f"fabricated evidence_ids not in world-diff: {fabricated[:3]}"
    ttl = raw.get("ttl_days")
    if not isinstance(ttl, int) or isinstance(ttl, bool) or ttl <= 0 or ttl > 30:
        return f"ttl_days must be int in (0, 30]: {ttl!r}"
    return None


def reflect(diff: WorldDiff, db: Path | None, _api=None) -> list[dict]:
    """有變化 → LLM 產建議 → 欄位級驗證 → 回合格 advice dict 列表(未落地)。

    quiet diff 不該進到這裡(tick 已短路);防呆:quiet 直接回空、不呼叫 LLM。
    """
    if diff.quiet:
        return []
    from core import llm, subagents
    system = subagents.load_contract("advisor")
    user = _build_reflect_prompt(diff, db)
    result = llm.complete_json(system, user, db=db, purpose="advise", _api=_api)

    valid_ids = _diff_evidence_ids(diff)
    advices = result.get("advices", [])
    if not isinstance(advices, list):
        stm.event_append(db, "advisor", "proposal_rejected",
                         f"reflect response invalid: advices is {type(advices).__name__}")
        return []
    out = []
    for raw in advices:
        reason = _validate_advice(raw, valid_ids)
        if reason:
            stm.event_append(db, "advisor", "proposal_rejected",
                             f"advice rejected: {reason}")
            continue
        out.append(raw)
    return out


# ── tick:完整流程(observe → quiet 短路 / reflect → 防疲勞 → 落地)──────

def tick(db: Path | None = None, now_ts: int | None = None, _api=None) -> dict:
    """一次 advisor tick。回統計 dict。

    - quiet(無重要變化)→ 推進 baseline、零 LLM。
    - 有變化 → reflect → 防疲勞過濾(配額/去重)→ 落 advices 表 → 推進 baseline。
    - reflect 失敗(LLMError)→ 不推進 baseline(下次重看同視窗)。
    """
    now = now_ts if now_ts is not None else stm.now()
    stm.advice_expire_due(db, now)                 # 先清過期
    diff = observe(db, now_ts=now)

    stats = {"quiet": diff.quiet, "world_diff": diff.as_summary(),
             "advices_created": 0, "skipped_quota": 0, "skipped_dedup": 0}

    if diff.quiet:
        advance_baseline(db, now)
        return stats

    from core import llm
    try:
        candidates = reflect(diff, db, _api=_api)
    except llm.LLMError:
        stats["reflect_failed"] = True
        return stats                                # baseline 不推進,下次重看

    day_start = now - DAY
    dedup_window = now - config.ADVICE_DEDUP_WINDOW_DAYS * DAY
    for raw in candidates:
        if stm.advice_count_since(db, day_start) >= config.ADVICE_DAILY_QUOTA:
            stats["skipped_quota"] += 1
            continue
        if stm.advice_dedup_recent(db, raw["dedup_key"], dedup_window):
            stats["skipped_dedup"] += 1
            continue
        stm.advice_add(
            db, priority=raw["priority"], observation=raw["observation"],
            suggestion=raw["suggestion"], evidence_ids=raw.get("evidence_ids") or None,
            dedup_key=raw["dedup_key"],
            expires_at=now + raw["ttl_days"] * DAY, created_at=now)
        stats["advices_created"] += 1

    advance_baseline(db, now)
    return stats


# ── push / action→confirm / 校準回饋(part-009-slice-002)────────────────

_PRIORITY_RANK = {"low": 0, "medium": 1, "high": 2}


def push_candidates(db: Path | None, now_ts: int | None = None) -> list[dict]:
    """取應主動推播的 pending advice(priority ≥ ADVICE_PUSH_MIN_PRIORITY,未過期)。

    只回候選;實際推播與標記 pushed 由 caller(job_advise)做,以便注入
    notify_fn(Discord DM / console)。
    """
    now = now_ts if now_ts is not None else stm.now()
    floor = _PRIORITY_RANK[config.ADVICE_PUSH_MIN_PRIORITY]
    return [a for a in stm.advice_list(db, state="pending", now_ts=now)
            if _PRIORITY_RANK[a["priority"]] >= floor]


def format_advice(advice: dict) -> str:
    """advice → 人可讀推播文(含 id,供使用者回饋定址)。"""
    return (f"[建議 #{advice['id']} · {advice['priority']}] "
            f"{advice['observation']}\n→ {advice['suggestion']}")


def apply_action(db: Path | None, advice_id: int, action_index: int,
                 confirm_fn, transcript_dir: Path | None = None):
    """執行 advice 附帶的一鍵 action(標準 proposal)——**走 writer + 確認**。

    advice 永不自己行動;action 落地與任何一般 proposal 同路徑(preview→confirm→
    writer)。回 writer.Result;無此 action → None。
    """
    from core import writer
    advice = stm.advice_get(db, advice_id)
    if advice is None or not advice.get("actions"):
        return None
    import json
    actions = json.loads(advice["actions"])
    if not 0 <= action_index < len(actions):
        return None
    proposal = actions[action_index].get("proposal")
    if not isinstance(proposal, dict):
        return None
    return writer.apply(proposal, confirm_fn, db, transcript_dir)


def record_feedback(db: Path | None, advice_id: int, accepted: bool,
                    transcript_dir: Path | None = None) -> dict:
    """使用者接受/忽略建議 → 回饋校準閉環。

    - 標記 advice state(accepted / ignored)。
    - 產生 preference facet 證據:記一筆 event(進冷儲存)並走 writer 產
      profile_facet,facet_key = advice 的 dedup_key(把「使用者對這類建議的
      態度」累積成偏好)。value = accept|ignore。重複 → reinforce → 越用越準;
      忽略某類累積 → 降頻訊號(未來 push 可讀此 facet)。
    走 writer 全驗證;不繞過。回統計 dict。
    """
    from core import writer
    advice = stm.advice_get(db, advice_id)
    if advice is None:
        return {"ok": False, "reason": "advice not found"}
    stm.advice_set_state(db, advice_id, "accepted" if accepted else "ignored")

    dedup_key = advice.get("dedup_key") or f"advice_{advice_id}"
    facet_key = f"advice_pref__{dedup_key}"
    value = "accept" if accepted else "ignore"
    # 回饋事件進冷儲存,取得可驗證的 evidence id
    eid = stm.event_append(db, "user", "decision",
                           f"advice #{advice_id} {value} ({dedup_key})")
    from core import transcript
    transcript.append(transcript_dir, f"evt:{eid}", "event_raw",
                      {"summary": f"advice feedback {value} for {dedup_key}"},
                      ts=stm.now())
    existing = stm.facet_get_active(db, "preference", facet_key)
    action = "reinforce" if existing else "create"
    proposal = {
        "agent": "advisor",
        "proposal_type": "profile_facet",
        "target": f"facet:preference/{facet_key}",
        "payload": {"action": action, "facet_class": "preference",
                    "facet_key": facet_key, "value": value,
                    "evidence_ids": [f"evt:{eid}"]},
        "confidence": 0.7,
        "evidence": [f"advice feedback {value}"],
    }
    res = writer.apply(proposal, None, db, transcript_dir)
    return {"ok": res.ok, "state": value, "facet": res.detail}
