"""非互動探勘執行器:session 已認證,跳過 phase0_probe 的手動登入 input。

複用 phase0_probe 的 dumper + config。headless 跑,直接開 saved 頁、攔所有 response、
dump schema。只觀察,不寫管線。
"""

from __future__ import annotations

import random
import sys
import time

import browser
import config
from phase0_probe import _looks_logged_in, _make_dumper, _safe_goto


def main() -> None:
    config.ensure_dirs()
    # 可傳 saved collection URL(如 /saved/?list_id=...);未傳用 config.SAVED_URL。
    target = sys.argv[1] if len(sys.argv) > 1 else config.SAVED_URL
    scrolls = int(sys.argv[2]) if len(sys.argv) > 2 else config.PROBE_SCROLLS
    print("=" * 70)
    print("FB Phase 0 probe (non-interactive; session already authenticated)")
    print(f"Target:    {target}")
    print(f"Raw dumps: {config.RAW_DIR}")
    print("=" * 70)

    with browser.persistent_context() as context:
        browser.attach_response_capture(context, _make_dumper())
        page = context.pages[0] if context.pages else context.new_page()

        print("\nLoading FB home to confirm session...")
        _safe_goto(page, config.BASE_URL)
        print(f"  home url: {page.url.split('?')[0]}  logged_in={_looks_logged_in(page.url)}")

        print(f"\nNavigating to saved collection: {target}")
        _safe_goto(page, target)
        print(f"  saved url: {page.url.split('?')[0]}  logged_in={_looks_logged_in(page.url)}")
        if not _looks_logged_in(page.url):
            print("  WARNING: bounced to login/checkpoint — captured data may be login pages.")

        time.sleep(config.SCROLL_DELAY)

        print(f"\nScrolling {scrolls} times...")
        for i in range(1, scrolls + 1):
            page.mouse.wheel(0, 3000)
            delay = config.SCROLL_DELAY + random.uniform(0, config.SCROLL_JITTER)
            print(f"  scroll {i}/{scrolls} (waiting {delay:.1f}s)")
            time.sleep(delay)

        print("\nWaiting for trailing responses...")
        time.sleep(config.SCROLL_DELAY)

    dumped = sorted(config.RAW_DIR.glob("*"))
    print("\n" + "=" * 70)
    print(f"Captured {len(dumped)} response file(s) in {config.RAW_DIR}")
    print("=" * 70)


if __name__ == "__main__":
    main()
