"""sync orchestrator 測試:dedupe → transform → vault .md + cursor + sync_runs。

crawl 用注入的 page-iterator(不起真瀏覽器);也對真 fixture 做端到端。
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import store  # noqa: E402
import sync  # noqa: E402
import transform  # noqa: E402

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "saved_page_sample.json"


@pytest.fixture()
def env(tmp_path):
    db = tmp_path / "state.db"
    vault = tmp_path / "vault"
    store.init_db(db)
    return {"db": db, "vault": vault}


def _mock_pages(*collections):
    """回一個 iter_saved_pages 替身:依序 yield 給定的 collection 塊。"""
    def _iter(_page):
        yield from collections
    return _iter


def _page(edges, has_next=False, cursor="C"):
    return {"edges": edges, "page_info": {"end_cursor": cursor, "has_next_page": has_next}}


def _edge(pid, text="hello", url="http://fb/p"):
    return {"node": {"savable": {"id": pid, "savable_title": {"text": text},
                                 "savable_permalink": url},
                     "saver": {"name": "me"}}}


# ── 基本:一頁 → 寫 .md + DB ─────────────────────────────────────────

def test_crawl_writes_md_and_db(env):
    pages = _mock_pages(_page([_edge("p1"), _edge("p2")]))
    result = sync.crawl(db=env["db"], vault=env["vault"], _iter_pages=pages)
    assert result["new_count"] == 2 and result["status"] == "ok"
    with store.connect(env["db"]) as conn:
        assert store.is_known(conn, "p1") and store.is_known(conn, "p2")
    mds = list(env["vault"].glob("*.md"))
    assert len(mds) == 2


# ── dedupe:第二次跑同資料 → 0 new ───────────────────────────────────

def test_second_run_dedupes(env):
    pages = _mock_pages(_page([_edge("p1")]))
    sync.crawl(db=env["db"], vault=env["vault"], _iter_pages=pages)
    result = sync.crawl(db=env["db"], vault=env["vault"],
                        _iter_pages=_mock_pages(_page([_edge("p1")])))
    assert result["new_count"] == 0            # 已知,不重寫


# ── 多頁 + 分頁 cursor 續傳 ──────────────────────────────────────────

def test_multi_page_and_cursor(env):
    pages = _mock_pages(
        _page([_edge("p1")], has_next=True, cursor="C1"),
        _page([_edge("p2")], has_next=False, cursor="C2"))
    result = sync.crawl(db=env["db"], vault=env["vault"], _iter_pages=pages)
    assert result["new_count"] == 2
    with store.connect(env["db"]) as conn:
        # 全部跑完 → cursor 清空(has_next_page=False)
        assert store.get_cursor(conn) is None


def test_cursor_persisted_on_interrupt(env):
    """中途頁(has_next=True)後 cursor 應被存(續傳點)。"""
    def _iter(_page):
        yield _page_dummy  # noqa: F821 — 觸發下方替換
    pages = _mock_pages(_page([_edge("p1")], has_next=True, cursor="RESUME_HERE"))
    # 只有一頁但 has_next=True(模擬被打斷)
    sync.crawl(db=env["db"], vault=env["vault"], _iter_pages=pages)
    with store.connect(env["db"]) as conn:
        assert store.get_cursor(conn) == "RESUME_HERE"


# ── sync_runs 記錄 ───────────────────────────────────────────────────

def test_sync_run_recorded(env):
    sync.crawl(db=env["db"], vault=env["vault"],
               _iter_pages=_mock_pages(_page([_edge("p1")])))
    with store.connect(env["db"]) as conn:
        row = conn.execute(
            "SELECT status, new_count FROM sync_runs ORDER BY id DESC LIMIT 1").fetchone()
    assert row["status"] == "ok" and row["new_count"] == 1


# ── 端到端:真 fixture → .md ─────────────────────────────────────────

def test_real_fixture_end_to_end(env):
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    coll = transform.extract_collection(payload)
    result = sync.crawl(db=env["db"], vault=env["vault"], _iter_pages=_mock_pages(coll))
    assert result["new_count"] == len(coll["edges"])
    mds = list(env["vault"].glob("*.md"))
    assert len(mds) == len(coll["edges"])
    # 抽一篇檢查格式
    sample = mds[0].read_text(encoding="utf-8")
    assert "source: facebook" in sample and "- inbox" in sample
