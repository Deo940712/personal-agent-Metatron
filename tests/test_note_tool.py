"""part-015-slice-002:note 能力層(明確指令解析 + 走 writer 確認)。"""

import pytest

from core import ltm, stm, vindex
from core.tools import note as note_tool
from core.tools.contracts import CapabilityContext


@pytest.fixture()
def env(tmp_path):
    db = tmp_path / "state.db"
    stm.init(db)
    vault = tmp_path / "vault"
    ltm.init_vault(vault)
    idx_db = tmp_path / "index.db"
    ctx = CapabilityContext(db=db, vault=vault, idx_db=idx_db, channel_ref="user:1")
    return ctx, vault, idx_db, db


def test_create_command_stages_pending(env):
    ctx, vault, idx_db, db = env
    r = note_tool.create("手動筆記 | 這是內容 | misc", ctx)
    assert r.needs_confirmation is True
    assert r.pending_id is not None
    # 尚未落地
    assert ltm.registry_entries(vault) == []
    # 確認後落地
    from core import chat
    chat.confirm(r.pending_id, True, db=db, vault=vault, idx_db=idx_db)
    assert any(e["title"] == "手動筆記" for e in ltm.registry_entries(vault))


def test_create_missing_body_hints_usage(env):
    ctx, *_ = env
    r = note_tool.create("只有標題沒有分隔", ctx)
    assert r.needs_confirmation is False
    assert "用法" in r.text or "|" in r.text


def test_delete_command_stages_pending(env):
    ctx, vault, idx_db, db = env
    nid = ltm.write_note(vault, "semantic", title="待刪", body="x",
                         frontmatter={"source": "manual", "tags": ["misc"],
                                      "summary": "s"}, ts=stm.now())
    vindex.upsert(idx_db, nid, title="待刪", summary="s", tags=["misc"])
    r = note_tool.delete(nid, ctx)
    assert r.needs_confirmation is True
    assert nid in r.text                              # 預覽含目標


def test_edit_command_parses_id_and_fields(env):
    ctx, vault, idx_db, db = env
    nid = ltm.write_note(vault, "semantic", title="原標題", body="原內容",
                         frontmatter={"source": "manual", "tags": ["misc"],
                                      "summary": "s"}, ts=stm.now())
    r = note_tool.edit(f"{nid} 新標題 | 新內容 | claude", ctx)
    assert r.needs_confirmation is True
    assert nid in r.text
