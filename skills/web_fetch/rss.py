"""RSS/Atom 抓取器(part-008-slice-001)。

stdlib xml.etree 解析(零依賴)。網路取回原始 XML 由 opener 注入(mock 測試 /
不同 transport);解析層純函數、可測。壞 XML → 空列表(不炸 core)。
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Callable

from skills.web_fetch import FetchedEntry

# opener: (url) -> raw XML 字串。預設 urllib;測試注入 mock。
Opener = Callable[[str], str]


def _default_opener(url: str) -> str:
    import urllib.request
    with urllib.request.urlopen(url, timeout=15) as resp:   # noqa: S310 — allowlist 已驗
        return resp.read().decode("utf-8", errors="replace")


def _text(node, *paths: str) -> str:
    for path in paths:
        found = node.find(path)
        if found is not None and found.text:
            return found.text.strip()
    return ""


def parse_feed(xml_text: str) -> list[FetchedEntry]:
    """解析 RSS 2.0 或 Atom → FetchedEntry 列表。壞 XML → []。"""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []
    out: list[FetchedEntry] = []
    # RSS 2.0: channel/item
    for item in root.iter("item"):
        link = _text(item, "link")
        out.append(FetchedEntry(
            url=link,
            title=_text(item, "title"),
            author=_text(item, "author", "{http://purl.org/dc/elements/1.1/}creator"),
            body=_text(item, "description"),
            published=_text(item, "pubDate"),
        ))
    if out:
        return out
    # Atom: entry(命名空間)
    ns = "{http://www.w3.org/2005/Atom}"
    for entry in root.iter(f"{ns}entry"):
        link_node = entry.find(f"{ns}link")
        link = link_node.get("href", "") if link_node is not None else ""
        author = ""
        author_node = entry.find(f"{ns}author/{ns}name")
        if author_node is not None and author_node.text:
            author = author_node.text.strip()
        out.append(FetchedEntry(
            url=link,
            title=_text(entry, f"{ns}title"),
            author=author,
            body=_text(entry, f"{ns}summary", f"{ns}content"),
            published=_text(entry, f"{ns}updated", f"{ns}published"),
        ))
    return out


def fetch(url: str, opener: Opener | None = None) -> list[FetchedEntry]:
    """抓一個 RSS/Atom feed → entry 列表。網路失敗 → [](不炸 core)。"""
    op = opener or _default_opener
    try:
        raw = op(url)
    except Exception:                              # noqa: BLE001 — 抓取層容錯
        return []
    return parse_feed(raw)
