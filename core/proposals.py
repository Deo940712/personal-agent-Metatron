"""提案(Proposal)信封與 payload 驗證(ARCHITECTURE §3.1)。

純確定性程式,無 LLM、無 I/O。writer.py 在此之上做 DB 相關驗證與落地。

part-002 範圍:schedule_change / task_change。
vault 類(classify_note / vault_maintenance / agent_note / project_update)
於 part-003+ 各自的 part 加入 PAYLOAD_VALIDATORS。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# ── 常數(§3.1 對照表)────────────────────────────────────────────────

KNOWN_AGENTS = {"schedule", "curator", "librarian", "coding_tracker", "orchestrator",
                "consolidator"}

# part-007:profile_facet 提案(consolidator 蒸餾偏好 / orchestrator 顯式指示)
FACET_ACTIONS = {"create", "reinforce", "supersede"}
FACET_CLASSES = {"preference", "identity", "routine", "workflow",
                 "veto", "goal", "tooling", "style"}

SCHEDULE_ACTIONS = {"add", "update", "done", "cancel"}

# 需使用者確認的 action(§3.1 規則 7:done 與查詢免確認)
CONFIRM_REQUIRED_ACTIONS = {"add", "update", "cancel"}

SCHEDULE_FIELDS = {"title", "detail", "start_at", "end_at", "remind_at", "rrule"}
TASK_FIELDS = {"title", "detail", "due_at"}

_INT_FIELDS = {"start_at", "end_at", "remind_at", "due_at"}

# B2:NOT NULL 欄位不可被 update 成 None(nullable 欄位 None = 清除,合法)
_NOT_NULL_FIELDS = {"title", "start_at"}

# B3:epoch 合理範圍 2000-01-01 ~ 2100-01-01(界外值會毒化 fmt_when/list)
EPOCH_MIN = 946_684_800
EPOCH_MAX = 4_102_444_800


@dataclass
class Proposal:
    """統一信封。target:DB1 rowid(字串數字)或 vault 路徑;add 時可為 'new'。"""
    agent: str
    proposal_type: str
    target: str
    payload: dict[str, Any]
    confidence: float
    evidence: list[str] = field(default_factory=list)


class ProposalError(ValueError):
    """信封/payload 層級的驗證失敗(writer 會拒絕並記 events)。"""


def parse_envelope(raw: dict[str, Any]) -> Proposal:
    """dict(通常來自 LLM JSON)→ Proposal。缺欄/型別錯 → ProposalError。"""
    missing = {"agent", "proposal_type", "target", "payload", "confidence"} - raw.keys()
    if missing:
        raise ProposalError(f"envelope missing fields: {sorted(missing)}")

    agent = raw["agent"]
    if agent not in KNOWN_AGENTS:
        raise ProposalError(f"unknown agent: {agent!r}")

    confidence = raw["confidence"]
    if not isinstance(confidence, (int, float)) or not (0.0 <= confidence <= 1.0):
        raise ProposalError(f"confidence out of [0,1]: {confidence!r}")

    payload = raw["payload"]
    if not isinstance(payload, dict):
        raise ProposalError("payload must be an object")

    evidence = raw.get("evidence", [])
    if not isinstance(evidence, list) or not all(isinstance(e, str) for e in evidence):
        raise ProposalError("evidence must be a list of strings")

    target = raw["target"]
    if not isinstance(target, str) or not target:
        raise ProposalError("target must be a non-empty string")

    return Proposal(
        agent=agent,
        proposal_type=str(raw["proposal_type"]),
        target=target,
        payload=payload,
        confidence=float(confidence),
        evidence=evidence,
    )


# ── payload 驗證(每 proposal_type 一個)─────────────────────────────

def _validate_change(payload: dict[str, Any], allowed_fields: set[str]) -> None:
    action = payload.get("action")
    if action not in SCHEDULE_ACTIONS:
        raise ProposalError(f"illegal action: {action!r} (allowed: {sorted(SCHEDULE_ACTIONS)})")

    fields = payload.get("fields", {})
    if not isinstance(fields, dict):
        raise ProposalError("fields must be an object")

    unknown = fields.keys() - allowed_fields
    if unknown:
        raise ProposalError(f"unknown fields: {sorted(unknown)}")

    # B1:update 空 fields → SQL 會炸,這裡先拒絕
    if action == "update" and not fields:
        raise ProposalError("update requires at least one field")

    # B2:NOT NULL 欄位不可為 None
    for key in fields.keys() & _NOT_NULL_FIELDS:
        if fields[key] is None:
            raise ProposalError(f"{key} cannot be null")

    for key in fields.keys() & _INT_FIELDS:
        v = fields[key]
        if v is None:
            continue  # nullable 時間欄位:None = 清除
        # B4:bool 是 int 的子類,必須顯式排除
        if isinstance(v, bool) or not isinstance(v, int):
            raise ProposalError(f"{key} must be int epoch seconds, got {type(v).__name__}")
        # B3:界外 epoch 會毒化所有 list 顯示
        if not (EPOCH_MIN <= v <= EPOCH_MAX):
            raise ProposalError(f"{key} out of range [2000-01-01, 2100-01-01]: {v}")

    if action == "add":
        title = fields.get("title")
        if not isinstance(title, str) or not title.strip():
            raise ProposalError("add requires non-empty fields.title")
        if allowed_fields is SCHEDULE_FIELDS and "start_at" not in fields:
            raise ProposalError("schedule add requires fields.start_at")

    # rrule 確定性驗證(LLM 產字串,這裡把關;part-002 支援 DAILY/WEEKLY 子集)
    rrule = fields.get("rrule")
    if rrule is not None:
        _validate_rrule(rrule)


def _validate_rrule(rrule: str) -> None:
    if not isinstance(rrule, str) or not rrule.startswith("FREQ="):
        raise ProposalError(f"rrule must start with FREQ=: {rrule!r}")
    parts = dict(p.split("=", 1) for p in rrule.split(";") if "=" in p)
    if parts.get("FREQ") not in {"DAILY", "WEEKLY"}:
        raise ProposalError(f"unsupported FREQ (part-002 supports DAILY/WEEKLY): {rrule!r}")
    byday = parts.get("BYDAY")
    if byday is not None:
        valid = {"MO", "TU", "WE", "TH", "FR", "SA", "SU"}
        if not set(byday.split(",")) <= valid:
            raise ProposalError(f"illegal BYDAY: {byday!r}")


def validate_schedule_change(payload: dict[str, Any]) -> None:
    _validate_change(payload, SCHEDULE_FIELDS)


def validate_task_change(payload: dict[str, Any]) -> None:
    _validate_change(payload, TASK_FIELDS)


def validate_classify_note(payload: dict[str, Any]) -> None:
    """part-004 curator:score/tags/summary(tags ⊆ 詞彙表由 writer 查 INDEX)。"""
    score = payload.get("score")
    if isinstance(score, bool) or not isinstance(score, (int, float)) \
            or not (0.0 <= score <= 10.0):
        raise ProposalError(f"score out of [0,10]: {score!r}")

    tags = payload.get("tags")
    if not isinstance(tags, list) or not tags \
            or not all(isinstance(t, str) and t.strip() for t in tags):
        raise ProposalError("tags must be a non-empty list of strings")

    summary = payload.get("summary")
    if not isinstance(summary, str) or not summary.strip() or len(summary) > 160:
        raise ProposalError("summary must be non-empty and <=160 chars")


def validate_project_update(payload: dict[str, Any]) -> None:
    """part-005 coding_tracker:phase/blockers/next_action 型別與長度。"""
    phase = payload.get("phase")
    if not isinstance(phase, str) or not phase.strip() or len(phase) > 120:
        raise ProposalError("phase must be non-empty string <=120 chars")

    blockers = payload.get("blockers")
    if not isinstance(blockers, list) or \
            not all(isinstance(b, str) and b.strip() for b in blockers):
        raise ProposalError("blockers must be a list of non-empty strings")
    if len(blockers) > 10:
        raise ProposalError("blockers list too long (>10)")

    next_action = payload.get("next_action")
    if not isinstance(next_action, str) or len(next_action) > 120:
        raise ProposalError("next_action must be a string <=120 chars")


def validate_profile_facet(payload: dict[str, Any]) -> None:
    """part-007 facet 提案:action/class/key/value/evidence_ids 型別與界限。

    evidence_ids 指向冷儲存 entry_id;「存在於 transcript」的執行期驗證在
    writer(此處純結構)。supersede 需 supersedes_id(舊 facet rowid)。
    """
    action = payload.get("action")
    if action not in FACET_ACTIONS:
        raise ProposalError(f"illegal facet action: {action!r} "
                            f"(allowed: {sorted(FACET_ACTIONS)})")

    facet_class = payload.get("facet_class")
    if facet_class not in FACET_CLASSES:
        raise ProposalError(f"illegal facet_class: {facet_class!r}")

    facet_key = payload.get("facet_key")
    if not isinstance(facet_key, str) or not facet_key.strip() or len(facet_key) > 80:
        raise ProposalError("facet_key must be non-empty string <=80 chars")

    value = payload.get("value")
    if not isinstance(value, str) or not value.strip() or len(value) > 500:
        raise ProposalError("value must be non-empty string <=500 chars")

    evidence_ids = payload.get("evidence_ids")
    if not isinstance(evidence_ids, list) or not evidence_ids \
            or not all(isinstance(e, str) and ":" in e for e in evidence_ids):
        raise ProposalError(
            "evidence_ids must be a non-empty list of transcript entry ids "
            "(namespace:id, e.g. 'evt:123')")
    if len(evidence_ids) > 50:
        raise ProposalError("evidence_ids list too long (>50)")

    if action == "supersede":
        old_id = payload.get("supersedes_id")
        if isinstance(old_id, bool) or not isinstance(old_id, int) or old_id <= 0:
            raise ProposalError("supersede requires positive int supersedes_id")


PAYLOAD_VALIDATORS = {
    "schedule_change": validate_schedule_change,
    "task_change": validate_task_change,
    "classify_note": validate_classify_note,
    "project_update": validate_project_update,
    "profile_facet": validate_profile_facet,
    # future: agent_note / vault_maintenance
}


def validate(proposal: Proposal) -> None:
    """信封已 parse 後的 payload 級驗證。未知 proposal_type → ProposalError。"""
    validator = PAYLOAD_VALIDATORS.get(proposal.proposal_type)
    if validator is None:
        raise ProposalError(f"unknown proposal_type: {proposal.proposal_type!r}")
    validator(proposal.payload)


def needs_confirmation(proposal: Proposal) -> bool:
    """§3.2 閘門第二層:寫入類 action 需使用者確認;done 免確認。

    classify_note 免確認:進的是 inbox 緩衝區的正式化(§3.2 自動放行層——
    「sync 管線 inbox 寫入本來就進緩衝區」的延伸;manual_tags 守衛在 writer)。
    """
    if proposal.proposal_type in {"schedule_change", "task_change"}:
        return proposal.payload.get("action") in CONFIRM_REQUIRED_ACTIONS
    if proposal.proposal_type == "classify_note":
        return False
    if proposal.proposal_type == "project_update":
        # 免確認(part-005 DESIGN):唯讀訊號推導的 Working State 快取,
        # 錯了無副作用、下輪自動修正、手動 project_set 永遠優先
        return False
    if proposal.proposal_type == "profile_facet":
        # create/reinforce 免確認:知識層累積,可 forget 逆轉、pin 硬覆蓋;
        # supersede 需確認:§3.2 閘門「supersede 既有筆記」屬需確認層
        return proposal.payload.get("action") == "supersede"
    return True  # 未知類型保守處理(實際上 validate 已擋)
