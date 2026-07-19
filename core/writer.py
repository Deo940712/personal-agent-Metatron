"""唯一寫入口(ARCHITECTURE §3.1 七條驗證 + §3.2 危險閘門)。

子 agent 永不直接寫 DB:提案 → writer.apply(proposal, confirm_fn) → 驗證 → 落地。
純確定性程式,無 LLM。

confirm_fn: Callable[[str預覽文], bool] —— CLI 注入 stdin y/N;
Discord(part-002.5)注入按鈕回呼;非互動(scheduler)注入 None → 需確認一律拒絕(fail-closed)。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from core import proposals as P
from core import stm
from core import transcript


@dataclass
class Result:
    status: str          # 'applied' | 'rejected' | 'needs_confirm_rejected'
    detail: str          # 人可讀原因/摘要
    row_id: int | None = None

    @property
    def ok(self) -> bool:
        return self.status == "applied"


def _reject(db: Path | None, proposal_desc: str, reason: str, *,
            status: str = "rejected", target: str | None = None) -> Result:
    """拒絕統一出口:記 events(§3.1 規則 6),不執行、不重試。

    B11:events.target 只放真正的影響對象(row id / 路徑),不放描述字串。
    """
    stm.event_append(db, "writer", "proposal_rejected",
                     f"{proposal_desc}: {reason}", target=target)
    return Result(status=status, detail=reason)


def _preview(p: P.Proposal) -> str:
    """需確認時給使用者看的預覽文(§6.6:預覽 → 確認 → 落地)。"""
    if p.proposal_type == "note_write":
        return _preview_note_write(p)
    f = p.payload.get("fields", {})
    lines = [f"[{p.proposal_type}] action={p.payload.get('action')} target={p.target}"]
    for k, v in f.items():
        shown = stm.fmt_when(v) if k.endswith("_at") and isinstance(v, int) else v
        lines.append(f"  {k} = {shown}")
    return "\n".join(lines)


def _preview_note_write(p: P.Proposal) -> str:
    """note_write 預覽(part-015):人可讀的新增/修改/刪除摘要。"""
    action = p.payload.get("action")
    label = {"create": "新增筆記", "edit": "修改筆記", "delete": "刪除筆記"}.get(
        action, action)
    if action == "delete":
        return f"[{label}] {p.target}\n(刪除後可從黑名單稽核,原文仍在 transcript)"
    title = p.payload.get("title", "")
    tags = " ".join(p.payload.get("tags", []))
    body = str(p.payload.get("body", ""))
    snippet = body if len(body) <= 200 else body[:200] + "…"
    target_str = "(新)" if p.target == "new" else p.target
    return (f"[{label}] {target_str}\n  標題:{title}\n  主題:{tags}\n"
            f"  內容:{snippet}")


# ── 落地(action → SQL;只有這裡碰 DB 寫入)───────────────────────────

_TABLE = {"schedule_change": "schedule", "task_change": "tasks"}
_DONE_STATUS = {"done": "done", "cancel": "cancelled"}


def apply_classify(p: P.Proposal, vault: Path, idx_db: Path,
                   db: Path | None = None) -> Result:
    """classify_note 落地(part-004):frontmatter 更新 + registry + vindex。

    §3.1 規則落實:
    - 規則 2:tags ⊆ INDEX.md 受控詞彙表(執行期真相)
    - 規則 3:evidence 每條需在筆記原文中找到(字串比對;截斷容忍——比對前 2000 字)
    - 規則 4:manual_tags: true 的筆記 → 拒絕(人工修改永不覆蓋)
    """
    from core import ltm, vindex

    note = ltm.read_note(vault, p.target)
    if note is None:
        return _reject(db, "classify_note", f"note not found or unparsable: {p.target}",
                       target=p.target)
    fm = note["frontmatter"]

    # 規則 4:manual_tags 守衛
    if str(fm.get("manual_tags", "")).lower() == "true":
        return _reject(db, "classify_note", "manual_tags=true, never override",
                       target=p.target)

    # 規則 2:受控詞彙表
    allowed = ltm.controlled_tags(vault)
    illegal = set(p.payload["tags"]) - allowed
    if illegal:
        return _reject(db, "classify_note",
                       f"tags not in controlled vocabulary: {sorted(illegal)}",
                       target=p.target)

    # 規則 3:evidence 屬實(在原文前 2000 字內逐條比對)
    haystack = note["body"][:2000]
    missing = [e for e in p.evidence if e not in haystack]
    if missing:
        return _reject(db, "classify_note",
                       f"evidence not found in note body: {missing[0][:50]!r}",
                       target=p.target)

    # 落地:frontmatter 更新(inbox → 正式 tags + score;low-score 走同路)
    fm["tags"] = list(p.payload["tags"])
    fm["score"] = float(p.payload["score"])
    fm["summary"] = p.payload["summary"]
    ltm.update_note_frontmatter(vault, p.target, fm)

    # 高分才進 registry + vindex(低分=metadata 保留但不進檢索面)
    import config as _config
    promoted = fm["score"] >= _config.CURATE_SCORE_THRESHOLD
    if promoted:
        note_id = fm.get("id") or ltm.register_existing(vault, p.target,
                                                        summary=p.payload["summary"])
        try:
            vindex.upsert(idx_db, note_id, title=fm.get("title", Path(p.target).stem),
                          summary=p.payload["summary"], tags=fm["tags"])
        except Exception:                        # noqa: BLE001 — 索引衍生物,不擋落地
            stm.event_append(db, "writer", "failed",
                             f"vindex upsert failed for {p.target} (rebuild will fix)")

    stm.event_append(db, "writer", "state_change",
                     f"classified {p.target} score={fm['score']} "
                     f"{'promoted' if promoted else 'low-score'}", target=p.target)
    return Result("applied", f"{p.target} score={fm['score']} "
                             f"{'promoted' if promoted else 'kept as metadata'}")


def apply_project_update(p: P.Proposal, db: Path | None = None) -> Result:
    """project_update 落地(part-005):stm.project_set upsert(只更新給定欄位)。

    precheck 已驗 target 是已註冊專案;此處純落地 + events 記錄。
    """
    stm.project_set(db, p.target,
                    phase=p.payload["phase"],
                    blockers=p.payload["blockers"],
                    next_action=p.payload["next_action"])
    stm.event_append(db, "writer", "state_change",
                     f"project {p.target} tracked: {p.payload['phase'][:60]}",
                     target=p.target)
    return Result("applied", f"project {p.target} updated")


def apply_facet(p: P.Proposal, db: Path | None = None,
                transcript_dir: Path | None = None) -> Result:
    """profile_facet 落地(part-007-slice-001)。

    驗證(欄位級,§3.1 精神):
    - evidence_ids 每條存在於冷儲存 transcript(不得虛構來源;同 consolidation 規則)
    - create:同 class+key 不得已有 active(要換值走 supersede,不靜默覆蓋)
    - reinforce:目標必須 active 且非 forgotten(資料層雙防線之上再擋一層)
    - supersede:舊 facet 真實、active、未被取代、非 pinned(Mneme 規則)
    """
    from core import transcript

    payload = p.payload
    action = payload["action"]
    desc = f"profile_facet({action})"

    # 不得虛構來源:evidence_ids 逐條驗證存在於 transcript
    _, missing = transcript.read_by_ids(transcript_dir, payload["evidence_ids"])
    if missing:
        return _reject(db, desc,
                       f"evidence_ids not found in transcript: {missing[:3]}")

    facet_class, facet_key = payload["facet_class"], payload["facet_key"]
    existing = stm.facet_get_active(db, facet_class, facet_key)

    if action == "create":
        if existing is not None:
            return _reject(db, desc,
                           f"active facet already exists: {facet_class}/{facet_key} "
                           f"#{existing['id']} (use reinforce or supersede)",
                           target=f"facet:{existing['id']}")
        row_id = stm.facet_insert(db, facet_class, facet_key, payload["value"],
                                  confidence=p.confidence,
                                  evidence_ids=payload["evidence_ids"])
        stm.event_append(db, "writer", "state_change",
                         f"facet create {facet_class}/{facet_key} by {p.agent}",
                         target=f"facet:{row_id}")
        return Result("applied", f"facet #{row_id} created (provisional)", row_id)

    if action == "reinforce":
        if existing is None:
            return _reject(db, desc,
                           f"no active facet to reinforce: {facet_class}/{facet_key}")
        if existing["user_state"] == "pinned":
            # pinned = 使用者裁決;累積證據無意義(評分無效化),直接拒絕以免假象
            return _reject(db, desc, "facet is pinned; scoring is void",
                           target=f"facet:{existing['id']}")
        ok = stm.facet_touch_evidence(db, existing["id"], payload["evidence_ids"],
                                      confidence=p.confidence)
        if not ok:
            return _reject(db, desc, f"facet #{existing['id']} not reinforceable",
                           target=f"facet:{existing['id']}")
        # 升級判定:純函數 detector;promote 條件到了就地升級
        from core import facets as F
        row = stm.facet_get(db, existing["id"])
        assessment = F.assess_row(row)
        promoted = (assessment.decision == "promote"
                    and stm.facet_promote(db, existing["id"], assessment.stability))
        stm.event_append(db, "writer", "state_change",
                         f"facet reinforce {facet_class}/{facet_key} "
                         f"({'promoted to stable' if promoted else 'accumulating'}) "
                         f"by {p.agent}",
                         target=f"facet:{existing['id']}")
        return Result("applied",
                      f"facet #{existing['id']} reinforced"
                      f"{' → stable' if promoted else ''}", existing["id"])

    # supersede:舊 facet → superseded,新值建 active
    old_id = payload["supersedes_id"]
    old = stm.facet_get(db, old_id)
    if old is None:
        return _reject(db, desc, f"supersede target not found: facet#{old_id}")
    if old["state"] not in ("provisional", "stable"):
        return _reject(db, desc,
                       f"supersede target not active: facet#{old_id} "
                       f"state={old['state']}", target=f"facet:{old_id}")
    if old["user_state"] == "pinned":
        return _reject(db, desc, f"facet#{old_id} is pinned; user must unpin first",
                       target=f"facet:{old_id}")
    if (old["facet_class"], old["facet_key"]) != (facet_class, facet_key):
        return _reject(db, desc,
                       f"supersede class/key mismatch: facet#{old_id} is "
                       f"{old['facet_class']}/{old['facet_key']}",
                       target=f"facet:{old_id}")
    # 先讓位(釋放 unique active 槽)再建新——同一交易語義由順序保證:
    # supersede 失敗即中止;insert 失敗時舊 facet 已標記,由 events 可稽核恢復
    if not stm.facet_supersede_mark(db, old_id):
        return _reject(db, desc, f"facet#{old_id} could not be superseded",
                       target=f"facet:{old_id}")
    row_id = stm.facet_insert(db, facet_class, facet_key, payload["value"],
                              confidence=p.confidence,
                              evidence_ids=payload["evidence_ids"])
    stm.facet_link_supersede(db, old_id, row_id)
    stm.event_append(db, "writer", "state_change",
                     f"facet supersede {facet_class}/{facet_key} "
                     f"#{old_id} → #{row_id} by {p.agent}",
                     target=f"facet:{row_id}")
    return Result("applied", f"facet #{old_id} superseded by #{row_id}", row_id)


def apply_note_write(p: P.Proposal, vault: Path, idx_db: Path,
                     db: Path | None = None) -> Result:
    """note_write 落地(part-015 知識庫 CRUD)。三 action:

    - create:ltm.write_note(semantic)+ vindex.upsert(tags ⊆ 受控詞彙表)
    - edit:改 body/title/tags(update_note_frontmatter + 重寫 body)+ 重 upsert
    - delete:ltm.delete_note(三處刪)+ 黑名單(防重跑復活)

    §3.1 規則 2 落實:create/edit 的 tags ⊆ INDEX.md 受控詞彙表。
    """
    from core import ltm, vindex

    action = p.payload["action"]
    desc = f"note_write({action})"

    if action == "delete":
        entry = next((e for e in ltm.registry_entries(vault) if e["id"] == p.target), None)
        md = vault / (entry["path"] if entry else f"semantic/{p.target}.md")
        if not md.exists():
            return _reject(db, desc, f"note not found: {p.target}", target=p.target)
        r = ltm.delete_note(vault, p.target, idx_db)
        # 黑名單(防 import 重跑復活)——與 tools/delete_note.py 同語義
        content_hash = r.get("content_hash")
        if content_hash:
            bl = vault / ".deleted_hashes.txt"
            existing = bl.read_text(encoding="utf-8") if bl.exists() else ""
            if content_hash not in existing:
                with open(bl, "a", encoding="utf-8") as f:
                    f.write(f"{content_hash}  # {p.target}\n")
        stm.event_append(db, "writer", "state_change",
                         f"note deleted {p.target} by {p.agent}", target=p.target)
        return Result("applied", f"已刪除筆記 {p.target}", None)

    # create / edit 共同:tags ⊆ 受控詞彙表(規則 2)
    tags = list(p.payload["tags"])
    allowed = ltm.controlled_tags(vault)
    illegal = set(tags) - allowed
    if illegal:
        return _reject(db, desc,
                       f"tags not in controlled vocabulary: {sorted(illegal)}")

    title = p.payload["title"]
    body = p.payload["body"]
    summary = body.replace("\n", " ")[:120]

    if action == "create":
        note_id = ltm.write_note(
            vault, "semantic", title=title, body=body,
            frontmatter={"source": "manual", "manual_tags": True,
                         "tags": tags, "summary": summary}, ts=stm.now())
        _upsert_index(vindex, idx_db, note_id, title, summary, tags, db)
        stm.event_append(db, "writer", "state_change",
                         f"note created {note_id} by {p.agent}", target=note_id)
        return Result("applied", f"已新增筆記 {note_id}:{title}", None)

    # edit
    note_id = p.target
    entry = next((e for e in ltm.registry_entries(vault) if e["id"] == note_id), None)
    rel_path = entry["path"] if entry else f"semantic/{note_id}.md"
    note = ltm.read_note(vault, rel_path)
    if note is None:
        return _reject(db, desc, f"note not found or unparsable: {note_id}",
                       target=note_id)
    fm = dict(note["frontmatter"])
    fm["title"] = title
    fm["tags"] = tags
    fm["summary"] = summary
    fm["manual_tags"] = True
    # 先寫 frontmatter(body 從 note 帶入),再覆蓋 body:update_note_frontmatter
    # 保留舊 body,故手動重寫整篇以換 body。
    _rewrite_note(vault, rel_path, fm, body)
    _upsert_index(vindex, idx_db, note_id, title, summary, tags, db)
    stm.event_append(db, "writer", "state_change",
                     f"note edited {note_id} by {p.agent}", target=note_id)
    return Result("applied", f"已更新筆記 {note_id}:{title}", None)


def _rewrite_note(vault: Path, rel_path: str, fm: dict, body: str) -> None:
    """重寫整篇(frontmatter + 新 body)。edit 換內容用。"""
    from core import ltm
    lines = ["---"]
    for k, v in fm.items():
        if isinstance(v, list):
            lines.append(f"{k}:")
            lines.extend(f"  - {ltm._yaml_scalar(item)}" for item in v)
        else:
            lines.append(f"{k}: {ltm._yaml_scalar(v)}")
    lines += ["---", "", body, ""]
    (vault / rel_path).write_text("\n".join(lines), encoding="utf-8")


def _upsert_index(vindex, idx_db: Path, note_id: str, title: str,
                  summary: str, tags: list[str], db: Path | None) -> None:
    """索引 upsert;失敗不擋落地(索引衍生物,rebuild 可修)。"""
    try:
        vindex.upsert(idx_db, note_id, title=title, summary=summary, tags=tags)
    except Exception:                                # noqa: BLE001
        stm.event_append(db, "writer", "failed",
                         f"vindex upsert failed for {note_id} (rebuild will fix)")


def _item_title(db: Path | None, table: str, row_id: int) -> str:
    """讀 schedule/tasks 標題(完成事件摘要用)。找不到 → 空字串(防禦)。"""
    con = stm.connect(db)
    try:
        row = con.execute(f"SELECT title FROM {table} WHERE id = ?", (row_id,)).fetchone()
        return row[0] if row else ""
    finally:
        con.close()


def _record_completed(db: Path | None, table: str, row_id: int, title: str) -> int:
    """完成一件 schedule/task → events(action='completed')+ 冷儲存 entry。

    part-011:作息迴圈訊號源。先寫事件取得 id,再以 evt:<id> append transcript,
    最後把 source_ids 補回事件列(durable 回水指標;事件被代謝/蒸餾後原文仍在)。
    """
    summary = f"完成 {table} #{row_id}:{title}".strip()
    event_id = stm.event_append(db, "user", "completed", summary,
                                target=f"{table}:{row_id}")
    entry_id = f"evt:{event_id}"
    transcript.append(None, entry_id, "event_raw",
                      {"summary": summary, "target": f"{table}:{row_id}",
                       "title": title}, stm.now())
    # source_ids 補回(event_append 無此參數的更新路徑,直接 UPDATE)
    con = stm.connect(db)
    try:
        con.execute("UPDATE events SET source_ids = ? WHERE id = ?",
                    (json.dumps([entry_id]), event_id))
        con.commit()
    finally:
        con.close()
    return event_id


def _apply_change(db: Path | None, p: P.Proposal) -> Result:
    table = _TABLE[p.proposal_type]
    action = p.payload["action"]
    fields = dict(p.payload.get("fields", {}))

    if action == "add":
        if table == "schedule":
            row_id = stm.schedule_add(
                db, fields.pop("title"), fields.pop("start_at"),
                end_at=fields.pop("end_at", None),
                remind_at=fields.pop("remind_at", None),
                rrule=fields.pop("rrule", None),
                detail=fields.pop("detail", None))
        else:
            row_id = stm.task_add(
                db, fields.pop("title"),
                due_at=fields.pop("due_at", None),
                detail=fields.pop("detail", None))
        stm.event_append(db, "writer", "state_change",
                         f"{table} add #{row_id} by {p.agent}", target=f"{table}:{row_id}")
        return Result("applied", f"{table} #{row_id} created", row_id)

    row_id = int(p.target)
    if action in _DONE_STATUS:
        status = _DONE_STATUS[action]
        # task_change 的 cancel 沒有對應 status(tasks 無 cancelled)→ archived
        if table == "tasks" and action == "cancel":
            status = "archived"
        title = _item_title(db, table, row_id)     # 取完成事件摘要用(狀態改前先讀)
        ok = (stm.schedule_set_status(db, row_id, status) if table == "schedule"
              else stm.task_set_status(db, row_id, status))
        if not ok:
            return _reject(db, f"{p.proposal_type}#{row_id}", "target row not found")
        stm.event_append(db, "writer", "state_change",
                         f"{table} #{row_id} → {status} by {p.agent}", target=f"{table}:{row_id}")
        # part-011:完成(非取消)寫 completed 事件 + 冷儲存 — 作息迴圈的訊號源。
        # source_ids 指向 transcript(durable,即使事件之後被代謝/蒸餾仍可回水)。
        if action == "done":
            _record_completed(db, table, row_id, title)
        return Result("applied", f"{table} #{row_id} → {status}", row_id)

    # update:只改給定欄位
    con = stm.connect(db)
    try:
        if not con.execute(f"SELECT 1 FROM {table} WHERE id = ?", (row_id,)).fetchone():
            return _reject(db, f"{p.proposal_type}#{row_id}", "target row not found")
        sets = ", ".join(f"{k} = ?" for k in fields)
        con.execute(f"UPDATE {table} SET {sets} WHERE id = ?", (*fields.values(), row_id))
        con.commit()
    finally:
        con.close()
    stm.event_append(db, "writer", "state_change",
                     f"{table} #{row_id} update {sorted(fields)} by {p.agent}",
                     target=f"{table}:{row_id}")
    return Result("applied", f"{table} #{row_id} updated", row_id)


# ── precheck:驗證但不落地(part-002.5 非同步確認的基座)────────────────

@dataclass
class PrecheckResult:
    ok: bool                     # 驗證是否通過(通過 ≠ 已落地)
    needs_confirm: bool          # 是否需使用者確認才能落地
    proposal: P.Proposal | None  # 驗證通過的提案(供後續 apply_validated)
    preview: str = ""            # 需確認時的預覽文
    reason: str = ""             # 失敗原因


def precheck(raw: dict | P.Proposal, db: Path | None = None) -> PrecheckResult:
    """跑 §3.1 全部驗證(信封/target/evidence/enum)但**不落地、不需 confirm_fn**。

    純讀取(target 存在性查詢)+ 失敗時記 events(規則 6)。供 CLI 與 Discord 共用:
    CLI 同步接 confirm 後呼 apply;Discord 存 pending,按鈕後呼 apply_validated。
    """
    try:
        p = raw if isinstance(raw, P.Proposal) else P.parse_envelope(raw)
        P.validate(p)
    except P.ProposalError as e:
        desc = (raw.proposal_type if isinstance(raw, P.Proposal)
                else str(raw.get("proposal_type", "?")))
        _reject(db, desc, str(e))
        return PrecheckResult(False, False, None, reason=str(e))

    desc = f"{p.proposal_type}({p.payload.get('action')})"

    # 規則 1:target 存在
    if p.proposal_type == "classify_note":
        # target = vault 相對路徑(part-004);vault 由呼叫端(curate)先驗——
        # 這裡驗格式:不得絕對路徑/不得跳脫 vault
        if p.target.startswith(("/", "\\")) or ".." in p.target or ":" in p.target:
            reason = f"illegal vault path: {p.target!r}"
            _reject(db, desc, reason)
            return PrecheckResult(False, False, None, reason=reason)
    elif p.proposal_type == "project_update":
        # target = projects.name(part-005);必須已註冊(不自動建專案——
        # 防 LLM 幻覺專案名進表)
        con = stm.connect(db)
        try:
            exists = con.execute(
                "SELECT 1 FROM projects WHERE name = ?", (p.target,)).fetchone()
        finally:
            con.close()
        if not exists:
            reason = f"project not registered: {p.target!r}"
            _reject(db, desc, reason)
            return PrecheckResult(False, False, None, reason=reason)
    elif p.proposal_type == "profile_facet":
        # target = 'facet:<class>/<key>' 描述性定址;真實性驗證(active 存在/
        # evidence 屬實/supersede 目標)在 apply_facet(執行期 DB+transcript 查驗)
        expected = f"facet:{p.payload.get('facet_class')}/{p.payload.get('facet_key')}"
        if p.target != expected:
            reason = f"target must be {expected!r}, got {p.target!r}"
            _reject(db, desc, reason)
            return PrecheckResult(False, False, None, reason=reason)
    elif p.proposal_type == "note_write":
        # part-015:create → target='new';edit/delete → note_id(非 'new')。
        # 路徑格式把關(擋跳脫);筆記存在性驗證在 apply_note_write(執行期查 vault)。
        action = p.payload.get("action")
        if action == "create":
            if p.target != "new":
                reason = f"note_write create target must be 'new', got {p.target!r}"
                _reject(db, desc, reason)
                return PrecheckResult(False, False, None, reason=reason)
        else:  # edit / delete
            if p.target == "new" or "/" in p.target or "\\" in p.target \
                    or ".." in p.target or ":" in p.target:
                reason = f"note_write {action} requires a valid note_id, got {p.target!r}"
                _reject(db, desc, reason)
                return PrecheckResult(False, False, None, reason=reason)
    elif p.payload.get("action") != "add":   # schedule/task:DB rowid(add 例外='new')
        if not p.target.isdigit():
            reason = f"target must be a row id for {p.payload.get('action')}: {p.target!r}"
            _reject(db, desc, reason)
            return PrecheckResult(False, False, None, reason=reason)
        table = _TABLE[p.proposal_type]
        con = stm.connect(db)
        try:
            exists = con.execute(
                f"SELECT 1 FROM {table} WHERE id = ?", (int(p.target),)).fetchone()
        finally:
            con.close()
        if not exists:
            reason = f"target not found: {table}#{p.target}"
            _reject(db, desc, reason)
            return PrecheckResult(False, False, None, reason=reason)

    # 規則 3:evidence 非空
    if not p.evidence:
        _reject(db, desc, "evidence required (original user utterance)")
        return PrecheckResult(False, False, None, reason="evidence required")

    return PrecheckResult(True, P.needs_confirmation(p), p, preview=_preview(p))


def confirm_and_apply(proposal_dict: dict, db: Path | None = None,
                      vault: Path | None = None, idx_db: Path | None = None) -> Result:
    """非同步確認流的第二階段(part-002.5):使用者按 ✅ 後落地。

    **重跑 precheck**——precheck 到此刻可能相隔數分鐘,target 可能已被刪/改
    (audit A2/A3)。不信任第一階段的驗證結果:接受 dict,重驗後才落地。
    vault/idx_db:note_write(part-015)落地用;None 落回 config 預設(生產)。
    """
    pre = precheck(proposal_dict, db)
    if not pre.ok:
        return Result("rejected", f"revalidation failed: {pre.reason}")
    return apply_validated(pre.proposal, db, vault=vault, idx_db=idx_db)


def apply_validated(p: P.Proposal, db: Path | None = None,
                    transcript_dir: Path | None = None,
                    vault: Path | None = None, idx_db: Path | None = None) -> Result:
    """落地一個剛通過 precheck 的 Proposal(同步 CLI 用:precheck 與落地間無空窗)。"""
    if p.proposal_type == "profile_facet":
        return apply_facet(p, db, transcript_dir)
    if p.proposal_type == "note_write":
        import config as _config
        return apply_note_write(p, vault or _config.VAULT_PATH,
                                idx_db or _config.INDEX_DB, db=db)
    return _apply_change(db, p)


# ── 主入口(CLI:同步 confirm)──────────────────────────────────────

def apply(raw: dict | P.Proposal, confirm_fn: Callable[[str], bool] | None,
          db: Path | None = None, transcript_dir: Path | None = None) -> Result:
    """七條驗證 + 閘門 → 落地。行為對 CLI 不變(precheck 重構後相容)。

    confirm_fn=None = 非互動環境:需確認的提案一律拒絕(fail-closed)。
    transcript_dir:profile_facet 的 evidence 驗證用(其餘類型忽略)。
    """
    pre = precheck(raw, db)
    if not pre.ok:
        return Result("rejected", pre.reason)

    if pre.needs_confirm:
        if confirm_fn is None:
            return _reject(db, f"{pre.proposal.proposal_type}({pre.proposal.payload.get('action')})",
                           "confirmation required but non-interactive (fail-closed)",
                           status="needs_confirm_rejected")
        if not confirm_fn(pre.preview):
            return _reject(db, f"{pre.proposal.proposal_type}({pre.proposal.payload.get('action')})",
                           "user declined", status="needs_confirm_rejected")

    return apply_validated(pre.proposal, db, transcript_dir)
