"""transform 測試:X likes tweet → normalize → Markdown。用真探勘 dump 當 fixture。

X likes schema(phase 0 釘死,真 dump 驗證):
  data.user.result.timeline.timeline.instructions[]  (type=TimelineAddEntries)
    → entries[]  (entryId=tweet-<id> / cursor-bottom-...)
    → content.itemContent.tweet_results.result
      rest_id                                    tweet id(dedupe key)
      legacy.full_text                           內文
      legacy.created_at                          時間
      legacy.extended_entities.media[]           圖片/影片
      core.user_results.result.legacy.screen_name/name  作者
    → cursor-bottom entry.content.value          分頁
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import transform  # noqa: E402

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "likes_page_sample.json"


@pytest.fixture()
def timeline() -> dict:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return transform.extract_timeline(payload)


# ── extract_timeline:找到 likes 資料塊 ───────────────────────────────

def test_extract_timeline_finds_instructions(timeline):
    assert "instructions" in timeline


def test_extract_timeline_none_for_non_likes():
    assert transform.extract_timeline({"data": {"explore_sidebar": {}}}) is None


# ── extract_tweets:entries → tweet result list ──────────────────────

def test_extract_tweets_returns_real_tweets(timeline):
    tweets = transform.extract_tweets(timeline)
    assert len(tweets) >= 1
    for t in tweets:
        assert "rest_id" in t or "legacy" in t


def test_extract_cursor(timeline):
    cursor = transform.extract_cursor(timeline)
    # 有內容的頁通常有 cursor(可能 None 若最後一頁)
    assert cursor is None or isinstance(cursor, str)


# ── normalize:tweet result → 統一 dict ──────────────────────────────

def test_normalize_core_fields(timeline):
    tweet = transform.extract_tweets(timeline)[0]
    norm = transform.normalize(tweet)
    assert norm["id"]                          # tweet id 非空
    assert isinstance(norm["text"], str)
    assert norm["url"].startswith("http")      # 建構的 x.com 連結
    assert "author" in norm


def test_normalize_all_tweets_have_id_and_url(timeline):
    for tweet in transform.extract_tweets(timeline):
        norm = transform.normalize(tweet)
        assert norm["id"], "every tweet must have an id"
        assert "/status/" in norm["url"], "url must be a tweet permalink"


def test_normalize_url_uses_author_and_id(timeline):
    tweet = transform.extract_tweets(timeline)[0]
    norm = transform.normalize(tweet)
    # x.com/<author>/status/<id>
    assert norm["id"] in norm["url"]


# ── to_markdown ──────────────────────────────────────────────────────

def test_to_markdown_frontmatter(timeline):
    norm = transform.normalize(transform.extract_tweets(timeline)[0])
    md = transform.to_markdown(norm)
    assert md.startswith("---\n")
    assert "source: x" in md
    assert "url:" in md and "- inbox" in md


def test_to_markdown_has_permalink(timeline):
    norm = transform.normalize(transform.extract_tweets(timeline)[0])
    md = transform.to_markdown(norm)
    assert norm["url"] in md


# ── filename 安全 ────────────────────────────────────────────────────

def test_filename_safe(timeline):
    norm = transform.normalize(transform.extract_tweets(timeline)[0])
    fname = transform.filename_for(norm)
    assert fname.endswith(".md")
    for bad in ("/", "\\", ":", "*", "?", '"', "<", ">", "|"):
        assert bad not in fname
