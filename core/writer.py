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
    f = p.payload.get("fields", {})
    lines = [f"[{p.proposal_type}] action={p.payload.get('action')} target={p.target}"]
    for k, v in f.items():
        shown = stm.fmt_when(v) if k.endswith("_at") and isinstance(v, int) else v
        lines.append(f"  {k} = {shown}")
    return "\n".join(lines)


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
        ok = (stm.schedule_set_status(db, row_id, status) if table == "schedule"
              else stm.task_set_status(db, row_id, status))
        if not ok:
            return _reject(db, f"{p.proposal_type}#{row_id}", "target row not found")
        stm.event_append(db, "writer", "state_change",
                         f"{table} #{row_id} → {status} by {p.agent}", target=f"{table}:{row_id}")
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


def confirm_and_apply(proposal_dict: dict, db: Path | None = None) -> Result:
    """非同步確認流的第二階段(part-002.5):使用者按 ✅ 後落地。

    **重跑 precheck**——precheck 到此刻可能相隔數分鐘,target 可能已被刪/改
    (audit A2/A3)。不信任第一階段的驗證結果:接受 dict,重驗後才落地。
    """
    pre = precheck(proposal_dict, db)
    if not pre.ok:
        return Result("rejected", f"revalidation failed: {pre.reason}")
    return _apply_change(db, pre.proposal)


def apply_validated(p: P.Proposal, db: Path | None = None) -> Result:
    """落地一個剛通過 precheck 的 Proposal(同步 CLI 用:precheck 與落地間無空窗)。"""
    return _apply_change(db, p)


# ── 主入口(CLI:同步 confirm)──────────────────────────────────────

def apply(raw: dict | P.Proposal, confirm_fn: Callable[[str], bool] | None,
          db: Path | None = None) -> Result:
    """七條驗證 + 閘門 → 落地。行為對 CLI 不變(precheck 重構後相容)。

    confirm_fn=None = 非互動環境:需確認的提案一律拒絕(fail-closed)。
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

    return apply_validated(pre.proposal, db)
