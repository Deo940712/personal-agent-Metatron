"""Phase 0 probe: manual login + dump raw GraphQL responses from the saved page.

Purpose (per threads-sync-plan.md section 6): pin down the ONE unknown before any
transform code — the GraphQL response schema, fields, and pagination cursor.

Run locally, headed. Log in manually in the opened window, pass any verification,
then press Enter. The script opens the saved page, scrolls a few times, and dumps
every captured GraphQL response as pretty JSON (or raw text) into config.RAW_DIR.

    uv run python threads-sync/phase0_probe.py

Nothing here writes to the vault or the DB — this phase only observes.
"""

from __future__ import annotations

import json
import random
import time
from datetime import UTC, datetime

import browser
import config
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Response
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

# How many scroll steps to sample during the probe. Small on purpose — we only
# need enough responses to understand the schema and cursor, not a full crawl.
PROBE_SCROLLS = 8

# URL fragments that mean we are still in the Instagram/Meta login/SSO flow,
# not on an authenticated Threads page.
LOGIN_URL_MARKERS = (
    "instagram.com/auth_platform",
    "instagram.com/accounts/login",
    "instagram.com/threads/sso",
    "/oauth/",
    "/login/",
    "recaptcha",
)


def _looks_logged_in(url: str) -> bool:
    """Heuristic: on a real Threads page and not bounced into the login/SSO flow."""
    return "threads.com" in url and not any(m in url for m in LOGIN_URL_MARKERS)


def _safe_goto(page, url: str) -> None:
    """Navigate, tolerating SSO redirects that interrupt the navigation.

    Meta's login flow fires cross-origin redirects mid-navigation, which Playwright
    surfaces as an error rather than a timeout. We swallow those so the probe keeps
    going — the redirect target is where the user needs to act anyway.
    """
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=30_000)
    except PlaywrightTimeoutError:
        print("  (navigation timeout — continuing; responses may still arrive)")
    except PlaywrightError as exc:
        if "interrupted by another navigation" in str(exc):
            print(f"  (redirected during navigation -> now at {page.url.split('?')[0]})")
        else:
            raise


def _timestamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")


# Substrings that mark a response as interesting enough to save the full body.
# The real Threads GraphQL path is still unknown, so we cast a wide net and let
# the manifest reveal which endpoint actually carries saved-posts data.
INTERESTING_URL_MARKERS = (
    "graphql",
    "/api/",
    "/oidc/",
    "bulk-route",
)


def _make_dumper():
    """Return an on_payload handler that logs EVERY response and dumps JSON bodies.

    Discovery mode: we don't know the real GraphQL endpoint yet, so this records
    every response URL to manifest.txt and saves the full body of anything that
    looks like an API/GraphQL call. Inspecting the manifest tells us which path to
    filter on for Phase 1.
    """
    counter = {"seen": 0, "saved": 0}
    manifest = config.RAW_DIR / "manifest.txt"
    manifest.write_text("", encoding="utf-8")  # reset per run

    def dump(response: Response) -> None:
        counter["seen"] += 1
        url = response.url
        try:
            ctype = response.headers.get("content-type", "")
        except Exception:
            ctype = ""

        # Always log the URL + method + content-type to the manifest.
        method = response.request.method
        with manifest.open("a", encoding="utf-8") as fh:
            fh.write(f"{method}\t{response.status}\t{ctype.split(';')[0]}\t{url}\n")

        url_lower = url.lower()
        looks_api = any(m in url_lower for m in INTERESTING_URL_MARKERS)
        looks_json = "json" in ctype.lower()
        if not (looks_api or looks_json):
            return

        try:
            body = response.text()
        except Exception:  # response may already be gone
            return

        # Skip tiny/empty bodies (pings, redirects) — no post data there.
        if len(body) < 50:
            return

        counter["saved"] += 1
        idx = counter["saved"]
        stamp = _timestamp()
        base = config.RAW_DIR / f"{stamp}_{idx:04d}"
        try:
            parsed = json.loads(body)
            base.with_suffix(".json").write_text(
                json.dumps(parsed, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            suffix = "json"
        except json.JSONDecodeError:
            base.with_suffix(".txt").write_text(body, encoding="utf-8")
            suffix = "txt"

        print(f"  [dump #{idx}] {method} {url.split('?')[0]} -> {base.name}.{suffix}")

    return dump


def main() -> None:
    config.ensure_dirs()
    print("=" * 70)
    print("Phase 0 probe — capturing GraphQL responses from the Threads saved page")
    print(f"Raw dumps go to: {config.RAW_DIR}")
    print(f"Session dir:     {config.USER_DATA_DIR}")
    print(f"Headless:        {config.HEADLESS}")
    print("=" * 70)

    with browser.persistent_context() as context:
        # Discovery mode: capture EVERY response (no URL filter) so we can find
        # the real saved-posts endpoint. See manifest.txt after the run.
        browser.attach_response_capture(context, _make_dumper())

        page = context.pages[0] if context.pages else context.new_page()

        print("\nOpening Threads. Log in manually if prompted (first run only).")
        _safe_goto(page, config.BASE_URL)

        while True:
            input(
                "\n>>> Log in / pass verification in the browser window, then press Enter "
                "here to continue...\n"
            )
            current = page.url
            if _looks_logged_in(current):
                break
            print(
                f"  Still on a login/SSO page ({current.split('?')[0]}).\n"
                "  Finish logging in (incl. any reCAPTCHA/2FA) until you see the Threads\n"
                "  home or your profile, then press Enter again."
            )

        print(f"\nNavigating to saved page: {config.SAVED_URL}")
        _safe_goto(page, config.SAVED_URL)

        if not _looks_logged_in(page.url):
            print(
                "\n  WARNING: saved-page navigation bounced to login "
                f"({page.url.split('?')[0]}).\n"
                "  Session may not be fully authenticated. Captured responses (if any)\n"
                "  may be login pages, not saved posts."
            )

        # Give the initial saved-tab GraphQL a moment to fire.
        time.sleep(config.SCROLL_DELAY)

        print(f"\nScrolling {PROBE_SCROLLS} times to trigger pagination...")
        for i in range(1, PROBE_SCROLLS + 1):
            page.mouse.wheel(0, 3000)
            delay = config.SCROLL_DELAY + random.uniform(0, config.SCROLL_JITTER)
            print(f"  scroll {i}/{PROBE_SCROLLS} (waiting {delay:.1f}s)")
            time.sleep(delay)

        print("\nDone scrolling. Waiting a moment for trailing responses...")
        time.sleep(config.SCROLL_DELAY)

    dumped = sorted(config.RAW_DIR.glob("*"))
    print("\n" + "=" * 70)
    print(f"Captured {len(dumped)} response file(s) in {config.RAW_DIR}")
    print("Next: inspect these to identify post_id, author, url, likes, and the")
    print("pagination cursor. That schema drives transform.py in Phase 1.")
    print("=" * 70)


if __name__ == "__main__":
    main()
