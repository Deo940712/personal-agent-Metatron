"""part-015-slice-002:知識庫 CRUD(note_write proposal + writer 三 action)。

全走確認(§3.2:寫入/刪除皆需使用者按 ✅);create/edit 落地真 vault + 索引;
delete 復用 ltm.delete_note + 黑名單;tags ⊆ 受控詞彙表。
"""

import pytest

from core import ltm, stm, vindex
from core import proposals as P
from core import writer


@pytest.fixture()
def db(tmp_path):
    path = tmp_path / "state.db"
    stm.init(path)
    return path


@pytest.fixture()
def vault(tmp_path):
    v = tmp_path / "vault"
    ltm.init_vault(v)
    return v


@pytest.fixture()
def idx_db(tmp_path):
    return tmp_path / "index.db"


def _create_prop(**over):
    base = {
        "agent": "orchestrator",
        "proposal_type": "note_write",
        "target": "new",
        "payload": {"action": "create", "title": "手動筆記",
                    "body": "這是我手動新增的知識。", "tags": ["misc"]},
        "confidence": 1.0,
        "evidence": ["新增筆記:手動筆記"],
    }
    base.update(over)
    return base


# ── proposal 驗證 ────────────────────────────────────────────────────


def test_note_write_create_validates():
    p = P.parse_envelope(_create_prop())
    P.validate(p)                                   # 不拋


def test_note_write_always_needs_confirmation():
    for action, target in [("create", "new"), ("edit", "20250101-x"),
                           ("delete", "20250101-x")]:
        payload = {"action": action, "title": "t", "body": "b", "tags": ["misc"]}
        p = P.Proposal("orchestrator", "note_write", target, payload, 1.0, ["e"])
        assert P.needs_confirmation(p) is True      # 刪除尤其要確認


def test_note_write_rejects_unknown_action():
    with pytest.raises(P.ProposalError):
        P.validate(P.parse_envelope(_create_prop(
            payload={"action": "nuke", "title": "t", "body": "b", "tags": ["misc"]})))


def test_note_write_edit_delete_require_note_id():
    # edit/delete 的 target 不可為 'new'
    p = P.parse_envelope(_create_prop(target="new",
                                      payload={"action": "delete"}))
    pre = writer.precheck(p)
    assert not pre.ok


# ── 落地:create ─────────────────────────────────────────────────────


def test_apply_create_writes_note_and_index(db, vault, idx_db):
    p = P.parse_envelope(_create_prop())
    result = writer.apply_note_write(p, vault, idx_db, db=db)
    assert result.ok
    # vault 有檔
    entries = ltm.registry_entries(vault)
    assert any(e["title"] == "手動筆記" for e in entries)
    nid = next(e["id"] for e in entries if e["title"] == "手動筆記")
    note = ltm.read_note(vault, f"semantic/{nid}.md")
    assert "手動新增的知識" in note["body"]
    # 索引可檢索
    assert nid in vindex.notes_by_tag(idx_db, "misc")


def test_apply_create_rejects_tag_outside_vocabulary(db, vault, idx_db):
    p = P.parse_envelope(_create_prop(
        payload={"action": "create", "title": "t", "body": "b",
                 "tags": ["not-a-real-tag"]}))
    result = writer.apply_note_write(p, vault, idx_db, db=db)
    assert not result.ok
    assert "controlled" in result.detail or "詞彙" in result.detail or "tag" in result.detail.lower()
    assert ltm.registry_entries(vault) == []        # 沒落地


# ── 落地:edit ───────────────────────────────────────────────────────


def test_apply_edit_updates_body_and_index(db, vault, idx_db):
    create = writer.apply_note_write(P.parse_envelope(_create_prop()), vault, idx_db, db=db)
    nid = create.row_id or next(e["id"] for e in ltm.registry_entries(vault))
    edit = P.Proposal("orchestrator", "note_write", nid,
                      {"action": "edit", "title": "手動筆記(改)",
                       "body": "改過的內容。", "tags": ["claude"]}, 1.0, ["改筆記"])
    result = writer.apply_note_write(edit, vault, idx_db, db=db)
    assert result.ok
    note = ltm.read_note(vault, f"semantic/{nid}.md")
    assert "改過的內容" in note["body"]
    assert nid in vindex.notes_by_tag(idx_db, "claude")


def test_apply_edit_missing_note_rejected(db, vault, idx_db):
    edit = P.Proposal("orchestrator", "note_write", "20250101-ghost",
                      {"action": "edit", "title": "x", "body": "y",
                       "tags": ["misc"]}, 1.0, ["改"])
    result = writer.apply_note_write(edit, vault, idx_db, db=db)
    assert not result.ok


# ── 落地:delete ─────────────────────────────────────────────────────


def test_apply_delete_removes_note_and_blacklists(db, vault, idx_db):
    create = writer.apply_note_write(P.parse_envelope(_create_prop()), vault, idx_db, db=db)
    nid = create.row_id or next(e["id"] for e in ltm.registry_entries(vault))
    dele = P.Proposal("orchestrator", "note_write", nid,
                      {"action": "delete"}, 1.0, ["刪筆記"])
    result = writer.apply_note_write(dele, vault, idx_db, db=db)
    assert result.ok
    assert not (vault / "semantic" / f"{nid}.md").exists()
    assert not any(e["id"] == nid for e in ltm.registry_entries(vault))
    # 黑名單有 content_hash(防重跑復活)
    bl = vault / ".deleted_hashes.txt"
    assert bl.exists() and bl.read_text(encoding="utf-8").strip()
