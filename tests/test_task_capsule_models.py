"""part-003.2-slice-001 Todo 3:Task Capsule + canonical observation typed models。

隔離實驗原型的資料契約。標準庫 frozen dataclass + StrEnum,無 Pydantic。
parse-then-validate:未知輸入解析成 validated 型別,壞的一律 raise。
邊界:bool-as-int、空 id/goal/next_action、非法 status、非正 version、非法 epoch、
重複 evidence、oversize、completed 無 evidence、未知 schema_version。
canonical 序列化穩定(sort_keys),供 hash/重現。
"""

import pytest

from experiments.task_capsule import models as m

EPOCH = 1_800_000_000


def _capsule(**over):
    base = dict(
        schema_version=1,
        task_id="task-alpha",
        version=1,
        status="in_progress",
        goal="ship slice",
        constraints=("no prod writes",),
        decisions=("use isolated sqlite",),
        completed=(),
        failed_attempts=(),
        open_loops=("write tests",),
        next_action="write models",
        evidence_refs=(),
        authority_versions=(("db1:tasks", "v1"),),
        created_at=EPOCH,
        updated_at=EPOCH,
    )
    base.update(over)
    return base


# ── enums ────────────────────────────────────────────────────────────

def test_status_enum_values():
    assert set(m.CapsuleStatus) == {
        m.CapsuleStatus.OPEN, m.CapsuleStatus.IN_PROGRESS,
        m.CapsuleStatus.BLOCKED, m.CapsuleStatus.DONE, m.CapsuleStatus.CANCELLED}


def test_authority_class_enum_values():
    assert m.AuthorityClass.AUTHORITATIVE != m.AuthorityClass.OBSERVATIONAL


# ── capsule happy path + canonical roundtrip ─────────────────────────

def test_parse_valid_capsule():
    c = m.parse_capsule(_capsule())
    assert c.task_id == "task-alpha" and c.version == 1
    assert c.status is m.CapsuleStatus.IN_PROGRESS


def test_canonical_json_is_stable_and_sorted():
    c = m.parse_capsule(_capsule())
    a = m.to_canonical_json(c)
    b = m.to_canonical_json(c)
    assert a == b                                          # deterministic
    assert a.index('"goal"') < a.index('"task_id"')       # sort_keys 生效
    assert "\\u" not in a                                  # ensure_ascii=False


def test_roundtrip_parse_serialize_parse():
    c1 = m.parse_capsule(_capsule())
    c2 = m.parse_capsule(m.from_canonical_json(m.to_canonical_json(c1)))
    assert c1 == c2


# ── boundary rejections ──────────────────────────────────────────────

@pytest.mark.parametrize("field", ["task_id", "goal", "next_action"])
def test_empty_required_string_rejected(field):
    with pytest.raises(m.CapsuleError):
        m.parse_capsule(_capsule(**{field: ""}))


@pytest.mark.parametrize("field", ["task_id", "goal", "next_action"])
def test_none_required_string_rejected(field):
    with pytest.raises(m.CapsuleError):
        m.parse_capsule(_capsule(**{field: None}))


def test_bool_as_version_rejected():
    """bool 是 int 子類,必須顯式排除(KNOWN_ISSUES B4)。"""
    with pytest.raises(m.CapsuleError):
        m.parse_capsule(_capsule(version=True))


def test_nonpositive_version_rejected():
    with pytest.raises(m.CapsuleError):
        m.parse_capsule(_capsule(version=0))
    with pytest.raises(m.CapsuleError):
        m.parse_capsule(_capsule(version=-1))


def test_invalid_status_rejected():
    with pytest.raises(m.CapsuleError):
        m.parse_capsule(_capsule(status="pausing"))


def test_invalid_epoch_rejected():
    with pytest.raises(m.CapsuleError):
        m.parse_capsule(_capsule(created_at=0))
    with pytest.raises(m.CapsuleError):
        m.parse_capsule(_capsule(created_at=True))


def test_unknown_schema_version_rejected():
    with pytest.raises(m.CapsuleError):
        m.parse_capsule(_capsule(schema_version=999))


def test_duplicate_decisions_rejected():
    with pytest.raises(m.CapsuleError):
        m.parse_capsule(_capsule(decisions=("x", "x")))


def test_oversize_field_rejected():
    with pytest.raises(m.CapsuleError):
        m.parse_capsule(_capsule(goal="A" * (m.MAX_FIELD_CHARS + 1)))


def test_completed_without_evidence_rejected():
    """completed 主張必須附 evidence_refs(溯源硬規則)。"""
    with pytest.raises(m.CapsuleError):
        m.parse_capsule(_capsule(completed=("shipped X",), evidence_refs=()))


def test_completed_with_evidence_ok():
    c = m.parse_capsule(_capsule(
        completed=("shipped X",),
        evidence_refs=(("db1:tasks:1", "sha:abc"),)))
    assert c.completed == ("shipped X",)


def test_list_item_type_enforced():
    with pytest.raises(m.CapsuleError):
        m.parse_capsule(_capsule(constraints=("ok", 123)))


# ── canonical observation ────────────────────────────────────────────

def _obs(**over):
    base = dict(
        source_kind="beacon",
        source_id="part-003.2-slice-001",
        captured_at=EPOCH,
        authority_class="observational",
        version_or_hash="sha:deadbeef",
        payload={"phase": "slice-001", "next": "models"},
    )
    base.update(over)
    return base


def test_parse_valid_observation():
    o = m.parse_observation(_obs())
    assert o.source_kind == "beacon"
    assert o.authority_class is m.AuthorityClass.OBSERVATIONAL


def test_observation_missing_provenance_rejected():
    for field in ("source_kind", "source_id", "version_or_hash"):
        with pytest.raises(m.CapsuleError):
            m.parse_observation(_obs(**{field: ""}))


def test_observation_bad_authority_class_rejected():
    with pytest.raises(m.CapsuleError):
        m.parse_observation(_obs(authority_class="supreme"))


def test_observation_bad_captured_at_rejected():
    with pytest.raises(m.CapsuleError):
        m.parse_observation(_obs(captured_at=True))


def test_observation_payload_must_be_object():
    with pytest.raises(m.CapsuleError):
        m.parse_observation(_obs(payload="not-a-dict"))


def test_observation_canonical_stable():
    o = m.parse_observation(_obs())
    assert m.observation_canonical_json(o) == m.observation_canonical_json(o)


# ── no chain-of-thought / raw chat fields ────────────────────────────

def test_capsule_has_no_freeform_transcript_field():
    """Capsule 契約禁 chain-of-thought/完整聊天(MEM-08)。"""
    fields = set(m.Capsule.__dataclass_fields__)
    for forbidden in ("transcript", "chat", "reasoning", "chain_of_thought", "raw_prompt"):
        assert forbidden not in fields
