"""sync orchestrator 測試:dedupe → transform → vault .md + cursor + sync_runs。

crawl 用注入的 timeline-iterator(不起真瀏覽器);也對真 fixture 做端到端。
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import store  # noqa: E402
import sync  # noqa: E402
import transform  # noqa: E402

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "likes_page_sample.json"


@pytest.fixture()
def env(tmp_path):
    db = tmp_path / "state.db"
    vault = tmp_path / "vault"
    store.init_db(db)
    return {"db": db, "vault": vault}


def _mock_pages(*timelines):
    def _iter(_page):
        yield from timelines
    return _iter


def _tweet_entry(tid, text="hi"):
    return {
        "entryId": f"tweet-{tid}",
        "content": {"itemContent": {"tweet_results": {"result": {
            "rest_id": tid,
            "legacy": {"full_text": text, "id_str": tid, "created_at": "now"},
            "core": {"user_results": {"result": {
                "core": {"screen_name": "bob", "name": "Bob"}}}},
        }}}},
    }


def _cursor_entry(val="C"):
    return {"entryId": "cursor-bottom-1", "content": {"value": val}}


def _timeline(entries):
    return {"instructions": [{"type": "TimelineAddEntries", "entries": entries}]}


# ── 基本:一頁 → .md + DB ────────────────────────────────────────────

def test_crawl_writes_md_and_db(env):
    tl = _timeline([_tweet_entry("t1"), _tweet_entry("t2"), _cursor_entry()])
    result = sync.crawl(db=env["db"], vault=env["vault"], _iter_pages=_mock_pages(tl))
    assert result["new_count"] == 2 and result["status"] == "ok"
    with store.connect(env["db"]) as conn:
        assert store.is_known(conn, "t1") and store.is_known(conn, "t2")
    assert len(list(env["vault"].glob("*.md"))) == 2


# ── dedupe ───────────────────────────────────────────────────────────

def test_second_run_dedupes(env):
    tl = _timeline([_tweet_entry("t1"), _cursor_entry()])
    sync.crawl(db=env["db"], vault=env["vault"], _iter_pages=_mock_pages(tl))
    result = sync.crawl(db=env["db"], vault=env["vault"],
                        _iter_pages=_mock_pages(_timeline([_tweet_entry("t1"), _cursor_entry()])))
    assert result["new_count"] == 0


# ── 多頁 + cursor ────────────────────────────────────────────────────

def test_multi_page(env):
    pages = _mock_pages(
        _timeline([_tweet_entry("t1"), _cursor_entry("C1")]),
        _timeline([_tweet_entry("t2"), _cursor_entry("C2")]))
    result = sync.crawl(db=env["db"], vault=env["vault"], _iter_pages=pages)
    assert result["new_count"] == 2


def test_cursor_persisted(env):
    tl = _timeline([_tweet_entry("t1"), _cursor_entry("RESUME")])
    sync.crawl(db=env["db"], vault=env["vault"], _iter_pages=_mock_pages(tl))
    with store.connect(env["db"]) as conn:
        assert store.get_cursor(conn) == "RESUME"


# ── sync_runs ────────────────────────────────────────────────────────

def test_sync_run_recorded(env):
    sync.crawl(db=env["db"], vault=env["vault"],
               _iter_pages=_mock_pages(_timeline([_tweet_entry("t1"), _cursor_entry()])))
    with store.connect(env["db"]) as conn:
        row = conn.execute(
            "SELECT status, new_count FROM sync_runs ORDER BY id DESC LIMIT 1").fetchone()
    assert row["status"] == "ok" and row["new_count"] == 1


# ── 端到端:真 fixture(7 真 tweets)→ .md ────────────────────────────

def test_real_fixture_end_to_end(env):
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    tl = transform.extract_timeline(payload)
    tweets = transform.extract_tweets(tl)
    result = sync.crawl(db=env["db"], vault=env["vault"], _iter_pages=_mock_pages(tl))
    assert result["new_count"] == len(tweets)
    mds = list(env["vault"].glob("*.md"))
    assert len(mds) == len(tweets)
    sample = mds[0].read_text(encoding="utf-8")
    assert "source: x" in sample and "- inbox" in sample
    assert "/status/" in sample
