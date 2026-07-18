"""transform 測試:node → normalize → Markdown。用真探勘 dump 當 fixture。

FB saved schema(phase 0 釘死):
  data.content_collection.collection_items.edges[].node
  node.savable.id                       貼文 id(dedupe key)
  node.savable.savable_title.text       內文
  node.savable.savable_permalink        原文連結(或 node.savable.story.url)
  node.savable.savable_image.uri        圖片(fbcdn,會過期)
  node.savable.savable_default_category POST_WITH_PHOTO 等
  node.saver.name / .profile_url        存貼文的人(=你自己)
  collection_items.page_info.end_cursor 分頁
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import transform  # noqa: E402

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "saved_page_sample.json"


@pytest.fixture()
def saved_page() -> dict:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return transform.extract_collection(payload)


# ── extract_collection:找到 saved 資料塊 ─────────────────────────────

def test_extract_collection_finds_edges(saved_page):
    assert "edges" in saved_page and "page_info" in saved_page
    assert len(saved_page["edges"]) >= 1


def test_extract_collection_returns_none_for_non_saved():
    assert transform.extract_collection({"data": {"viewer": {}}}) is None


def test_page_info_has_cursor(saved_page):
    pi = saved_page["page_info"]
    assert "end_cursor" in pi and "has_next_page" in pi


# ── normalize:node → 統一 dict ───────────────────────────────────────

def test_normalize_extracts_core_fields(saved_page):
    node = saved_page["edges"][0]["node"]
    norm = transform.normalize(node)
    assert norm["id"]                          # 貼文 id 非空
    assert norm["url"].startswith("http")      # 原文連結
    assert isinstance(norm["text"], str)       # 內文(可空)
    assert "author" in norm                    # 存貼文的人
    assert "category" in norm


def test_normalize_all_edges_have_id_and_url(saved_page):
    for edge in saved_page["edges"]:
        norm = transform.normalize(edge["node"])
        assert norm["id"], "every saved item must have an id"
        assert norm["url"], "every saved item must have a url"


def test_normalize_id_is_stable_dedupe_key(saved_page):
    # 同一 node normalize 兩次 → 同 id(dedupe 可靠)
    node = saved_page["edges"][0]["node"]
    assert transform.normalize(node)["id"] == transform.normalize(node)["id"]


# ── to_markdown:normalize → frontmatter + body ───────────────────────

def test_to_markdown_has_frontmatter(saved_page):
    norm = transform.normalize(saved_page["edges"][0]["node"])
    md = transform.to_markdown(norm)
    assert md.startswith("---\n")
    assert "source: facebook" in md
    assert "url:" in md and "tags:" in md
    assert "- inbox" in md                     # inbox tag 先行(之後分類)


def test_to_markdown_body_has_permalink(saved_page):
    norm = transform.normalize(saved_page["edges"][0]["node"])
    md = transform.to_markdown(norm)
    assert norm["url"] in md                   # 原文連結在內文


def test_to_markdown_escapes_yaml(saved_page):
    # 內文含冒號/引號不該炸 YAML
    norm = transform.normalize(saved_page["edges"][0]["node"])
    norm["author"] = 'has: colon "and quote"'
    md = transform.to_markdown(norm)
    assert "author:" in md                     # 不炸,能產出


# ── slug/檔名:安全 ───────────────────────────────────────────────────

def test_filename_is_safe(saved_page):
    norm = transform.normalize(saved_page["edges"][0]["node"])
    fname = transform.filename_for(norm)
    assert fname.endswith(".md")
    for bad in ("/", "\\", ":", "*", "?", '"', "<", ">", "|"):
        assert bad not in fname
