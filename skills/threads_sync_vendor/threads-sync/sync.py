"""Orchestrator / entrypoint: crawl saved posts and write them to the vault.

Phase 1: full dump. Opens the saved page, paginates to the end, normalizes each
post, and writes one .md per post into the vault. Records each post in SQLite and
persists the pagination cursor after every page so an interrupted crawl resumes
from where it stopped (crash / login expiry / block).

    uv run python threads-sync/sync.py

Media (images/video) are referenced by remote CDN URL for now; Phase 3 downloads
them locally. Requires an authenticated session — run import_session.py first.
"""

from __future__ import annotations

import re

import browser
import config
import store
import transform


def _slugify(text: str, fallback: str) -> str:
    """Build a filesystem-safe filename stem from post text, capped in length."""
    stem = text.strip().splitlines()[0] if text.strip() else ""
    stem = re.sub(r"[^\w\u4e00-\u9fff \-]", "", stem)  # keep word chars + CJK
    stem = re.sub(r"\s+", " ", stem).strip()[:60]
    return stem or fallback


def _write_markdown(norm: dict) -> str:
    """Write one post's .md into the vault. Returns the relative md path."""
    post_id = norm["post_id"]
    slug = _slugify(norm["text"], fallback=post_id)
    filename = f"{slug} ({post_id}).md"
    md_path = config.VAULT_PATH / filename
    md_path.write_text(transform.to_markdown(norm), encoding="utf-8")
    return filename


def _looks_logged_in(url: str) -> bool:
    return "threads.com" in url and "login" not in url and "instagram.com" not in url


def run() -> int:
    """Run one full crawl. Returns process exit code (0 ok, 1 problem)."""
    config.ensure_dirs()
    store.init_db()

    new_count = 0
    status = "ok"

    with store.connect() as conn, browser.persistent_context() as context:
        run_id = store.start_run(conn)
        page = context.pages[0] if context.pages else context.new_page()

        print(f"Opening saved page: {config.SAVED_URL}")
        try:
            page.goto(config.SAVED_URL, wait_until="domcontentloaded", timeout=30_000)
        except Exception as exc:
            print(f"  (navigation issue: {exc})")

        if not _looks_logged_in(page.url):
            print(f"\nERROR: not authenticated (landed on {page.url.split('?')[0]}).")
            print("Run: uv run python threads-sync/import_session.py cookies.json")
            store.finish_run(conn, run_id, new_count=0, status="login_expired")
            return 1

        print("Crawling saved posts (scrolling to paginate)...\n")
        try:
            for saved in browser.iter_saved_pages(page):
                edges = saved.get("edges") or []
                page_info = saved.get("page_info") or {}

                for edge in edges:
                    node = edge.get("node") or {}
                    for item in node.get("thread_items") or []:
                        post = item.get("post") or {}
                        if not post.get("pk"):
                            continue
                        norm = transform.normalize(post)
                        post_id = norm["post_id"]

                        if store.is_known(conn, post_id):
                            # Backfill thread_len on the pre-existing 780 so the
                            # thread pass can find them, without rewriting the .md.
                            store.set_thread_len(conn, post_id, norm["thread_len"])
                            continue

                        md_path = _write_markdown(norm)
                        store.add_post(
                            conn,
                            post_id=post_id,
                            author=norm["author"],
                            url=norm["url"],
                            md_path=md_path,
                            thread_len=norm["thread_len"],
                        )
                        new_count += 1
                        flag = f" [thread x{norm['thread_len']}]" if norm["thread_len"] > 1 else ""
                        print(f"  + [{new_count}] @{norm['author']}: {md_path}{flag}")

                # Persist cursor after each page so an interrupt can resume.
                cursor = page_info.get("end_cursor")
                store.save_cursor(conn, cursor)
                conn.commit()

                if not page_info.get("has_next_page", False):
                    store.clear_cursor(conn)
                    print("\nReached the end of saved posts (has_next_page=False).")
                    break
        except Exception as exc:
            status = "error"
            print(f"\nERROR during crawl: {exc}")

        store.finish_run(conn, run_id, new_count=new_count, status=status)

    print("\n" + "=" * 60)
    print(f"Done. New posts written: {new_count}. Status: {status}")
    print(f"Vault: {config.VAULT_PATH}")
    print("=" * 60)
    return 0 if status == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(run())
