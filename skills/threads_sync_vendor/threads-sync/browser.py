"""Playwright persistent session + GraphQL response capture.

The persistent context keeps the login session under config.USER_DATA_DIR so the
first manual login is reused on later runs. We capture GraphQL *responses* (not
the DOM) via a `response` event hook; callers decide what to do with each JSON
payload.
"""

from __future__ import annotations

import json
import random
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

import config
from playwright.sync_api import BrowserContext, Page, Response, sync_playwright

# Playwright accepts only these sameSite values; map everything else here.
_SAMESITE_MAP = {
    "no_restriction": "None",
    "none": "None",
    "unspecified": "Lax",
    "lax": "Lax",
    "strict": "Strict",
}

# Saved-posts data comes through POST /graphql/query (verified in Phase 0).
# NOT /api/graphql — that returns the anti-scripting wait screen.
GRAPHQL_URL_MARKERS = ("/graphql/query",)

# A saved-posts GraphQL response is identified by this nested key.
SAVED_MEDIA_PATH = ("data", "xdt_text_app_viewer", "saved_media")


def is_graphql_response(response: Response) -> bool:
    url = response.url
    return any(marker in url for marker in GRAPHQL_URL_MARKERS)


def extract_saved_media(payload: dict) -> dict | None:
    """Return the saved_media block if this JSON is a saved-posts response, else None."""
    node: object = payload
    for key in SAVED_MEDIA_PATH:
        if not isinstance(node, dict):
            return None
        node = node.get(key)
    return node if isinstance(node, dict) else None


@contextmanager
def persistent_context() -> Iterator[BrowserContext]:
    """Launch a persistent Chromium context using the saved session.

    Headed vs headless is controlled by config.HEADLESS. The user data dir is
    fixed so login survives across runs.
    """
    config.ensure_dirs()
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(config.USER_DATA_DIR),
            headless=config.HEADLESS,
            viewport={"width": 1280, "height": 900},
        )
        try:
            yield context
        finally:
            context.close()


def attach_graphql_capture(
    context: BrowserContext,
    on_payload: Callable[[Response], None],
) -> None:
    """Register a handler that fires for every GraphQL response.

    on_payload receives the raw Response; it is responsible for reading the body
    (response.json() / response.text()) and handling parse failures. Keep the
    handler cheap and defensive — it runs on Playwright's event loop.
    """

    def _handler(response: Response) -> None:
        if is_graphql_response(response):
            on_payload(response)

    context.on("response", _handler)


def attach_response_capture(
    context: BrowserContext,
    on_payload: Callable[[Response], None],
) -> None:
    """Register a handler that fires for EVERY response, no URL filtering.

    Used by the Phase 0 probe to discover which endpoints actually carry the
    saved-posts data, since the exact GraphQL path is still unknown. on_payload
    decides what to keep. Keep the handler cheap and defensive.
    """
    context.on("response", on_payload)


def iter_saved_pages(page: Page) -> Iterator[dict]:
    """Yield each saved_media block from the saved page, scrolling to paginate.

    Threads loads saved posts via POST /graphql/query as you scroll. We capture
    those responses into a queue and drain them, scrolling until a response reports
    has_next_page=False (or the safety cap MAX_SCROLLS is hit).

    Each yielded dict is a saved_media block:
      {"edges": [...], "page_info": {"end_cursor": ..., "has_next_page": bool}}

    The caller reads edges[].node.thread_items[].post. Scroll delay is jittered
    (config.SCROLL_DELAY + up to SCROLL_JITTER) to stay low-key.
    """
    pending: list[dict] = []

    def _collect(response: Response) -> None:
        if not is_graphql_response(response):
            return
        try:
            payload = response.json()
        except Exception:
            return
        saved = extract_saved_media(payload)
        if saved is not None:
            pending.append(saved)

    page.on("response", _collect)
    try:
        # The initial saved-tab load fires the first response; give it a moment.
        time.sleep(config.SCROLL_DELAY)

        scrolls = 0
        done = False
        while not done and scrolls < config.MAX_SCROLLS:
            # Drain everything captured so far.
            while pending:
                saved = pending.pop(0)
                yield saved
                page_info = saved.get("page_info") or {}
                if not page_info.get("has_next_page", False):
                    done = True

            if done:
                break

            # Scroll to trigger the next page, then wait (jittered) for responses.
            page.mouse.wheel(0, 3000)
            scrolls += 1
            delay = config.SCROLL_DELAY + random.uniform(0, config.SCROLL_JITTER)
            time.sleep(delay)

        # Drain any trailing responses that arrived after the last scroll.
        while pending:
            yield pending.pop(0)
    finally:
        page.remove_listener("response", _collect)


def fetch_post_html(page: Page, url: str) -> str:
    """Open a post detail page and return its fully rendered HTML.

    The author's self-thread continuation posts are server-side rendered into
    inline <script type="application/json"> blobs (verified in Phase 0), so the
    HTML is where they live — no extra GraphQL call carries them. Waits a jittered
    delay after load to let the inline data settle.
    """
    page.goto(url, wait_until="domcontentloaded", timeout=30_000)
    time.sleep(config.SCROLL_DELAY + random.uniform(0, config.SCROLL_JITTER))
    return page.content()


def _normalize_cookie(raw: dict) -> dict | None:
    """Convert one Cookie-Editor / storage_state cookie dict to add_cookies shape.

    Returns None for cookies that lack a name or value. Handles the field-name and
    sameSite differences between browser-extension exports and Playwright.
    """
    name = raw.get("name")
    value = raw.get("value")
    if not name or value is None:
        return None

    domain = raw.get("domain", "")
    path = raw.get("path", "/")

    cookie: dict = {
        "name": name,
        "value": value,
        "domain": domain,
        "path": path,
        "httpOnly": bool(raw.get("httpOnly", False)),
        "secure": bool(raw.get("secure", False)),
    }

    # sameSite: Cookie-Editor uses lower/underscored values; Playwright wants
    # exactly "Strict" | "Lax" | "None".
    raw_ss = str(raw.get("sameSite", "")).lower()
    cookie["sameSite"] = _SAMESITE_MAP.get(raw_ss, "Lax")
    # Playwright rejects sameSite=None unless secure is True.
    if cookie["sameSite"] == "None":
        cookie["secure"] = True

    # expires: Cookie-Editor uses "expirationDate" (float epoch seconds);
    # storage_state uses "expires". Session cookies omit it -> -1.
    expires = raw.get("expirationDate", raw.get("expires"))
    if expires is not None:
        cookie["expires"] = int(float(expires))

    return cookie


def cookies_from_editor_json(path: Path) -> list[dict]:
    """Load a Cookie-Editor / storage_state JSON export as add_cookies dicts.

    Accepts either a bare list of cookies (Cookie-Editor's default export) or a
    storage_state object with a top-level "cookies" key.
    """
    # utf-8-sig tolerates a UTF-8 BOM, which Windows editors / clipboard exports
    # from Cookie-Editor sometimes prepend.
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    raw_cookies = data["cookies"] if isinstance(data, dict) else data

    normalized: list[dict] = []
    for raw in raw_cookies:
        cookie = _normalize_cookie(raw)
        if cookie is not None:
            normalized.append(cookie)
    return normalized
