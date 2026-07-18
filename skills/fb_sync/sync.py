"""fb-sync orchestrator:爬 saved collection → dedupe → transform → vault .md。

1. 開 saved collection 頁,滾動攔 GraphQL(browser.iter_saved_pages)。
2. 每個 edge.node → normalize → 若 id 未知 → 寫 .md + 記 DB。
3. cursor 續傳:每頁存 end_cursor;全部跑完(has_next_page=False)清 cursor。
4. sync_runs 記錄 status(ok/error)。

crawl() 的 _iter_pages 可注入(測試用 mock,正式用 browser.iter_saved_pages)。
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable

import config
import store
import transform


def _write_note(vault: Path, norm: dict) -> str:
    """寫一篇 .md,回相對檔名。"""
    vault.mkdir(parents=True, exist_ok=True)
    fname = transform.filename_for(norm)
    (vault / fname).write_text(transform.to_markdown(norm), encoding="utf-8")
    return fname


def _process_page(conn, vault: Path, coll: dict) -> int:
    """處理一個 collection 塊,回本頁新增數。"""
    new = 0
    for edge in coll.get("edges", []):
        node = edge.get("node") or {}
        norm = transform.normalize(node)
        if not norm["id"] or store.is_known(conn, norm["id"]):
            continue
        fname = _write_note(vault, norm)
        store.add_post(conn, post_id=norm["id"], author=norm["author"],
                       url=norm["url"], md_path=fname)
        new += 1
    return new


def crawl(*, db: Path | None = None, vault: Path | None = None,
          _iter_pages: Callable | None = None, page=None) -> dict:
    """爬 saved collection。回 {new_count, status}。

    _iter_pages(page) -> iterator of collection blocks。測試注入 mock;正式傳
    browser.iter_saved_pages。
    """
    db = db or config.DB_PATH
    vault = vault or config.VAULT_PATH
    store.init_db(db)

    if _iter_pages is None:
        from browser import iter_saved_pages
        _iter_pages = iter_saved_pages

    new_count = 0
    status = "ok"
    with store.connect(db) as conn:
        run_id = store.start_run(conn)
    try:
        with store.connect(db) as conn:
            for coll in _iter_pages(page):
                new_count += _process_page(conn, vault, coll)
                pi = coll.get("page_info") or {}
                cursor = pi.get("end_cursor")
                if pi.get("has_next_page", False):
                    store.save_cursor(conn, cursor)     # 續傳點
                else:
                    store.clear_cursor(conn)            # 全部跑完
    except Exception as e:      # noqa: BLE001 — 記 error status,不讓 run 卡 running
        status = "error"
        print(f"crawl error: {type(e).__name__}: {e}", file=sys.stderr)
    finally:
        with store.connect(db) as conn:
            store.finish_run(conn, run_id, new_count=new_count, status=status)

    return {"new_count": new_count, "status": status}


def run() -> int:
    """正式入口:開瀏覽器爬 saved collection。需先 import_session。

    對齊探勘成功流程:先載 BASE_URL 確認 session,再開 collection URL,讓
    iter_saved_pages 滾動觸發 content_collection GraphQL。
    """
    import time

    import browser
    with browser.persistent_context() as context:
        page = context.pages[0] if context.pages else context.new_page()
        # 1. 先確認 session(避免直接開 collection 時尚未認證)
        page.goto(config.BASE_URL, wait_until="domcontentloaded", timeout=30_000)
        time.sleep(config.SCROLL_DELAY)
        # 2. 開 saved collection 入口
        page.goto(config.SAVED_URL, wait_until="domcontentloaded", timeout=30_000)
        time.sleep(config.SCROLL_DELAY)
        result = crawl(page=page)
    print(f"Done. New posts written: {result['new_count']}. Status: {result['status']}")
    print(f"Vault: {config.VAULT_PATH}")
    return 0 if result["status"] == "ok" else 1


if __name__ == "__main__":
    sys.exit(run())
