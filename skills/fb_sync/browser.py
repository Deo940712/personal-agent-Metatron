"""Playwright persistent session + response capture(fb-sync 探勘)。

大部分邏輯平台無關,直接沿用 threads-sync 的做法:persistent context 保 session、
攔 response、cookie 匯入正規化。**不含任何 FB 專屬 GraphQL schema**——探勘階段
schema 未知,phase0_probe 用 discovery 模式攔所有 response 找出真正的 saved 端點。
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

# saved 資料走 POST /api/graphql/(phase 0 驗證);多個 GraphQL 查詢共用此端點,
# 靠 response 內是否含 content_collection.collection_items 區分。
GRAPHQL_URL_MARKERS = ("/api/graphql/",)

# Playwright 只接受這些 sameSite 值;其餘映射到這裡。
_SAMESITE_MAP = {
    "no_restriction": "None",
    "none": "None",
    "unspecified": "Lax",
    "lax": "Lax",
    "strict": "Strict",
}


@contextmanager
def persistent_context() -> Iterator[BrowserContext]:
    """啟動帶 session 的 persistent Chromium context。headed/headless 由 config 控。"""
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
    """註冊一個對「每個 response」都觸發的 handler(無 URL 過濾)。

    探勘用:FB 的 saved 端點路徑未知,先攔全部,由 handler 決定留什麼。handler
    要 cheap + defensive(跑在 Playwright event loop)。
    """
    context.on("response", on_payload)


def _normalize_cookie(raw: dict) -> dict | None:
    """把一個 Cookie-Editor / storage_state cookie 轉成 add_cookies 形狀。"""
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
        cookie["secure"] = True    # Playwright 要求 sameSite=None 必須 secure

    expires = raw.get("expirationDate", raw.get("expires"))
    if expires is not None:
        cookie["expires"] = int(float(expires))

    return cookie


def cookies_from_editor_json(path: Path) -> list[dict]:
    """讀 Cookie-Editor / storage_state JSON 匯出成 add_cookies dicts。

    接受裸 cookie list(Cookie-Editor 預設)或帶 "cookies" 鍵的 storage_state。
    utf-8-sig 容忍 Windows 剪貼簿 export 有時前置的 BOM。
    """
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    raw_cookies = data["cookies"] if isinstance(data, dict) else data
    out: list[dict] = []
    for raw in raw_cookies:
        cookie = _normalize_cookie(raw)
        if cookie is not None:
            out.append(cookie)
    return out


# ── saved collection capture(實作階段)────────────────────────────────

def is_graphql_response(response: Response) -> bool:
    return any(marker in response.url for marker in GRAPHQL_URL_MARKERS)


def iter_saved_pages(page: Page) -> Iterator[dict]:
    """滾動 saved collection 頁,yield 每個 collection_items 塊。

    FB 走 POST /api/graphql/ 分頁載入。攔 response 進 queue,滾動直到
    has_next_page=False(或 MAX_SCROLLS)。每個 yield 是:
      {"edges": [...], "page_info": {"end_cursor": ..., "has_next_page": bool}}
    呼叫者讀 edges[].node。滾動延遲帶 jitter,低頻。
    """
    pending: list[dict] = []

    def _collect(response: Response) -> None:
        if not is_graphql_response(response):
            return
        try:
            payload = response.json()
        except Exception:      # noqa: BLE001 — response 可能已消失/非 JSON
            return
        coll = transform.extract_collection(payload)
        if coll is not None:
            pending.append(coll)

    page.on("response", _collect)
    try:
        time.sleep(config.SCROLL_DELAY)      # 初始載入
        scrolls = 0
        done = False
        while not done and scrolls < config.MAX_SCROLLS:
            while pending:
                coll = pending.pop(0)
                yield coll
                pi = coll.get("page_info") or {}
                if not pi.get("has_next_page", False):
                    done = True
            if done:
                break
            page.mouse.wheel(0, 3000)
            scrolls += 1
            time.sleep(config.SCROLL_DELAY + random.uniform(0, config.SCROLL_JITTER))
        while pending:
            yield pending.pop(0)
    finally:
        page.remove_listener("response", _collect)
