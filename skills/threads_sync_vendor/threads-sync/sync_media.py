"""Orchestrator: download all remote images in the vault into attachments/.

Scans the SQLite `posts` table for rows with `media_done = 0`, downloads every
`![image](https://...)` URL in each post's .md to `vault/attachments/`, rewrites
the .md to reference the local relative path, and marks `media_done = 1`.

Videos are intentionally left as remote URLs (per user decision — attachments
budget). Idempotent: skips already-downloaded files, and rerun-safe via
media_done. Interruptions leave partial progress that resumes on next run.

    uv run python threads-sync/sync_media.py

Jittered 1-3s delay between individual downloads (per user decision — conservative
to avoid Meta CDN bot detection).
"""

from __future__ import annotations

import random
import time

import config
import media
import store


def run() -> int:
    config.ensure_dirs()
    store.init_db()

    with store.connect() as conn:
        rows = conn.execute(
            "SELECT id, author, md_path FROM posts "
            "WHERE media_done = 0 AND md_path IS NOT NULL"
        ).fetchall()

    if not rows:
        print("No posts pending media download. All done.")
        return 0

    # Pre-scan how many remote images exist across pending posts so the user
    # sees the real workload size (not the post count).
    total_remote = 0
    pending: list[tuple] = []
    for row in rows:
        md_path = config.VAULT_PATH / row["md_path"]
        if not md_path.is_file():
            continue
        n = media.count_remote_images(md_path)
        if n > 0:
            total_remote += n
            pending.append((row, md_path, n))

    if not pending:
        print(f"No remote images in {len(rows)} pending post(s). Marking done.")
        with store.connect() as conn:
            for row in rows:
                conn.execute("UPDATE posts SET media_done = 1 WHERE id = ?", (row["id"],))
            conn.commit()
        return 0

    print(f"Downloading {total_remote} remote image(s) across {len(pending)} post(s).")
    print(f"  attachments -> {config.ATTACHMENTS_PATH}")
    print(f"  jitter: {config.SCROLL_DELAY}s + up to {config.SCROLL_JITTER}s per image\n")

    def _delay(_url: str) -> None:
        time.sleep(config.SCROLL_DELAY + random.uniform(0, config.SCROLL_JITTER))

    done_posts = 0
    total_downloaded = 0
    total_failed = 0

    with store.connect() as conn:
        for row, md_path, _n_expected in pending:
            post_id = row["id"]
            got, total = media.rewrite_md_images(
                md_path,
                post_id=post_id,
                vault=config.VAULT_PATH,
                attachments_dir=config.ATTACHMENTS_PATH,
                on_download=_delay,
            )
            total_downloaded += got
            failed = total - got
            total_failed += failed
            done_posts += 1

            # Mark media_done only when every image landed (partial failures
            # remain pending so a re-run retries them).
            if failed == 0:
                conn.execute("UPDATE posts SET media_done = 1 WHERE id = ?", (post_id,))
                conn.commit()

            flag = "" if failed == 0 else f"  [!! {failed} failed]"
            print(f"  + [{done_posts}/{len(pending)}] @{row['author']}: {got}/{total} img{flag}")

    print("\n" + "=" * 60)
    print(f"Done. Downloaded {total_downloaded}/{total_remote} image(s).")
    if total_failed:
        print(f"  {total_failed} failed — those posts stay media_done=0 for retry on re-run.")
    print(f"Vault attachments: {config.ATTACHMENTS_PATH}")
    print("=" * 60)
    return 0 if total_failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(run())
