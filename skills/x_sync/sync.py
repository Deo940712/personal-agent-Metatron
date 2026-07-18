"""x-sync orchestrator:爬 likes timeline → dedupe → transform → vault .md。

1. 開 likes 頁,滾動攔 Likes GraphQL(browser.iter_like_pages)。
2. 每個 timeline 塊 → extract_tweets → 若 id 未知 → 寫 .md + 記 DB。
3. cursor 續傳:每頁存 cursor-bottom value;沒有更多 tweet 時停。
4. sync_runs 記錄 status(ok/error)。

crawl() 的 _iter_pages 可注入(測試 mock,正式用 browser.iter_like_pages)。
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable

import config
import store
import transform


def _write_note(vault: Path, norm: dict) -> str:
    vault.mkdir(parents=True, exist_ok=True)
    fname = transform.filename_for(norm)
    (vault / fname).write_text(transform.to_markdown(norm), encoding="utf-8")
    return fname


def _process_timeline(conn, vault: Path, timeline: dict) -> int:
    """處理一個 timeline 塊,回本頁新增數。"""
    new = 0
    for tweet in transform.extract_tweets(timeline):
        norm = transform.normalize(tweet)
        if not norm["id"] or store.is_known(conn, norm["id"]):
            continue
        fname = _write_note(vault, norm)
        store.add_post(conn, post_id=norm["id"], author=norm["author"],
                       url=norm["url"], md_path=fname)
        new += 1
    return new


def crawl(*, db: Path | None = None, vault: Path | None = None,
          _iter_pages: Callable | None = None, page=None,
          navigate: Callable | None = None) -> dict:
    """爬 likes timeline。回 {new_count, status}。

    _iter_pages(page, navigate) -> iterator of timeline blocks。測試注入 mock;
    正式用 browser.iter_like_pages。navigate 先註冊監聽再觸發 likes 載入
    (確保攔到初始頁)。
    """
    db = db or config.DB_PATH
    vault = vault or config.VAULT_PATH
    store.init_db(db)

    use_real = _iter_pages is None
    if use_real:
        from browser import iter_like_pages
        _iter_pages = iter_like_pages

    new_count = 0
    status = "ok"
    with store.connect(db) as conn:
        run_id = store.start_run(conn)
    try:
        pages = (_iter_pages(page, navigate) if use_real else _iter_pages(page))
        with store.connect(db) as conn:
            for timeline in pages:
                new_count += _process_timeline(conn, vault, timeline)
                cursor = transform.extract_cursor(timeline)
                if cursor:
                    store.save_cursor(conn, cursor)
    except Exception as e:      # noqa: BLE001 — 記 error,不讓 run 卡 running
        status = "error"
        print(f"crawl error: {type(e).__name__}: {e}", file=sys.stderr)
    finally:
        with store.connect(db) as conn:
            store.finish_run(conn, run_id, new_count=new_count, status=status)

    return {"new_count": new_count, "status": status}


def run() -> int:
    """正式入口:開瀏覽器爬 likes。需先 import_session。

    先確認 session,再把「開 likes 頁」包成 navigate callback 傳給 crawl——
    iter_like_pages 會先註冊 response 監聽,才呼叫 navigate,確保攔到初始頁
    (否則初始頁的 GraphQL 在監聽就緒前已載完 → 漏掉 → 0 posts 的根因)。
    """
    import time

    import browser
    with browser.persistent_context() as context:
        page = context.pages[0] if context.pages else context.new_page()
        # 先確認 session(不預先開 likes;那步交給 navigate callback)
        page.goto(config.BASE_URL, wait_until="domcontentloaded", timeout=30_000)
        time.sleep(config.SCROLL_DELAY)

        def _navigate() -> None:
            page.goto(config.BOOKMARKS_URL, wait_until="domcontentloaded", timeout=30_000)

        result = crawl(page=page, navigate=_navigate)
    print(f"Done. New posts written: {result['new_count']}. Status: {result['status']}")
    print(f"Vault: {config.VAULT_PATH}")
    return 0 if result["status"] == "ok" else 1


if __name__ == "__main__":
    sys.exit(run())
