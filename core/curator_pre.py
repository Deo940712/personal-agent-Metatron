"""curator 確定性前處理(part-004;ARCHITECTURE §6.5 的 State→curator 橋)。

非 LLM:掃 inbox tag 筆記 → 算 content_hash → 跨源去重 → 補齊 §5.2 欄位。
輸入是 sync skill 的產出(threads-sync frontmatter:source/author/url/date/
likes/tags;缺 id/source_id/captured_at/content_hash)。

去重策略(§8):URL 正規化相同 或 content_hash 相同 → 重複;保留較早的一篇,
重複篇標 tag=duplicate(不刪——append-only)。
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime
from pathlib import Path

from core import ltm

INBOX_TAG = "inbox"
DUPLICATE_TAG = "duplicate"


def content_hash(body: str) -> str:
    """內文 SHA-256 前 16 碼(§5.2)。正規化:去空白差異,避免同文不同排版漏判。"""
    normalized = re.sub(r"\s+", " ", body.strip())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


def normalize_url(url: str) -> str:
    """URL 正規化供跨源比對:去 query/fragment、去尾斜線、小寫 host。"""
    url = url.split("?")[0].split("#")[0].rstrip("/")
    m = re.match(r"(https?://)([^/]+)(.*)", url)
    if m:
        return f"{m.group(1)}{m.group(2).lower()}{m.group(3)}"
    return url


def _extract_source_id(fm: dict) -> str:
    """從 url 抽平台 post id;無 url 用 content_hash 代。"""
    url = fm.get("url", "")
    m = re.search(r"/post/([A-Za-z0-9_-]+)", url)
    if m:
        return m.group(1)
    return f"hash:{fm.get('content_hash', 'unknown')}"


def scan_inbox(vault: Path) -> list[dict]:
    """掃 vault 全部筆記,回傳帶 inbox tag 的:[{path, frontmatter, body}]。

    走檔案系統而非 registry——sync skill 的產出還沒進 registry(curator 才登記)。
    壞 frontmatter 跳過(ltm.read_note 回 None)。
    """
    out = []
    for md in sorted(vault.rglob("*.md")):
        rel = md.relative_to(vault).as_posix()
        if rel.startswith((".", "_index/", "attachments/")) or rel == "INDEX.md":
            continue
        note = ltm.read_note(vault, rel)
        if note is None:
            continue
        tags = note["frontmatter"].get("tags", [])
        if isinstance(tags, list) and INBOX_TAG in tags:
            out.append({"path": rel, "frontmatter": note["frontmatter"],
                        "body": note["body"]})
    return out


def enrich(note: dict, ts: int) -> dict:
    """補齊 §5.2 欄位(id 除外——正式入庫時由 writer/ltm 給)。冪等:已有的不覆蓋。"""
    fm = note["frontmatter"]
    if "content_hash" not in fm:
        fm["content_hash"] = content_hash(note["body"])
    if "captured_at" not in fm:
        fm["captured_at"] = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
    if "source_id" not in fm:
        fm["source_id"] = _extract_source_id(fm)
    return note


def _note_date_key(note: dict) -> str:
    """去重先後依據:原文發布時間(date)早者為正本;無 date 排最後。"""
    return str(note["frontmatter"].get("date") or "9999-99-99")


def dedupe(notes: list[dict]) -> tuple[list[dict], list[dict]]:
    """跨源去重:URL 正規化或 content_hash 相同 → **發布時間晚的**標 duplicate。

    回 (uniques, duplicates)。正本 = date 最早的一篇(手動 QA 抓到:原本依
    path 字母序,誰是正本變成檔名運氣)。
    """
    seen_urls: dict[str, str] = {}
    seen_hashes: dict[str, str] = {}
    uniques, duplicates = [], []
    for note in sorted(notes, key=_note_date_key):
        fm = note["frontmatter"]
        url_key = normalize_url(fm["url"]) if fm.get("url") else None
        hash_key = fm.get("content_hash")
        if (url_key and url_key in seen_urls) or (hash_key and hash_key in seen_hashes):
            duplicates.append(note)
            continue
        if url_key:
            seen_urls[url_key] = note["path"]
        if hash_key:
            seen_hashes[hash_key] = note["path"]
        uniques.append(note)
    return uniques, duplicates


def prepare(vault: Path, ts: int) -> dict:
    """完整前處理:掃 inbox → enrich → dedupe。回 {uniques, duplicates, scanned}。"""
    notes = scan_inbox(vault)
    for n in notes:
        enrich(n, ts)
    uniques, duplicates = dedupe(notes)
    return {"scanned": len(notes), "uniques": uniques, "duplicates": duplicates}
