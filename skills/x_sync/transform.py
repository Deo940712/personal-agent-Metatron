"""X likes tweet → normalize → Markdown(phase 0 schema 釘死,真 dump 驗證)。

資料路徑:
  data.user.result.timeline.timeline.instructions[]  (或 timeline_v2)
    type=TimelineAddEntries → entries[]
      entryId=tweet-<id>   → content.itemContent.tweet_results.result
      entryId=cursor-bottom-... → content.value (分頁)

  tweet result:
    rest_id                                          tweet id(dedupe key)
    legacy.full_text                                 內文
    legacy.created_at                                時間
    legacy.extended_entities.media[].media_url_https 圖片
    core.user_results.result.legacy.screen_name/name 作者
"""

from __future__ import annotations

import re


def extract_timeline(payload: dict) -> dict | None:
    """回 likes timeline 塊({instructions})若這是 likes response,否則 None。"""
    user = _dig(payload, "data", "user", "result")
    if not isinstance(user, dict):
        return None
    for key in ("timeline", "timeline_v2"):
        tl = user.get(key)
        inner = _dig(tl, "timeline") if isinstance(tl, dict) else None
        if isinstance(inner, dict) and "instructions" in inner:
            return inner
    return None


def _dig(obj: object, *keys: str) -> object:
    for k in keys:
        if not isinstance(obj, dict):
            return None
        obj = obj.get(k)
    return obj


def extract_tweets(timeline: dict) -> list[dict]:
    """timeline → tweet result 列表(略過 cursor / 非 tweet entry)。"""
    out: list[dict] = []
    for instr in timeline.get("instructions", []):
        if instr.get("type") != "TimelineAddEntries":
            continue
        for entry in instr.get("entries", []):
            if not str(entry.get("entryId", "")).startswith("tweet-"):
                continue
            result = _dig(entry, "content", "itemContent", "tweet_results", "result")
            if isinstance(result, dict):
                out.append(result)
    return out


def extract_cursor(timeline: dict) -> str | None:
    """回 cursor-bottom 的 value(下一頁);無則 None。"""
    for instr in timeline.get("instructions", []):
        if instr.get("type") != "TimelineAddEntries":
            continue
        for entry in instr.get("entries", []):
            if str(entry.get("entryId", "")).startswith("cursor-bottom"):
                val = _dig(entry, "content", "value")
                if isinstance(val, str):
                    return val
    return None


def normalize(result: dict) -> dict:
    """一個 tweet result → 統一 dict。缺欄容錯。"""
    # 有些 result 是 TweetWithVisibilityResults 包一層 .tweet
    if result.get("__typename") == "TweetWithVisibilityResults":
        result = result.get("tweet", result)

    rest_id = str(result.get("rest_id") or _dig(result, "legacy", "id_str") or "")
    legacy = result.get("legacy") or {}
    text = legacy.get("full_text") or ""

    # 作者:新版 X 把 screen_name/name 放在 user_results.result.core(真 dump 校正);
    # 舊版在 .legacy。兩者都試。
    user_result = _dig(result, "core", "user_results", "result") or {}
    user_core = user_result.get("core") or {}
    user_legacy = user_result.get("legacy") or {}
    screen_name = user_core.get("screen_name") or user_legacy.get("screen_name") or ""
    author_name = (user_core.get("name") or user_legacy.get("name") or screen_name)

    url = (f"https://x.com/{screen_name}/status/{rest_id}"
           if screen_name and rest_id else "")

    ext = legacy.get("extended_entities") or legacy.get("entities") or {}
    images = [m.get("media_url_https") for m in ext.get("media", [])
              if m.get("media_url_https")]

    return {
        "id": rest_id,
        "text": str(text),
        "url": url,
        "author": str(author_name),
        "author_handle": str(screen_name),
        "created_at": str(legacy.get("created_at") or ""),
        "image_urls": images,
    }


def _yaml_str(value: str) -> str:
    if value == "" or re.search(r'[:#"\'\[\]{}|>&*!%@`]', value) or value != value.strip():
        return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return value


def to_markdown(norm: dict) -> str:
    title = norm["text"].splitlines()[0][:80] if norm["text"] else "(no text)"
    fm = [
        "---",
        "source: x",
        f"author: {_yaml_str(norm['author'])}",
        f"handle: {_yaml_str('@' + norm['author_handle'] if norm['author_handle'] else '')}",
        f"url: {_yaml_str(norm['url'])}",
        f"date: {_yaml_str(norm['created_at'])}",
        "tags:",
        "  - x",
        "  - inbox",
        "---",
        "",
    ]
    body = [f"# {title}", "", norm["text"] or "(no text captured)", ""]
    for img in norm["image_urls"]:
        body.append(f"![image]({img})  <!-- remote; media step downloads -->")
    if norm["image_urls"]:
        body.append("")
    body.append(f"[原始貼文]({norm['url']})")
    body.append("")
    return "\n".join(fm) + "\n".join(body)


_SAFE = re.compile(r'[\\/:*?"<>|\n\r\t]+')


def filename_for(norm: dict) -> str:
    stem = norm["text"].strip()[:40] if norm["text"] else "x-tweet"
    stem = _SAFE.sub(" ", stem).strip() or "x-tweet"
    safe_id = _SAFE.sub("-", norm["id"]).strip("-") or "noid"
    return f"{stem} ({safe_id}).md"
