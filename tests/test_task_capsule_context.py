"""part-003.2-slice-001 Todo 8:bounded historical context assembly。

只 exact task_id match;全部內容標 historical/non-authoritative;可設 byte/token
budget;固定欄位優先序 goal/constraints -> decisions -> completed -> failed_attempts
-> open_loops -> next_action -> evidence_refs/authority_versions;field-item 邊界截斷
並回 omitted 計數。動作前對比每個 authority version/hash 與 current bundle;stale
欄位排除並標記重讀。永不以 session/topic/free-text 合併。
"""

from experiments.task_capsule import context as C
from experiments.task_capsule import models as m


def _capsule(task_id="t1", **over):
    base = dict(
        schema_version=1, task_id=task_id, version=2, status="in_progress",
        goal="build parser", constraints=("no external deps",),
        decisions=("recursive descent",), completed=("skeleton",),
        failed_attempts=(), open_loops=("tokenizer tests",),
        next_action="add tokenizer tests",
        evidence_refs=(("beacon:CURRENT", "v3"),),
        authority_versions=(("beacon:CURRENT", "v3"), ("git:HEAD", "c3")),
        created_at=1_800_000_000, updated_at=1_800_000_100)
    base.update(over)
    # completed 需 evidence
    if base["completed"] and not base["evidence_refs"]:
        base["evidence_refs"] = (("x", "v"),)
    return m.parse_capsule(base)


CURRENT_AUTHORITY = {"beacon:CURRENT": "v3", "git:HEAD": "c3"}


# ── historical / non-authoritative 標記 ───────────────────────────────

def test_assembly_is_marked_historical():
    a = C.assemble(_capsule(), current_authority=CURRENT_AUTHORITY)
    assert a.historical is True
    assert "historical" in a.text.lower() or "非權威" in a.text


def test_exact_task_only_no_merge():
    a = C.assemble(_capsule(task_id="t1"), current_authority=CURRENT_AUTHORITY)
    assert a.task_id == "t1"                              # 不跨 task 合併


# ── budget:field-item 邊界截斷 + omitted 計數 ────────────────────────

def test_zero_budget_omits_all():
    a = C.assemble(_capsule(), current_authority=CURRENT_AUTHORITY, max_bytes=0)
    assert a.text == "" and a.omitted_count > 0


def test_small_budget_keeps_high_priority_first():
    """budget 小時優先保 goal/constraints(最高優先序)。"""
    a = C.assemble(_capsule(), current_authority=CURRENT_AUTHORITY, max_bytes=40)
    assert "build parser" in a.text                       # goal 最先進
    assert a.omitted_count > 0                            # 低優先被略


def test_exact_budget_keeps_all():
    a = C.assemble(_capsule(), current_authority=CURRENT_AUTHORITY, max_bytes=100000)
    assert a.omitted_count == 0
    assert "add tokenizer tests" in a.text               # next_action 也進


def test_deterministic_output_stable():
    a1 = C.assemble(_capsule(), current_authority=CURRENT_AUTHORITY, max_bytes=200)
    a2 = C.assemble(_capsule(), current_authority=CURRENT_AUTHORITY, max_bytes=200)
    assert a1.text == a2.text and a1.omitted_count == a2.omitted_count


def test_priority_order_goal_before_next_action():
    a = C.assemble(_capsule(), current_authority=CURRENT_AUTHORITY, max_bytes=100000)
    assert a.text.index("build parser") < a.text.index("add tokenizer tests")


# ── authority revalidation:stale 欄位排除 + 標記重讀 ──────────────────

def test_stale_authority_excluded_and_flagged():
    # capsule 引用 beacon:CURRENT v3,但 current 已是 v9 → stale
    stale_current = {"beacon:CURRENT": "v9", "git:HEAD": "c3"}
    a = C.assemble(_capsule(), current_authority=stale_current)
    assert "beacon:CURRENT" in a.stale_sources           # 標記為需重讀
    assert a.actionable is False                          # 有 stale → 不可直接行動


def test_fresh_authority_is_actionable():
    a = C.assemble(_capsule(), current_authority=CURRENT_AUTHORITY)
    assert a.stale_sources == ()
    assert a.actionable is True


def test_missing_current_authority_is_stale():
    # current bundle 缺少 capsule 引用的 source → 視為 stale(不可假設仍有效)
    a = C.assemble(_capsule(), current_authority={"beacon:CURRENT": "v3"})
    assert "git:HEAD" in a.stale_sources
    assert a.actionable is False


def test_superseded_preference_flagged_stale():
    cap = _capsule(
        task_id="pref", authority_versions=(("vault:agent/profile", "v2"),),
        evidence_refs=(("vault:agent/profile", "v2"),),
        completed=(),
        next_action="apply English templates")
    a = C.assemble(cap, current_authority={"vault:agent/profile": "v3"})
    assert "vault:agent/profile" in a.stale_sources       # 舊偏好被取代
    assert a.actionable is False


# ── cross-task / session collision 不影響 ─────────────────────────────

def test_wrong_task_capsule_not_used():
    """context 只接受呼叫者指定的 task capsule;不會自己去撈別的 task。"""
    cap = _capsule(task_id="other")
    a = C.assemble(cap, current_authority=CURRENT_AUTHORITY)
    assert a.task_id == "other"                           # 用哪個 capsule 呼叫者決定


# ── 無 authority_versions 的 capsule:視為不可行動(無法核對)──────────

def test_capsule_without_authority_versions_not_actionable():
    cap = _capsule(authority_versions=(), evidence_refs=(("x", "v"),))
    a = C.assemble(cap, current_authority=CURRENT_AUTHORITY)
    assert a.actionable is False                          # 無可核對的權威版本
