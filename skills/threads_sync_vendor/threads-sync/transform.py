"""Normalize raw Threads GraphQL posts and render them as Markdown.

Field paths are verified against real Phase 0 dumps — see AGENTS.md
"Saved-posts GraphQL schema". normalize() pulls a raw `post` object (from
edges[].node.thread_items[].post) into a flat dict; to_markdown() renders that
dict into a frontmatter + body string ready to write into the vault.

Phase 1 references remote CDN image URLs directly. Phase 3 will swap these for
downloaded local attachments/ paths (the CDN URLs expire).
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any

# media_type values observed in real dumps (AGENTS.md). 19 is unknown but still
# carries caption text; treat unknown types as text + best-effort media.
MEDIA_IMAGE = 1
MEDIA_VIDEO = 2
MEDIA_CAROUSEL = 8

# Inline JSON script blobs on a post detail page hold the full thread (verified
# against page_DaMTOVhGTUZ.html). The author's continuation posts live under
# result.data.data.edges[].node.thread_items[].post — we identify them by matching
# user.pk to the main author and requiring a self_thread position.
_JSON_SCRIPT_RE = re.compile(
    r'<script type="application/json"[^>]*>(.*?)</script>', re.DOTALL
)


def _iter_posts_deep(obj: object, depth: int = 0):
    """Yield every dict that looks like a Threads post (has pk + thread position)."""
    if depth > 40:
        return
    if isinstance(obj, dict):
        if "pk" in obj and "text_post_app_info" in obj and "caption" in obj:
            yield obj
        for value in obj.values():
            yield from _iter_posts_deep(value, depth + 1)
    elif isinstance(obj, list):
        for value in obj:
            yield from _iter_posts_deep(value, depth + 1)


def extract_author_thread(html: str, author_pk: str) -> list[dict]:
    """Extract the author's own self-thread posts from a post-detail page's HTML.

    Parses inline <script type="application/json"> blobs, collects every post
    authored by `author_pk` that carries a self_thread position, dedupes by pk, and
    returns them ordered by post_position_in_self_thread. Excludes other users'
    replies. Returns [] if nothing parseable is found.
    """
    by_position: dict[int, dict] = {}
    seen_pk: set[str] = set()

    for blob in _JSON_SCRIPT_RE.findall(html):
        if "post_position_in_self_thread" not in blob:
            continue
        try:
            data = json.loads(blob)
        except json.JSONDecodeError:
            continue
        for post in _iter_posts_deep(data):
            user_pk = str((post.get("user") or {}).get("pk") or "")
            if user_pk != str(author_pk):
                continue
            tpai = post.get("text_post_app_info") or {}
            sti = tpai.get("self_thread_info") or {}
            pos = sti.get("post_position_in_self_thread")
            if not isinstance(pos, int):
                continue
            pk = str(post.get("pk") or "")
            if pk in seen_pk:
                continue
            seen_pk.add(pk)
            by_position[pos] = post

    return [by_position[p] for p in sorted(by_position)]


def _best_image_url(image_versions2: dict | None) -> str | None:
    """Return the highest-resolution image URL from an image_versions2 block.

    candidates[] is largest-first, but pick explicitly by width*height to be safe.
    """
    if not image_versions2:
        return None
    candidates = image_versions2.get("candidates") or []
    if not candidates:
        return None
    best = max(
        candidates,
        key=lambda c: (c.get("width") or 0) * (c.get("height") or 0),
    )
    return best.get("url")


def _best_video_url(video_versions: list | None) -> str | None:
    if not video_versions:
        return None
    return video_versions[0].get("url")


def _extract_media(post: dict) -> list[dict]:
    """Flatten a post's media into a list of {type, url} dicts (order preserved).

    Handles single image, single video, and carousel (list of children, each with
    its own image/video). Unknown media types fall back to any image present.
    """
    media_type = post.get("media_type")

    if media_type == MEDIA_CAROUSEL and post.get("carousel_media"):
        items: list[dict] = []
        for child in post["carousel_media"]:
            video_url = _best_video_url(child.get("video_versions"))
            if video_url:
                items.append({"type": "video", "url": video_url})
                continue
            image_url = _best_image_url(child.get("image_versions2"))
            if image_url:
                items.append({"type": "image", "url": image_url})
        return items

    if media_type == MEDIA_VIDEO:
        video_url = _best_video_url(post.get("video_versions"))
        if video_url:
            return [{"type": "video", "url": video_url}]

    # Image, unknown type (e.g. 19), or video fallback: use the still image.
    image_url = _best_image_url(post.get("image_versions2"))
    if image_url:
        return [{"type": "image", "url": image_url}]
    return []


def build_body(post: dict) -> str:
    """Build the post body, rendering in-text links as clickable Markdown.

    Threads splits caption text into `text_post_app_info.text_fragments.fragments[]`:
    plaintext fragments are emitted as-is; link fragments become
    `[display_text](uri)` so URLs are clickable in Obsidian (caption.text alone
    can show truncated/label-only link text with no real URL).

    Falls back to the plain `caption.text` when no fragments are present.
    """
    tpai = post.get("text_post_app_info") or {}
    fragments = ((tpai.get("text_fragments") or {}).get("fragments")) or []

    if not fragments:
        return ((post.get("caption") or {}).get("text") or "").strip()

    parts: list[str] = []
    for frag in fragments:
        if frag.get("fragment_type") == "link":
            link = frag.get("link_fragment") or {}
            uri = link.get("uri") or ""
            display = link.get("display_text") or frag.get("plaintext") or uri
            parts.append(f"[{display}]({uri})" if uri else (frag.get("plaintext") or ""))
        else:
            parts.append(frag.get("plaintext") or "")
    return "".join(parts).strip()


def normalize(post: dict) -> dict[str, Any]:
    """Extract the fields we care about from a raw Threads `post` object."""
    pk = str(post.get("pk") or "")
    user = post.get("user") or {}
    username = user.get("username") or ""

    text = build_body(post)

    code = post.get("code") or ""
    url = f"https://www.threads.com/@{username}/post/{code}" if code and username else ""

    taken_at = post.get("taken_at")
    date_str = ""
    if isinstance(taken_at, int):
        date_str = datetime.fromtimestamp(taken_at).strftime("%Y-%m-%d %H:%M")

    tpai = post.get("text_post_app_info") or {}
    sti = tpai.get("self_thread_info") or {}
    thread_len = sti.get("self_thread_length")

    return {
        "post_id": pk,
        "author": username,
        "author_pk": str(user.get("pk") or ""),
        "full_name": user.get("full_name") or "",
        "is_verified": bool(user.get("is_verified")),
        "url": url,
        "code": code,
        "text": text,
        "likes": post.get("like_count") or 0,
        "taken_at": taken_at,
        "date": date_str,
        "media_type": post.get("media_type"),
        "media": _extract_media(post),
        "thread_len": thread_len if isinstance(thread_len, int) else 1,
        "detected_language": post.get("detected_language") or "",
        "accessibility_caption": post.get("accessibility_caption") or "",
    }


def _yaml_escape(value: str) -> str:
    """Quote a string for a YAML scalar, escaping embedded double quotes."""
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _post_body_parts(norm: dict[str, Any]) -> list[str]:
    """Body text + media embeds for a single normalized post (no frontmatter)."""
    parts = [norm["text"].strip()] if norm["text"].strip() else []
    # Phase 1: reference remote CDN URLs. Phase 3 swaps to local attachments/.
    for item in norm["media"]:
        parts.append(f"![{item['type']}]({item['url']})")
    return parts


def to_markdown(norm: dict[str, Any], continuations: list[dict[str, Any]] | None = None) -> str:
    """Render a normalized post as frontmatter + body Markdown.

    Frontmatter matches the plan's section 5 template. Every post gets the `inbox`
    tag first (re-classified later in Obsidian).

    `continuations` are the author's own self-thread follow-up posts (already
    normalized, in order). When present they are appended under the main post,
    separated by `---`, so the whole thread reads as one note.
    """
    fm_lines = ["---", "source: threads"]
    fm_lines.append(f"author: {_yaml_escape(norm['author'])}")
    if norm["url"]:
        fm_lines.append(f"url: {norm['url']}")
    if norm["date"]:
        fm_lines.append(f"date: {norm['date']}")
    fm_lines.append(f"likes: {norm['likes']}")
    fm_lines.append("tags:")
    fm_lines.append("  - threads")
    fm_lines.append("  - inbox")
    fm_lines.append("---")

    body_parts = _post_body_parts(norm)

    for cont in continuations or []:
        cont_parts = _post_body_parts(cont)
        if cont_parts:
            body_parts.append("---")
            body_parts.extend(cont_parts)

    if norm["url"]:
        body_parts.append(f"[原始貼文]({norm['url']})")

    return "\n".join(fm_lines) + "\n\n" + "\n\n".join(body_parts) + "\n"
