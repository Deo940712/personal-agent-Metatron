"""Phase 0 probe:登入 + dump facebook.com/saved 頁的所有 network response。

目的:釘死實作前唯一的未知——FB saved 的資料端點、response schema、分頁機制。
FB 的 saved 怎麼載入(GraphQL/REST/batch)完全未知,所以用 discovery 模式:攔每個
response、URL 記進 manifest.txt、看起來像 API/JSON 的存完整 body。看完 dump 才知道
要不要、能不能寫管線。

    python phase0_probe.py

本階段只觀察——不寫 vault、不寫 DB、不建管線。headed 手動登入。
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

# 還在 FB 登入流程(未認證)的 URL 標記。
LOGIN_URL_MARKERS = (
    "facebook.com/login",
    "facebook.com/checkpoint",
    "/recover/",
    "/two_step_verification",
    "recaptcha",
)

# 看起來像 API/資料端點的 URL 標記(存完整 body)。FB 真正的 saved 端點未知,
# 撒大網,靠 manifest 揭露哪個 path 帶 saved 資料。
INTERESTING_URL_MARKERS = (
    "graphql",
    "/api/",
    "/ajax/",
    "bulk-route",
)


def _looks_logged_in(url: str) -> bool:
    return "facebook.com" in url and not any(m in url for m in LOGIN_URL_MARKERS)


def _safe_goto(page, url: str) -> None:
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


def _make_dumper():
    """回一個 on_payload handler:記錄每個 response,存 API/JSON body。"""
    counter = {"seen": 0, "saved": 0}
    manifest = config.RAW_DIR / "manifest.txt"
    manifest.write_text("", encoding="utf-8")   # 每次 run 重置

    def dump(response: Response) -> None:
        counter["seen"] += 1
        url = response.url
        try:
            ctype = response.headers.get("content-type", "")
        except Exception:      # noqa: BLE001
            ctype = ""

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
        except Exception:      # noqa: BLE001 — response 可能已消失
            return

        if len(body) < 50:     # 跳過空/ping body
            return

        counter["saved"] += 1
        idx = counter["saved"]
        base = config.RAW_DIR / f"{_timestamp()}_{idx:04d}"
        try:
            parsed = json.loads(body)
            base.with_suffix(".json").write_text(
                json.dumps(parsed, ensure_ascii=False, indent=2), encoding="utf-8")
            suffix = "json"
        except json.JSONDecodeError:
            base.with_suffix(".txt").write_text(body, encoding="utf-8")
            suffix = "txt"

        print(f"  [dump #{idx}] {method} {url.split('?')[0]} -> {base.name}.{suffix}")

    return dump


def main() -> None:
    config.ensure_dirs()
    print("=" * 70)
    print("Phase 0 probe — capturing network responses from the FB saved page")
    print(f"Raw dumps go to: {config.RAW_DIR}")
    print(f"Session dir:     {config.USER_DATA_DIR}")
    print(f"Headless:        {config.HEADLESS}")
    print("=" * 70)

    with browser.persistent_context() as context:
        browser.attach_response_capture(context, _make_dumper())
        page = context.pages[0] if context.pages else context.new_page()

        print("\nOpening Facebook. Log in manually if prompted (first run only).")
        _safe_goto(page, config.BASE_URL)

        while True:
            input(
                "\n>>> Log in / pass verification in the browser window, then press "
                "Enter here to continue...\n")
            if _looks_logged_in(page.url):
                break
            print(
                f"  Still on a login/checkpoint page ({page.url.split('?')[0]}).\n"
                "  Finish logging in (incl. any 2FA/checkpoint) until you see your\n"
                "  Facebook feed, then press Enter again.")

        print(f"\nNavigating to saved page: {config.SAVED_URL}")
        _safe_goto(page, config.SAVED_URL)

        if not _looks_logged_in(page.url):
            print(
                "\n  WARNING: saved-page navigation bounced to login "
                f"({page.url.split('?')[0]}).\n"
                "  Session may not be fully authenticated.")

        time.sleep(config.SCROLL_DELAY)

        print(f"\nScrolling {config.PROBE_SCROLLS} times to trigger pagination...")
        for i in range(1, config.PROBE_SCROLLS + 1):
            page.mouse.wheel(0, 3000)
            delay = config.SCROLL_DELAY + random.uniform(0, config.SCROLL_JITTER)
            print(f"  scroll {i}/{config.PROBE_SCROLLS} (waiting {delay:.1f}s)")
            time.sleep(delay)

        print("\nDone scrolling. Waiting for trailing responses...")
        time.sleep(config.SCROLL_DELAY)

    dumped = sorted(config.RAW_DIR.glob("*"))
    print("\n" + "=" * 70)
    print(f"Captured {len(dumped)} response file(s) in {config.RAW_DIR}")
    print("Next: inspect manifest.txt + the .json dumps to find which endpoint")
    print("carries saved items, and identify id/author/url/date/media + the")
    print("pagination cursor. That schema decides whether/how to build the pipeline.")
    print("=" * 70)


if __name__ == "__main__":
    main()
