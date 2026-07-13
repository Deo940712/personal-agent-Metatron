"""Import a real-browser login session into Playwright's persistent context.

Meta's anti-scripting reCAPTCHA blocks logging in *inside* Playwright's Chromium.
Workaround: log in with your normal Chrome, export the threads.com + instagram.com
cookies to a JSON file (Cookie-Editor extension -> Export -> JSON), then run this
to inject them into the persistent context under config.USER_DATA_DIR. After this,
phase0_probe.py starts already authenticated.

    uv run python threads-sync/import_session.py path\\to\\cookies.json

Steps to produce the JSON (one-time, manual):
  1. In your normal Chrome, open https://www.threads.com and log in fully.
  2. Install the "Cookie-Editor" extension.
  3. On the Threads tab, open Cookie-Editor -> Export -> Export as JSON (copies to
     clipboard) -> paste into a file, e.g. cookies_threads.json.
  4. Repeat on an https://www.instagram.com tab (Threads uses IG SSO) and either
     save a second file or merge both JSON arrays into one file.
"""

from __future__ import annotations

import sys
from pathlib import Path

import browser
import config

# Cookies on these domains are what authenticate the Threads saved page.
RELEVANT_DOMAIN_MARKERS = ("threads.com", "threads.net", "instagram.com")

# If these are missing, the session almost certainly won't authenticate.
KEY_COOKIE_NAMES = ("sessionid", "ds_user_id")


def _is_relevant(cookie: dict) -> bool:
    domain = cookie.get("domain", "")
    return any(marker in domain for marker in RELEVANT_DOMAIN_MARKERS)


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: uv run python threads-sync/import_session.py <cookies.json>")
        print("See the module docstring for how to export cookies from Chrome.")
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
    print(f"Keeping {len(cookies)} on Threads/Instagram domains.")

    found_keys = {c["name"] for c in cookies} & set(KEY_COOKIE_NAMES)
    missing = set(KEY_COOKIE_NAMES) - found_keys
    if missing:
        print(f"  WARNING: missing key cookie(s): {', '.join(sorted(missing))}")
        print("  The session may not authenticate. Make sure you exported cookies")
        print("  from a tab where you are actually logged in.")
    else:
        print(f"  Found key cookies: {', '.join(sorted(found_keys))}")
    print("=" * 70)

    if not cookies:
        print("Nothing to inject. Aborting.")
        raise SystemExit(1)

    with browser.persistent_context() as context:
        context.add_cookies(cookies)
        print(f"\nInjected {len(cookies)} cookie(s) into {config.USER_DATA_DIR}")

        # Verify by loading Threads and checking we don't bounce to login.
        page = context.pages[0] if context.pages else context.new_page()
        print("Verifying by loading Threads...")
        try:
            page.goto(config.BASE_URL, wait_until="domcontentloaded", timeout=30_000)
        except Exception as exc:
            print(f"  (navigation issue: {exc})")

        final_url = page.url
        logged_in = "threads.com" in final_url and "login" not in final_url
        print(f"  Landed on: {final_url.split('?')[0]}")
        if logged_in:
            print("\nSUCCESS: session looks authenticated.")
            print("Next: uv run python threads-sync/phase0_probe.py")
            print("(In the probe, just press Enter at the login prompt — you're already in.)")
        else:
            print("\nWARNING: still bounced to login. Cookies may be stale/incomplete.")
            print("Re-export from Chrome while freshly logged in and try again.")


if __name__ == "__main__":
    main()
