"""夜間蒸餾 job(ARCHITECTURE §6.3;docs/MEMORY-zh.md §5)。

流程:decay → to_trash(原文落地)→ due_for_distill → 按天分組(每組≤50)
→ LLM 蒸餾 → 欄位級驗證(五條)→ ltm 寫筆記(帶 source_ids)→ mark_archived。

驗證失敗:該組跳過 + events 記 proposal_rejected + 繼續下一組。
該批 events 維持 trash(下輪重試)——蒸餾失敗永不丟資料。
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import config
from core import health, llm, ltm, stm, subagents, vindex

MAX_EVENTS_PER_GROUP = 50
TOPIC_LINK_WINDOW_DAYS = 30    # Membox 輕量版:同 topic 跨天串連的時間窗

_KIND_SUBDIR = {"episodic": "episodic", "preference": "agent/profile"}
_KIND_REQUIRED_TAG = {"episodic": "daily-log", "preference": "preference"}


def _group_by_day(events: list[dict]) -> list[list[dict]]:
    """按天分組;單日超過上限再切(防爆 context)。"""
    by_day: dict[str, list[dict]] = {}
    for e in events:
        by_day.setdefault(datetime.fromtimestamp(e["ts"]).strftime("%Y-%m-%d"),
                          []).append(e)
    groups = []
    for day in sorted(by_day):
        chunk = by_day[day]
        for i in range(0, len(chunk), MAX_EVENTS_PER_GROUP):
            groups.append(chunk[i:i + MAX_EVENTS_PER_GROUP])
    return groups


def _validate_group(group: dict, batch_ids: set[int],
                    allowed_tags: set[str]) -> str | None:
    """MEMORY §5.2 五條。回傳 None = 合格;str = 拒絕原因。"""
    # 第 0 條(audit S6):group 本身必須是 object——LLM 可能回字串/數字混入
    if not isinstance(group, dict):
        return f"group must be an object, got {type(group).__name__}"
    kind = group.get("kind")
    if kind not in _KIND_SUBDIR:
        return f"illegal kind: {kind!r}"

    tags = group.get("tags")
    if not isinstance(tags, list) or not tags:
        return "tags must be a non-empty list"
    illegal = set(tags) - allowed_tags
    if illegal:
        return f"tags not in controlled vocabulary: {sorted(illegal)}"

    src = group.get("source_event_ids")
    if (not isinstance(src, list) or not src
            or not all(isinstance(i, int) and not isinstance(i, bool) for i in src)):
        return "source_event_ids must be a non-empty list of ints"
    fabricated = set(src) - batch_ids
    if fabricated:
        return f"fabricated source_event_ids: {sorted(fabricated)}"

    conf = group.get("confidence")
    if not isinstance(conf, (int, float)) or isinstance(conf, bool) \
            or not (0.0 <= conf <= 1.0):
        return f"confidence out of [0,1]: {conf!r}"
    if conf < config.DISTILL_MIN_CONFIDENCE:
        return f"confidence {conf} below threshold {config.DISTILL_MIN_CONFIDENCE}"

    summary = group.get("summary")
    if not isinstance(summary, str) or not summary.strip() or len(summary) > 500:
        return "summary must be non-empty and <=500 chars"

    title = group.get("title")
    if not isinstance(title, str) or not title.strip():
        return "title must be a non-empty string"

    # 第六條(backlog-022, Membox):topic 供跨天連結,必填
    topic = group.get("topic")
    if not isinstance(topic, str) or not topic.strip() or len(topic) > 30:
        return "topic must be a non-empty string <=30 chars"

    # 第七條(backlog-023, Mneme):supersedes 選填;若給則必須是真實存在
    # 且尚未被 superseded 的 profile 筆記 id(呼叫端傳入 existing_profile_ids)
    return None


def _validate_supersedes(group: dict, existing_profile_ids: set[str]) -> str | None:
    """獨立於 _validate_group(需要 vault 查詢,呼叫端先做)。回 None=合格。

    audit U2:supersedes 只允許 preference kind——episodic 帶 supersedes 曾繞過
    驗證直接執行 mark_superseded(驗證與執行不對稱漏洞)。
    """
    supersedes = group.get("supersedes")
    if supersedes is None:
        return None
    if group.get("kind") != "preference":
        return f"supersedes only allowed on preference kind, got {group.get('kind')!r}"
    if not isinstance(supersedes, str) or not supersedes.strip():
        return "supersedes must be a non-empty string if present"
    if supersedes not in existing_profile_ids:
        return f"supersedes target not found or already superseded: {supersedes!r}"
    return None


def _existing_profile_index(vault: Path) -> tuple[str, set[str]]:
    """既有 agent/profile/ 筆記的 INDEX 一行描述(漸進揭露,§4.2)+ id 集合
    (供 supersedes 驗證;已被 superseded 的排除——不能疊加 supersede 舊鏈)。"""
    lines, ids = [], set()
    for e in ltm.registry_entries(vault):
        if not e["path"].startswith("agent/profile/"):
            continue
        note = ltm.read_note(vault, e["path"])
        if note is None or note["frontmatter"].get("superseded_by"):
            continue
        lines.append(f"- `{e['id']}` — {e['title']} — {e['summary']}")
        ids.add(e["id"])
    return "\n".join(lines), ids


def _distill_batch(batch: list[dict], vault: Path, db: Path | None,
                   _api=None) -> tuple[int, list[int]]:
    """一組(一天)events → LLM → 驗證 → 寫筆記。回傳 (寫入筆記數, 已涵蓋 event ids)。"""
    day = datetime.fromtimestamp(batch[0]["ts"]).strftime("%Y-%m-%d")
    allowed = ltm.controlled_tags(vault)
    listing = "\n".join(
        f"- id={e['id']} [{e['actor']}/{e['action']}] {e['summary']}" for e in batch)
    profile_index, existing_profile_ids = _existing_profile_index(vault)
    parts = [f"允許的 tags: {', '.join(sorted(allowed))}"]
    if profile_index:
        parts.append(f"既有偏好清單:\n{profile_index}")
    parts.append(f"事件({day}):\n{listing}")
    user = "\n".join(parts)

    system = subagents.load_contract("consolidator")
    result = llm.complete_json(system, user, db=db, purpose="consolidate", _api=_api)

    batch_ids = {e["id"] for e in batch}
    written, covered = 0, []
    groups = result.get("groups", [])
    if not isinstance(groups, list):
        # audit S5:LLM 回 groups 非 list → 整批視為無效回應,留 trash 下輪重試
        stm.event_append(db, "consolidator", "proposal_rejected",
                         f"distill response invalid: groups is {type(groups).__name__}")
        return 0, []
    for group in groups:
        reason = _validate_group(group, batch_ids, allowed)
        if reason is None:
            # audit U2:所有 kind 都過 supersedes 驗證(episodic 帶 supersedes 會被拒)
            reason = _validate_supersedes(group, existing_profile_ids)
        if reason:
            stm.event_append(db, "consolidator", "proposal_rejected",
                             f"distill group rejected: {reason}")
            continue  # 逐組跳過,不整批失敗
        source_ids = [f"evt:{i}" for i in group["source_event_ids"]]
        frontmatter = {
            "source": "consolidation",
            "period": day,
            "topic": group["topic"],
            "source_ids": source_ids,
            "distilled_at": datetime.fromtimestamp(stm.now()).strftime("%Y-%m-%d %H:%M"),
            "model": config.LLM_MODEL_CHEAP,
            "tags": group["tags"],
            "summary": group["summary"][:120],
        }
        supersedes = group.get("supersedes")
        if supersedes:
            frontmatter["supersedes"] = supersedes
        note_id = ltm.write_note(
            vault, _KIND_SUBDIR[group["kind"]],
            title=group["title"], body=group["summary"],
            frontmatter=frontmatter,
            ts=batch[0]["ts"])
        if supersedes:
            # 雙側保留(Mneme):新筆記已落地;舊筆記補 superseded_by,不刪不改內容
            marked = ltm.mark_superseded(vault, supersedes, note_id)
            if marked:
                existing_profile_ids.discard(supersedes)  # 同批次後續 group 不可再指它
            stm.event_append(db, "consolidator", "state_change",
                             f"{'superseded' if marked else 'failed to mark superseded'} "
                             f"{supersedes} by {note_id}", target=note_id)
        # 管線尾:進檢索索引(FTS 立即可查;向量由 rebuild/後續補)
        try:
            vindex.upsert(config.INDEX_DB, note_id, title=group["title"],
                          summary=group["summary"][:120], tags=group["tags"])
        except Exception:                        # noqa: BLE001 — 索引是衍生物,失敗不擋蒸餾
            stm.event_append(db, "consolidator", "failed",
                             f"vindex upsert failed for {note_id} (rebuild will fix)")
        if group["kind"] == "episodic":
            new_path = f"episodic/{note_id}.md"
            _link_same_topic(vault, note_id, new_path, group["topic"], day, db)
        written += 1
        covered.extend(group["source_event_ids"])
    return written, covered


def _add_related(vault: Path, path: str, related_id: str) -> bool:
    """筆記 frontmatter 的 related list 補一筆(去重)。回傳是否真的新增。"""
    note = ltm.read_note(vault, path)
    if note is None:
        return False
    fm = note["frontmatter"]
    related = fm.get("related", [])
    if not isinstance(related, list):
        related = []
    if related_id in related:
        return False
    fm["related"] = related + [related_id]
    ltm.update_note_frontmatter(vault, path, fm)
    return True


def _link_same_topic(vault: Path, new_id: str, new_path: str, topic: str,
                     period: str, db: Path | None) -> int:
    """Membox 輕量版(backlog-022):近 TOPIC_LINK_WINDOW_DAYS 天內同 topic 的
    既有 episodic 筆記,雙向補 related 連結——不引入獨立 trace 資料結構,
    僅靠 frontmatter 字串比對,零新模組。回傳新連結數(單向計數,雙向各補一次)。"""
    new_date = datetime.strptime(period, "%Y-%m-%d")
    linked = 0
    for entry in ltm.registry_entries(vault):
        if entry["id"] == new_id or not entry["path"].startswith("episodic/"):
            continue
        note = ltm.read_note(vault, entry["path"])
        if note is None:
            continue
        fm = note["frontmatter"]
        if fm.get("topic") != topic:
            continue
        try:
            other_date = datetime.strptime(str(fm.get("period", "")), "%Y-%m-%d")
        except ValueError:
            continue
        if abs((new_date - other_date).days) > TOPIC_LINK_WINDOW_DAYS:
            continue

        if _add_related(vault, entry["path"], new_id):     # 舊 → 新
            linked += 1
        _add_related(vault, new_path, entry["id"])          # 新 → 舊(雙向)

    if linked:
        stm.event_append(db, "consolidator", "state_change",
                         f"linked {linked} same-topic notes for {new_id} (topic={topic})",
                         target=new_id)
    return linked


def run(db: Path | None = None, vault: Path | None = None,
        transcript_dir: Path | None = None, now_ts: int | None = None,
        _api=None) -> dict:
    """完整夜間 job。回傳統計 dict(寫進 agent_runs summary)。

    設計:LLM 對某天失敗 → 該天跳過(events 留 trash 下輪重試),繼續其他天。
    """
    ts = now_ts or stm.now()
    vault = vault or config.VAULT_PATH
    ltm.init_vault(vault)

    health.decay(db, now_ts=ts)
    trashed = health.to_trash(db, now_ts=ts, transcript_dir=transcript_dir)
    due = health.due_for_distill(db, now_ts=ts)

    stats = {"trashed": len(trashed), "due": len(due),
             "notes_written": 0, "archived": 0, "batches_failed": 0}
    for batch in _group_by_day(due):
        try:
            written, covered = _distill_batch(batch, vault, db, _api=_api)
        except llm.LLMError:
            stats["batches_failed"] += 1
            continue  # 該天留 trash,下輪重試——永不丟資料
        stats["notes_written"] += written
        if covered:
            stats["archived"] += health.mark_archived(db, covered)
    return stats
