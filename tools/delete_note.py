# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""從知識庫刪一篇筆記(乾淨:vault 檔 + 向量索引 + registry),並加入刪除黑名單。

黑名單(vault/.deleted_hashes.txt)讓 import_threads_vault.py 重跑時不復活已刪貼文。

用法:
    python tools/delete_note.py <note_id>            # 依 note id 刪
    python tools/delete_note.py --match 5082         # 依檔名關鍵字找(先列出確認)
    python tools/delete_note.py --match 5082 --yes   # 找到唯一一篇直接刪
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

import config  # noqa: E402
from core import curator_pre, ltm, vindex  # noqa: E402

BLACKLIST_FILE = ".deleted_hashes.txt"


def _out(s: str) -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    print(s)


def _resolve(vault: Path, note_id: str | None, match: str | None) -> list[str]:
    """回符合的 note_id 清單。note_id 直接用;match 掃 semantic 檔名。"""
    if note_id:
        return [note_id]
    if not match:
        return []
    return [md.stem for md in (vault / "semantic").glob("*.md")
            if match in md.name]


def _delete(vault: Path, note_id: str) -> dict:
    """三處刪除 + 黑名單。回統計。"""
    md = vault / "semantic" / f"{note_id}.md"
    result = {"note_id": note_id, "file": False, "registry": 0,
              "index": False, "blacklisted": None}

    # content_hash(刪檔前先算,加黑名單用)
    content_hash = None
    if md.exists():
        note = ltm.read_note(vault, f"semantic/{note_id}.md")
        if note:
            content_hash = curator_pre.content_hash(note["body"])

    # 1. 向量索引(vindex._connect 會 load vec0)
    con = vindex._connect(config.INDEX_DB)
    try:
        rid = con.execute("SELECT rowid FROM note_map WHERE note_id=?",
                          (note_id,)).fetchone()
        if rid:
            con.execute("DELETE FROM notes_vec WHERE rowid=?", (rid[0],))
            con.execute("DELETE FROM note_map WHERE note_id=?", (note_id,))
        con.execute("DELETE FROM notes_fts WHERE note_id=?", (note_id,))
        con.commit()
        result["index"] = bool(rid)
    finally:
        con.close()

    # 2. INDEX registry
    index = vault / "INDEX.md"
    if index.exists():
        lines = index.read_text(encoding="utf-8").splitlines()
        kept = [ln for ln in lines if note_id not in ln]
        result["registry"] = len(lines) - len(kept)
        index.write_text("\n".join(kept) + "\n", encoding="utf-8")

    # 3. vault 檔案
    if md.exists():
        md.unlink()
        result["file"] = True

    # 4. 黑名單(防重跑復活)
    if content_hash:
        bl = vault / BLACKLIST_FILE
        existing = bl.read_text(encoding="utf-8") if bl.exists() else ""
        if content_hash not in existing:
            with open(bl, "a", encoding="utf-8") as f:
                f.write(f"{content_hash}  # {note_id}\n")
            result["blacklisted"] = content_hash

    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("note_id", nargs="?", default=None)
    parser.add_argument("--match", default=None, help="依檔名關鍵字找")
    parser.add_argument("--yes", action="store_true", help="唯一命中直接刪")
    args = parser.parse_args(argv)

    vault = config.VAULT_PATH
    ids = _resolve(vault, args.note_id, args.match)
    if not ids:
        _out("找不到符合的筆記。")
        return 1

    if len(ids) > 1 and not args.note_id:
        _out(f"找到 {len(ids)} 篇,請指定 note_id(或用更精確的 --match):")
        for i in ids:
            _out(f"  {i}")
        return 1

    if args.match and not args.yes and len(ids) == 1:
        _out(f"將刪除:{ids[0]}")
        _out("確認請加 --yes。")
        return 0

    for note_id in ids:
        r = _delete(vault, note_id)
        _out(f"已刪 {note_id}:檔案={r['file']} registry={r['registry']} "
             f"index={r['index']} 黑名單={'+' if r['blacklisted'] else '已有'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
