"""FB saved node → normalize → Markdown(phase 0 schema 釘死)。

資料路徑(真 dump 驗證):
  data.content_collection.collection_items.edges[].node
  node.savable.id                       貼文 id(dedupe key)
  node.savable.savable_title.text       內文
  node.savable.savable_permalink        原文連結(fallback: node.savable.story.url)
  node.savable.savable_image.uri        圖片(fbcdn,會過期 → media 階段下載)
  node.savable.savable_default_category POST_WITH_PHOTO / POST / VIDEO ...
  node.saver.name                       存貼文的人(通常是你自己)
  collection_items.page_info            分頁 cursor
"""

from __future__ import annotations

import re
from datetime import UTC, datetime

# saved 資料塊的識別路徑。
_COLLECTION_PATH = ("data", "content_collection", "collection_items")


def extract_collection(payload: dict) -> dict | None:
    """回 collection_items 塊({edges, page_info})若這是 saved response,否則 None。"""
    node: object = payload
    for key in _COLLECTION_PATH:
        if not isinstance(node, dict):
            return None
        node = node.get(key)
    if isinstance(node, dict) and "edges" in node:
        return node
    return None


def _dig(obj: object, *keys: str) -> object:
    """安全巢狀取值;任一層缺失或非 dict → None。"""
    for k in keys:
        if not isinstance(obj, dict):
            return None
        obj = obj.get(k)
    return obj


def normalize(node: dict) -> dict:
    """一個 edge.node → 統一 dict。缺欄容錯(外部 schema)。"""
    savable = node.get("savable") or {}
    saver = node.get("saver") or {}

    post_id = savable.get("id") or node.get("id") or ""
    text = _dig(savable, "savable_title", "text") or ""
    url = (savable.get("savable_permalink")
           or _dig(savable, "story", "url") or "")
    image = _dig(savable, "savable_image", "uri")

    return {
        "id": str(post_id),
        "text": str(text),
        "url": str(url),
        "author": str(saver.get("name") or ""),
        "author_url": str(saver.get("profile_url") or saver.get("url") or ""),
        "category": str(savable.get("savable_default_category") or ""),
        "image_url": str(image) if image else "",
    }


def _yaml_str(value: str) -> str:
    """安全 YAML 純量:含特殊字元就雙引號 + escape。"""
    if value == "" or re.search(r'[:#"\'\[\]{}|>&*!%@`]', value) or value != value.strip():
        return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return value


def to_markdown(norm: dict) -> str:
    """normalize → frontmatter + body。每篇先掛 inbox tag(之後分類)。"""
    date = datetime.now(UTC).strftime("%Y-%m-%d %H:%M")
    title_line = norm["text"].splitlines()[0][:80] if norm["text"] else "(no text)"

    fm = [
        "---",
        "source: facebook",
        f"author: {_yaml_str(norm['author'])}",
        f"url: {_yaml_str(norm['url'])}",
        f"date: {date}",
        f"category: {_yaml_str(norm['category'])}",
        "tags:",
        "  - facebook",
        "  - inbox",
        "---",
        "",
    ]
    body = [
        f"# {title_line}",
        "",
        norm["text"] or "(no text captured)",
        "",
    ]
    if norm["image_url"]:
        body.append(f"![image]({norm['image_url']})  <!-- remote; media step downloads -->")
        body.append("")
    body.append(f"[原始貼文]({norm['url']})")
    body.append("")
    return "\n".join(fm) + "\n".join(body)


_SAFE = re.compile(r'[\\/:*?"<>|\n\r\t]+')


def filename_for(norm: dict) -> str:
    """安全 .md 檔名:內文前段 + id(去重穩定)。

    id 可能含冒號(如 'pageid:postid'),冒號是 Windows 非法檔名字元,必須清掉,
    否則作業系統會截斷/摺疊導致不同 id 碰撞成同檔名。
    """
    stem = norm["text"].strip()[:40] if norm["text"] else "fb-post"
    stem = _SAFE.sub(" ", stem).strip() or "fb-post"
    safe_id = _SAFE.sub("-", norm["id"]).strip("-") or "noid"
    return f"{stem} ({safe_id}).md"
