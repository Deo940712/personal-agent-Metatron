"""Probe: open one saved *self-thread* post and dump its GraphQL responses.

Phase 0 only scrolled the saved LIST, so continuation replies (the author's own
self-thread) were never loaded. To capture the author's follow-up posts we must
open the individual post page — that fires a different /graphql/query carrying the
full thread. This probe opens a known multi-post thread and dumps everything to
data/raw/thread/ so we can pin down the reply schema before coding it.

    uv run python threads-sync/probe_thread.py [code]

Default code is a saved post with self_thread_length=4 (verified in Phase 0).
Requires an authenticated session (run import_session.py first).
"""

from __future__ import annotations

import json
import sys
import time
from datetime import UTC, datetime

import browser
import config

# A saved post known to be a 4-post self-thread (from Phase 0 analysis).
DEFAULT_CODE = "DaMTOVhGTUZ"
DEFAULT_USERNAME = "kufutw"

THREAD_RAW_DIR = config.RAW_DIR / "thread"


def _timestamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")


def _make_dumper():
    counter = {"n": 0}

    def dump(response: browser.Response) -> None:
        if not browser.is_graphql_response(response):
            return
        try:
            payload = response.json()
        except Exception:
            return
        counter["n"] += 1
        idx = counter["n"]
        # Record which top-level data.* keys this response carries — that tells us
        # which endpoint holds the thread/reply data.
        data = payload.get("data") if isinstance(payload, dict) else None
        keys = sorted(data.keys()) if isinstance(data, dict) else []
        out = THREAD_RAW_DIR / f"{_timestamp()}_{idx:04d}.json"
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  [dump #{idx}] data keys={keys} -> {out.name}")

    return dump


def main() -> None:
    code = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_CODE
    THREAD_RAW_DIR.mkdir(parents=True, exist_ok=True)
    post_url = f"{config.BASE_URL}/@{DEFAULT_USERNAME}/post/{code}"

    print("=" * 70)
    print(f"Probing single-thread post: {post_url}")
    print(f"Dumps -> {THREAD_RAW_DIR}")
    print("=" * 70)

    with browser.persistent_context() as context:
        page = context.pages[0] if context.pages else context.new_page()
        page.on("response", _make_dumper())

        print(f"\nOpening {post_url}")
        try:
            page.goto(post_url, wait_until="domcontentloaded", timeout=30_000)
        except Exception as exc:
            print(f"  (navigation issue: {exc})")

        if "threads.com" not in page.url or "login" in page.url:
            print(f"\nERROR: not authenticated (at {page.url.split('?')[0]}).")
            print("Run: uv run python threads-sync/import_session.py cookies.json")
            return

        # Let the thread + replies load, and scroll a bit to trigger reply pages.
        time.sleep(config.SCROLL_DELAY)
        for _ in range(4):
            page.mouse.wheel(0, 2500)
            time.sleep(config.SCROLL_DELAY)

        print("\nDone. Waiting for trailing responses...")
        time.sleep(config.SCROLL_DELAY)

        # Dump the full rendered HTML too. The continuation-thread text is likely
        # server-side rendered into inline <script type="application/json"> blobs
        # rather than fetched via a later GraphQL call, so the HTML is where it
        # actually lives. Saved for offline analysis regardless of capture path.
        html_path = THREAD_RAW_DIR / f"page_{code}.html"
        try:
            html_path.write_text(page.content(), encoding="utf-8")
            print(f"Saved full page HTML -> {html_path.name} ({html_path.stat().st_size} bytes)")
        except Exception as exc:
            print(f"  (could not save HTML: {exc})")

    dumped = sorted(THREAD_RAW_DIR.glob("*.json"))
    print("\n" + "=" * 70)
    print(f"Captured {len(dumped)} GraphQL response(s) in {THREAD_RAW_DIR}")
    print("Next: inspect these + the page HTML to find the author's continuation posts.")
    print("=" * 70)


if __name__ == "__main__":
    main()
