"""part-003-slice-002:ltm vault 寫入層(init/ID 防撞/frontmatter roundtrip/
registry/壞檔不炸)。"""

import pytest

from core import ltm, vindex

TS = 1_752_300_000  # 2025-07


@pytest.fixture()
def vault(tmp_path):
    v = tmp_path / "vault"
    ltm.init_vault(v)
    return v


def test_init_vault_idempotent(vault):
    index_before = (vault / "INDEX.md").read_text(encoding="utf-8")
    ltm.init_vault(vault)                                  # 重跑
    assert (vault / "INDEX.md").read_text(encoding="utf-8") == index_before
    for sub in ("episodic", "agent/profile", "agent/ops", "agent/sop", "semantic"):
        assert (vault / sub).is_dir()


def test_controlled_tags_from_index(vault):
    tags = ltm.controlled_tags(vault)
    assert "daily-log" in tags and "preference" in tags


def test_write_note_roundtrip(vault):
    nid = ltm.write_note(
        vault, "episodic", title="架構定案", body="今天定了 DATA_DIR。",
        frontmatter={"source": "consolidation", "period": "2025-07-12",
                     "source_ids": ["evt:12", "evt:13"],
                     "tags": ["daily-log"], "summary": "定案 DATA_DIR"},
        ts=TS)
    assert nid.startswith("20250712-")                     # YYYYMMDD-slug
    note = ltm.read_note(vault, f"episodic/{nid}.md")
    fm = note["frontmatter"]
    assert fm["id"] == nid
    assert fm["source"] == "consolidation"
    assert fm["source_ids"] == ["evt:12", "evt:13"]        # list roundtrip
    assert fm["tags"] == ["daily-log"]
    assert "DATA_DIR" in note["body"]


def test_note_id_collision_appends_suffix(vault):
    fm = {"source": "consolidation", "tags": ["daily-log"], "summary": "s"}
    a = ltm.write_note(vault, "episodic", title="同名", body="1", frontmatter=dict(fm), ts=TS)
    b = ltm.write_note(vault, "episodic", title="同名", body="2", frontmatter=dict(fm), ts=TS)
    c = ltm.write_note(vault, "episodic", title="同名", body="3", frontmatter=dict(fm), ts=TS)
    assert a != b != c and b.endswith("-2") and c.endswith("-3")   # 永不重用


def test_registry_appended_and_parsed(vault):
    ltm.write_note(vault, "episodic", title="第一篇", body="x",
                   frontmatter={"source": "consolidation", "tags": ["daily-log"],
                                "summary": "第一篇的一行描述"}, ts=TS)
    entries = ltm.registry_entries(vault)
    assert len(entries) == 1
    e = entries[0]
    assert e["title"] == "第一篇" and "一行描述" in e["summary"]
    assert e["path"].startswith("episodic/")


def test_slugify_windows_safe(vault):
    nid = ltm.write_note(vault, "episodic", title='壞字元: <>:"/\\|?* 測試', body="x",
                         frontmatter={"source": "consolidation",
                                      "tags": ["daily-log"], "summary": "s"}, ts=TS)
    assert (vault / "episodic" / f"{nid}.md").exists()     # 檔名合法可建檔


def test_read_note_bad_frontmatter_returns_none(vault):
    bad = vault / "episodic" / "broken.md"
    bad.write_text("沒有 frontmatter 的檔案", encoding="utf-8")
    assert ltm.read_note(vault, "episodic/broken.md") is None      # 不炸
    assert ltm.read_note(vault, "episodic/nonexistent.md") is None


def test_registry_skips_garbage_lines(vault):
    with open(vault / "INDEX.md", "a", encoding="utf-8") as f:
        f.write("這是一行垃圾,不是 registry 格式\n")
    ltm.write_note(vault, "episodic", title="正常", body="x",
                   frontmatter={"source": "consolidation", "tags": ["daily-log"],
                                "summary": "s"}, ts=TS)
    assert len(ltm.registry_entries(vault)) == 1           # 垃圾行不擋解析


# ── part-015-slice-000:INDEX 中文化 ──────────────────────────────────


def test_index_template_explanatory_text_is_chinese(vault):
    """INDEX.md 說明文字中文化(part-015);tag 清單保持英文(系統識別碼)。"""
    text = (vault / "INDEX.md").read_text(encoding="utf-8")
    # 標題/說明中文
    assert "知識庫" in text
    assert "使用方式" in text or "用法" in text
    assert "受控" in text
    # tag 仍英文(受控詞彙表不動)
    assert "`daily-log`" in text and "`rag-knowledge`" in text
    # controlled_tags 仍讀得到(執行期真相解析未壞)
    tags = ltm.controlled_tags(vault)
    assert "daily-log" in tags and "rag-knowledge" in tags


# ── part-015-slice-000:ltm.delete_note 原語 ─────────────────────────


def test_delete_note_removes_file_registry_and_returns_hash(vault, tmp_path):
    """delete_note 三處刪(vault 檔 / registry / 索引)+ 回 content_hash。"""
    idx_db = tmp_path / "index.db"
    nid = ltm.write_note(
        vault, "semantic", title="待刪筆記", body="這是要刪的內容。",
        frontmatter={"source": "manual", "tags": ["misc"], "summary": "待刪"}, ts=TS)
    # 建索引一筆(FTS + map),模擬真實入庫
    vindex.upsert(idx_db, nid, title="待刪筆記", summary="待刪", tags=["misc"])
    assert (vault / "semantic" / f"{nid}.md").exists()
    assert any(e["id"] == nid for e in ltm.registry_entries(vault))

    result = ltm.delete_note(vault, nid, idx_db)

    assert result["file"] is True
    assert result["registry"] == 1
    assert result["index"] is True
    assert result["content_hash"]                          # 回 hash(供黑名單)
    # 三處都清了
    assert not (vault / "semantic" / f"{nid}.md").exists()
    assert not any(e["id"] == nid for e in ltm.registry_entries(vault))
    con = vindex._connect(idx_db)
    try:
        assert con.execute("SELECT 1 FROM note_map WHERE note_id=?", (nid,)).fetchone() is None
        assert con.execute("SELECT 1 FROM notes_fts WHERE note_id=?", (nid,)).fetchone() is None
    finally:
        con.close()


def test_delete_note_missing_file_is_safe(vault, tmp_path):
    """刪不存在的筆記不炸;file=False、content_hash=None。"""
    idx_db = tmp_path / "index.db"
    vindex._connect(idx_db).close()                        # 建空索引 schema
    result = ltm.delete_note(vault, "20250101-nonexistent", idx_db)
    assert result["file"] is False
    assert result["content_hash"] is None
    assert result["registry"] == 0
