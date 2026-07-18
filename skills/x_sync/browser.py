"""Playwright persistent session + response capture(x-sync 探勘)。

平台無關邏輯沿用 threads/fb-sync:persistent context 保 session、攔 response、
cookie 匯入正規化。**不含 X 專屬 GraphQL schema**——探勘階段 schema 未知,
phase0_probe 用 discovery 模式攔所有 response 找出 bookmarks 端點。
"""

from __future__ import annotations

import json
import random
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

import config
import transform
from playwright.sync_api import BrowserContext, Page, Response, sync_playwright

# Likes 資料走 GraphQL /Likes 端點(phase 0 驗證)。多查詢共用 /i/api/graphql/,
# 靠 response 有無 user.result.timeline 的 TimelineAddEntries 區分。
LIKES_URL_MARKERS = ("/Likes", "/graphql/")

_SAMESITE_MAP = {
    "no_restriction": "None",
    "none": "None",
    "unspecified": "Lax",
    "lax": "Lax",
    "strict": "Strict",
}


@contextmanager
def persistent_context() -> Iterator[BrowserContext]:
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


def attach_response_capture(
    context: BrowserContext,
    on_payload: Callable[[Response], None],
) -> None:
    """對每個 response 觸發(無 URL 過濾)。探勘用:X bookmarks 端點路徑未知。"""
    context.on("response", on_payload)


def _normalize_cookie(raw: dict) -> dict | None:
    name = raw.get("name")
    value = raw.get("value")
    if not name or value is None:
        return None
    cookie: dict = {
        "name": name,
        "value": value,
        "domain": raw.get("domain", ""),
        "path": raw.get("path", "/"),
        "httpOnly": bool(raw.get("httpOnly", False)),
        "secure": bool(raw.get("secure", False)),
    }
    raw_ss = str(raw.get("sameSite", "")).lower()
    cookie["sameSite"] = _SAMESITE_MAP.get(raw_ss, "Lax")
    if cookie["sameSite"] == "None":
        cookie["secure"] = True
    expires = raw.get("expirationDate", raw.get("expires"))
    if expires is not None:
        cookie["expires"] = int(float(expires))
    return cookie


def cookies_from_editor_json(path: Path) -> list[dict]:
    """讀 Cookie-Editor / storage_state JSON 匯出成 add_cookies dicts。"""
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    raw_cookies = data["cookies"] if isinstance(data, dict) else data
    out: list[dict] = []
    for raw in raw_cookies:
        cookie = _normalize_cookie(raw)
        if cookie is not None:
            out.append(cookie)
    return out


# ── Likes timeline capture(實作階段)──────────────────────────────────

def is_graphql_response(response: Response) -> bool:
    return any(marker in response.url for marker in LIKES_URL_MARKERS)


def iter_like_pages(page: Page, navigate: Callable[[], None] | None = None
                    ) -> Iterator[dict]:
    """滾動 likes 頁,yield 每個含 tweets 的 timeline 塊。

    X 走 GraphQL /Likes 分頁載入(滾動時自動帶 cursor 發下一頁)。攔含
    user.result.timeline 的 response 進 queue,滾動直到某頁無新 tweet
    (只剩 cursor entry)或到 MAX_SCROLLS。每個 yield 是 timeline 塊
    ({instructions: [...]});呼叫者用 transform.extract_tweets 讀。

    navigate:先註冊 response 監聽,再呼叫它觸發 likes 頁載入——確保攔到初始頁
    (若在導航後才註冊,初始頁的 GraphQL 已載完會漏掉)。
    """
    pending: list[dict] = []

    def _collect(response: Response) -> None:
        if not is_graphql_response(response):
            return
        try:
            payload = response.json()
        except Exception:      # noqa: BLE001 — response 可能已消失/非 JSON
            return
        timeline = transform.extract_timeline(payload)
        if timeline is not None:
            pending.append(timeline)

    # 用 context 層監聽(而非 page.on):X 的 likes 導航可能在別的 frame/page 觸發
    # GraphQL,context.on 攔得到、page.on 會漏(診斷實證:context 層攔到 5 tweets,
    # page 層 0)。
    ctx = page.context
    ctx.on("response", _collect)
    try:
        if navigate is not None:
            navigate()                       # 監聽已就緒,才觸發 likes 載入
        time.sleep(config.SCROLL_DELAY)      # 等頁面框架載入

        # 關鍵:X 的 Likes GraphQL 是「第一次滾動才觸發」(初始 goto 不發)。
        # 順序必須是 先滾動→等待→drain,否則在資料到達前就累積 empty 退出。
        scrolls = 0
        empty_streak = 0
        while scrolls < config.MAX_SCROLLS:
            page.mouse.wheel(0, 3000)
            scrolls += 1
            time.sleep(config.SCROLL_DELAY + random.uniform(0, config.SCROLL_JITTER))

            drained_tweets = 0
            while pending:
                timeline = pending.pop(0)
                yield timeline
                drained_tweets += len(transform.extract_tweets(timeline))

            # 連續 3 次滾動都沒新 tweet → 視為到底(放寬,容忍載入延遲)
            if drained_tweets == 0:
                empty_streak += 1
                if empty_streak >= 3:
                    break
            else:
                empty_streak = 0
        while pending:
            yield pending.pop(0)
    finally:
        ctx.remove_listener("response", _collect)
