"""Backfill pass: merge each self-thread's author-continuation posts into its .md.

The saved-list crawl only captures the MAIN post. ~half of saved posts are
self-threads where the author continues across 2-4 chained posts; that
continuation text is server-side rendered into the post detail page's inline JSON,
not in the saved-list GraphQL. This pass:

  1. Finds posts flagged thread_len > 1 with thread_done = 0 (store.pending_threads).
  2. Opens each post's detail page and grabs its HTML (browser.fetch_post_html).
  3. Extracts the author's own continuation posts (transform.extract_author_thread).
  4. Rewrites that post's .md to include main + continuations, marks thread_done.

Run AFTER sync.py. Re-running sync.py first flags the pre-existing posts as
threads (sets thread_len) so this pass can pick them up. Idempotent: already-done
posts are skipped, and interrupted runs resume from remaining pending rows.

    uv run python threads-sync/sync_threads.py

Jittered delay between page fetches to stay low-key. Requires an authenticated
session (run import_session.py first).
"""

from __future__ import annotations

import random
import time

import browser
import config
import store
import transform


def _looks_logged_in(url: str) -> bool:
    return "threads.com" in url and "login" not in url and "instagram.com" not in url


def _rewrite_md_with_thread(row: store.sqlite3.Row, continuations: list[dict]) -> None:
    """Rewrite an existing post's .md to append the author's continuation posts.

    Re-reads nothing from Threads for the main post — the main post body is already
    in the .md. We rebuild the whole file from the main post's remaining metadata is
    not possible here, so instead we append a thread section to the existing file.
    """
    md_name = row["md_path"]
    if not md_name:
        return
    md_path = config.VAULT_PATH / md_name
    if not md_path.is_file():
        return

    existing = md_path.read_text(encoding="utf-8")

    # Build the continuation section (each author follow-up, separated by ---).
    cont_parts: list[str] = []
    for cont in continuations:
        body = transform._post_body_parts(cont)
        if body:
            cont_parts.append("---")
            cont_parts.extend(body)
    if not cont_parts:
        return

    section = "\n\n".join(cont_parts)

    # Insert the continuation BEFORE the trailing "原始貼文" link if present,
    # otherwise append at the end.
    marker = "[原始貼文]("
    idx = existing.rfind(marker)
    if idx != -1:
        # find start of that line
        line_start = existing.rfind("\n\n", 0, idx)
        head = existing[:line_start] if line_start != -1 else existing[:idx].rstrip()
        tail = existing[line_start:] if line_start != -1 else "\n\n" + existing[idx:]
        new_content = head + "\n\n" + section + tail
    else:
        new_content = existing.rstrip() + "\n\n" + section + "\n"

    md_path.write_text(new_content, encoding="utf-8")


def run() -> int:
    """Backfill author continuations for all pending self-threads. Returns exit code."""
    config.ensure_dirs()
    store.init_db()

    with store.connect() as conn:
        pending = store.pending_threads(conn)

    if not pending:
        print("No pending self-threads. Run sync.py first to flag them, or all done.")
        return 0

    print(f"Backfilling {len(pending)} self-thread(s) with author continuations.\n")

    done = 0
    status = "ok"
    with store.connect() as conn, browser.persistent_context() as context:
        page = context.pages[0] if context.pages else context.new_page()

        # Auth check via a cheap navigation.
        try:
            page.goto(config.BASE_URL, wait_until="domcontentloaded", timeout=30_000)
        except Exception as exc:
            print(f"  (navigation issue: {exc})")
        if not _looks_logged_in(page.url):
            print(f"\nERROR: not authenticated (at {page.url.split('?')[0]}).")
            print("Run: uv run python threads-sync/import_session.py cookies.json")
            return 1

        for row in pending:
            post_id = row["id"]
            url = row["url"]
            if not url:
                store.mark_thread_done(conn, post_id)
                conn.commit()
                continue

            try:
                html = browser.fetch_post_html(page, url)
            except Exception as exc:
                print(f"  ! {post_id}: fetch failed ({exc})")
                status = "error"
                continue

            # The main post's own thread_items[0] is included by extract_author_thread
            # (position 1); we want positions 2..N as continuations.
            all_author_posts = transform.extract_author_thread(html, _author_pk_from(html, post_id))
            continuations = [
                transform.normalize(p)
                for p in all_author_posts
                if str(p.get("pk")) != str(post_id)
            ]

            if continuations:
                _rewrite_md_with_thread(row, continuations)
                done += 1
                print(f"  + @{row['author']}: +{len(continuations)} author post(s)")
            else:
                print(f"  · @{row['author']}: no author continuations found (marking done)")

            store.mark_thread_done(conn, post_id)
            conn.commit()

            time.sleep(config.SCROLL_DELAY + random.uniform(0, config.SCROLL_JITTER))

    print("\n" + "=" * 60)
    print(f"Done. Threads backfilled: {done}/{len(pending)}. Status: {status}")
    print("=" * 60)
    return 0 if status == "ok" else 1


def _author_pk_from(html: str, main_post_id: str) -> str:
    """Find the main post's author pk from the page HTML.

    The main post (pk == main_post_id) appears in the inline JSON with its user.pk;
    we match continuations against that. Falls back to scanning all author posts.
    """
    # extract_author_thread needs the author pk, but we can derive it: parse the
    # inline JSON, find the post whose pk == main_post_id, read its user.pk.
    import json
    import re

    for blob in re.findall(
        r'<script type="application/json"[^>]*>(.*?)</script>', html, re.DOTALL
    ):
        if main_post_id not in blob:
            continue
        try:
            data = json.loads(blob)
        except json.JSONDecodeError:
            continue
        for post in transform._iter_posts_deep(data):
            if str(post.get("pk")) == str(main_post_id):
                return str((post.get("user") or {}).get("pk") or "")
    return ""


if __name__ == "__main__":
    raise SystemExit(run())
