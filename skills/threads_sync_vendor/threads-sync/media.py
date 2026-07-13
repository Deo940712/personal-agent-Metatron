"""Download remote images referenced in vault .md files to local attachments/.

Threads/Instagram CDN URLs (*.fbcdn.net, *.cdninstagram.com) expire within days
to weeks. Phase 3 downloads every `![image](https://...)` embed into
`vault/attachments/{post_id}_{n}.{ext}` and rewrites the .md to reference the
local relative path, so the vault stays complete offline.

Videos (`![video](...)`) are left as remote URLs by design (large, rarely needed).
"""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

# Match Markdown image embeds pointing at a remote http(s) URL. Videos and
# already-local paths are left alone.
_IMG_EMBED_RE = re.compile(r"!\[image\]\((https?://[^)]+)\)")

# A benign, browser-like UA. Meta CDN sometimes rejects Python defaults.
_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/149.0 Safari/537.36"
)

_TIMEOUT_SECS = 30


def _ext_for(url: str, content_type: str | None) -> str:
    """Pick a file extension: URL path first, then Content-Type, else .jpg."""
    path = urlparse(url).path
    m = re.search(r"\.(jpg|jpeg|png|gif|webp|heic)$", path, re.IGNORECASE)
    if m:
        return "." + m.group(1).lower()
    if content_type:
        ct = content_type.split(";")[0].strip().lower()
        if ct == "image/jpeg":
            return ".jpg"
        if ct == "image/png":
            return ".png"
        if ct == "image/gif":
            return ".gif"
        if ct == "image/webp":
            return ".webp"
    return ".jpg"


def download_image(url: str, dest_no_ext: Path) -> Path | None:
    """Fetch one image to `dest_no_ext.<ext>`. Returns the written path, or None on failure.

    Retries once on network error. Uses a browser-like User-Agent so the CDN
    doesn't reject the Python default. Skips if a file at any matching extension
    already exists (idempotent — re-runs don't re-download).
    """
    # Idempotent skip: if any file with this stem already exists, reuse it.
    for existing in dest_no_ext.parent.glob(dest_no_ext.name + ".*"):
        if existing.is_file() and existing.stat().st_size > 0:
            return existing

    req = Request(url, headers={"User-Agent": _UA, "Accept": "image/*,*/*;q=0.8"})
    last_error: Exception | None = None
    for _attempt in (1, 2):
        try:
            with urlopen(req, timeout=_TIMEOUT_SECS) as resp:
                content_type = resp.headers.get("Content-Type")
                data = resp.read()
            if not data:
                last_error = ValueError("empty response body")
                continue
            ext = _ext_for(url, content_type)
            out = dest_no_ext.with_suffix(ext)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(data)
            return out
        except Exception as exc:  # noqa: BLE001 - want broad catch for retry
            last_error = exc
    print(f"    ! download failed after 2 tries: {url[:80]} ({last_error})")
    return None


def _relpath_for_vault(attachment: Path, vault: Path) -> str:
    """Return the vault-relative POSIX path used inside a Markdown link."""
    rel = attachment.relative_to(vault)
    return rel.as_posix()


def rewrite_md_images(
    md_path: Path,
    *,
    post_id: str,
    vault: Path,
    attachments_dir: Path,
    on_download,
) -> tuple[int, int]:
    """Download every remote image in one .md, rewrite embeds to local paths.

    Returns (downloaded, total). `on_download(url)` is called BEFORE each fetch so
    the orchestrator can insert its jittered delay between requests.
    """
    text = md_path.read_text(encoding="utf-8")
    matches = list(_IMG_EMBED_RE.finditer(text))
    if not matches:
        return (0, 0)

    downloaded = 0
    # Rewrite in reverse so earlier match spans stay valid.
    new_text = text
    for idx, m in enumerate(reversed(matches), start=1):
        url = m.group(1)
        # Preserve original ordering in the filename.
        n = len(matches) - idx + 1
        stem = f"{post_id}_{n}"
        dest_no_ext = attachments_dir / stem
        on_download(url)
        saved = download_image(url, dest_no_ext)
        if saved is None:
            continue
        rel = _relpath_for_vault(saved, vault)
        new_text = new_text[: m.start()] + f"![image]({rel})" + new_text[m.end():]
        downloaded += 1

    if downloaded:
        md_path.write_text(new_text, encoding="utf-8")
    return (downloaded, len(matches))


def count_remote_images(md_path: Path) -> int:
    """How many `![image](http...)` embeds are still remote in this file."""
    try:
        text = md_path.read_text(encoding="utf-8")
    except OSError:
        return 0
    return len(_IMG_EMBED_RE.findall(text))
