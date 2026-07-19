# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""一次性把 vendored threads-sync vault 的已 render 貼文匯入 agent 知識庫。

背景:threads-sync 7/16 已成功同步 823 篇 .md + 924 圖到它自己的 vault
(`skills/threads_sync_vendor/vault`),但沒進 agent 知識庫(`my-agent-data/vault`)
——所以 recall 查不到。此腳本把它們接進來。

做法(idempotent、只補不覆蓋):
- 每篇 .md → 複製到 agent vault/semantic/;補 `id`(YYYYMMDD-slug)+ 進 INDEX registry
- attachments 圖片 → 複製到 agent vault/attachments/
- 建向量索引(vindex.upsert;FTS 立即可查)
- content_hash 去重:同內文已匯入 → 跳過

用法:
    python tools/import_threads_vault.py              # 執行匯入
    python tools/import_threads_vault.py --dry-run    # 只報告不動
"""

from __future__ import annotations

import argparse
import shutil
import sys
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

import config  # noqa: E402
from core import curator_pre, ltm, vindex  # noqa: E402

SRC_VAULT = REPO / "skills" / "threads_sync_vendor" / "vault"


def _parse_date_ts(fm: dict) -> int:
    """frontmatter date(YYYY-MM-DD HH:mm)→ epoch;缺/壞 → now。"""
    raw = str(fm.get("date", "")).strip()
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return int(datetime.strptime(raw, fmt).timestamp())
        except ValueError:
            continue
    return int(datetime.now().timestamp())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    if not SRC_VAULT.exists():
        print(f"ERROR: source vault not found: {SRC_VAULT}")
        return 2

    dst_vault = config.VAULT_PATH
    ltm.init_vault(dst_vault)
    idx_db = config.INDEX_DB

    # 既有 content_hash 集合(去重)——讀 agent vault semantic 現有筆記
    seen_hashes: set[str] = set()
    for md in (dst_vault / "semantic").glob("*.md"):
        note = ltm.read_note(dst_vault, f"semantic/{md.name}")
        if note:
            seen_hashes.add(curator_pre.content_hash(note["body"]))

    src_notes = sorted((SRC_VAULT).glob("*.md"))
    stats = {"total": len(src_notes), "imported": 0, "skipped_dupe": 0,
             "skipped_bad": 0, "attachments": 0}

    (dst_vault / "attachments").mkdir(parents=True, exist_ok=True)

    for md in src_notes:
        note = ltm.read_note(SRC_VAULT, md.name)
        if note is None:
            stats["skipped_bad"] += 1
            continue
        body = note["body"]
        h = curator_pre.content_hash(body)
        if h in seen_hashes:
            stats["skipped_dupe"] += 1
            continue

        fm = note["frontmatter"]
        title = md.stem.rsplit(" (", 1)[0][:80] or "threads-post"
        ts = _parse_date_ts(fm)
        summary = (body.strip().splitlines() or [title])[0][:120]

        if args.dry_run:
            stats["imported"] += 1
            seen_hashes.add(h)
            continue

        # frontmatter 補齊 + content_hash;tags 保留(threads-sync 已分類)
        new_fm = {
            "source": "threads",
            "url": fm.get("url", ""),
            "author": fm.get("author", "unknown"),
            "date": fm.get("date", ""),
            "captured_at": datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M"),
            "content_hash": h,
            "tags": fm.get("tags", ["misc"]),
            "summary": summary,
            "likes": fm.get("likes", 0),
        }
        note_id = ltm.write_note(dst_vault, "semantic", title=title, body=body,
                                 frontmatter=new_fm, ts=ts)
        try:
            vindex.upsert(idx_db, note_id, title=title, summary=summary,
                          tags=list(new_fm["tags"]))
        except Exception as e:                       # noqa: BLE001 — 索引衍生物
            print(f"  vindex fail {note_id}: {type(e).__name__}")
        seen_hashes.add(h)
        stats["imported"] += 1

    # 附件複製(idempotent:已存在跳過)
    src_att = SRC_VAULT / "attachments"
    if src_att.exists() and not args.dry_run:
        dst_att = dst_vault / "attachments"
        for img in src_att.iterdir():
            target = dst_att / img.name
            if not target.exists() and img.is_file():
                shutil.copy2(img, target)
                stats["attachments"] += 1

    print(("DRY-RUN " if args.dry_run else "") + f"import stats: {stats}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
