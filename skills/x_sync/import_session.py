"""從真實 Chrome 匯入 X 登入 session 到 Playwright persistent context(一次性)。

同 threads/fb-sync:X 也建議用匯入 cookie 而非 Playwright 內登入。在你平常的 Chrome
登入 x.com,用 Cookie-Editor 匯出 JSON,再跑這個把 cookie 注入 config.USER_DATA_DIR。

    python import_session.py <cookies.json>

導出步驟(一次性):
  1. Chrome 開 https://x.com 並完整登入。
  2. 裝 Cookie-Editor 擴充。
  3. x.com 分頁 → Cookie-Editor → Export → Export as JSON → 存成 x_cookies.json。

關鍵 cookie:auth_token(登入 token)+ ct0(CSRF token,GraphQL 需要)。
X 對讀自己 bookmarks 較寬鬆,但仍低頻為上。
"""

from __future__ import annotations

import sys
from pathlib import Path

import browser
import config


def _is_relevant(cookie: dict) -> bool:
    domain = cookie.get("domain", "")
    return any(marker in domain for marker in config.RELEVANT_DOMAIN_MARKERS)


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python import_session.py <cookies.json>")
        print("See the module docstring for how to export X cookies from Chrome.")
        raise SystemExit(2)

    json_path = Path(sys.argv[1]).expanduser().resolve()
    if not json_path.is_file():
        print(f"ERROR: file not found: {json_path}")
        raise SystemExit(2)

    config.ensure_dirs()

    all_cookies = browser.cookies_from_editor_json(json_path)
    cookies = [c for c in all_cookies if _is_relevant(c)]

    print("=" * 70)
    print(f"Loaded {len(all_cookies)} cookie(s) from {json_path.name}")
    print(f"Keeping {len(cookies)} on X/Twitter domains.")

    found_keys = {c["name"] for c in cookies} & set(config.KEY_COOKIE_NAMES)
    missing = set(config.KEY_COOKIE_NAMES) - found_keys
    if missing:
        print(f"  WARNING: missing key cookie(s): {', '.join(sorted(missing))}")
        print("  The session may not authenticate. Export from a tab where you are")
        print("  actually logged in to x.com.")
    else:
        print(f"  Found key cookies: {', '.join(sorted(found_keys))}")
    print("=" * 70)

    if not cookies:
        print("Nothing to inject. Aborting.")
        raise SystemExit(1)

    with browser.persistent_context() as context:
        context.add_cookies(cookies)
        print(f"\nInjected {len(cookies)} cookie(s) into {config.USER_DATA_DIR}")

        page = context.pages[0] if context.pages else context.new_page()
        print("Verifying by loading X...")
        try:
            page.goto(config.BASE_URL, wait_until="domcontentloaded", timeout=30_000)
        except Exception as exc:      # noqa: BLE001 — 導覽問題不該中斷驗證
            print(f"  (navigation issue: {exc})")

        final_url = page.url
        logged_in = ("x.com" in final_url or "twitter.com" in final_url) \
            and "login" not in final_url and "/i/flow/" not in final_url
        print(f"  Landed on: {final_url.split('?')[0]}")
        if logged_in:
            print("\nSUCCESS: session looks authenticated.")
            print("Next: python run_probe.py")
        else:
            print("\nWARNING: bounced to login. Cookies may be stale/incomplete.")
            print("Re-export from Chrome while freshly logged in and try again.")


if __name__ == "__main__":
    main()
