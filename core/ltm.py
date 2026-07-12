"""DB2 vault 存取層(ARCHITECTURE §5.2;docs/MEMORY-zh.md §5.3)。

vault = 人類知識介面(Obsidian 可讀 markdown)。本模組負責:
- vault 初始化(INDEX.md + 受控詞彙表 + 目錄)
- 筆記寫入(frontmatter 組裝、穩定 ID YYYYMMDD-slug 防撞)
- INDEX.md registry 維護(每篇一行描述——index-first 檢索的資料源)
- 讀取解析(壞 frontmatter 跳過該篇,不炸全庫)

append-only:不改寫既有筆記(supersede 走新筆記,part-004+)。
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

# 初始受控詞彙表(INDEX.md 為執行期真相;此為初始化種子)
INITIAL_TAGS = ["inbox", "ai-agent", "coding", "schedule", "preference",
                "ops", "daily-log"]

_INDEX_TEMPLATE = """# Knowledge Base — Index

## How to use (for agents)
1. 先讀本 index,依一行描述挑 1-3 篇打開;不掃全庫。
2. 引用資訊時附筆記 id。

## Controlled tags
{tags}

## Registry
"""

_REGISTRY_LINE = re.compile(
    r"^- `(?P<id>[^`]+)` — \*\*(?P<title>[^*]+)\*\* — `(?P<path>[^`]+)` — (?P<summary>.+)$")


def init_vault(vault: Path) -> None:
    """建立 vault 骨架。idempotent:已存在的不動。"""
    for sub in ("episodic", "agent/profile", "agent/ops", "agent/sop", "semantic"):
        (vault / sub).mkdir(parents=True, exist_ok=True)
    index = vault / "INDEX.md"
    if not index.exists():
        index.write_text(
            _INDEX_TEMPLATE.format(tags=", ".join(f"`{t}`" for t in INITIAL_TAGS)),
            encoding="utf-8")


def controlled_tags(vault: Path) -> set[str]:
    """從 INDEX.md 讀受控詞彙表(執行期真相)。"""
    index = vault / "INDEX.md"
    if not index.exists():
        return set(INITIAL_TAGS)
    for line in index.read_text(encoding="utf-8").splitlines():
        if line.startswith("`") and "`" in line[1:]:
            return {t.strip("` ") for t in line.split(",")}
    return set(INITIAL_TAGS)


def _slugify(text: str, max_len: int = 40) -> str:
    """標題 → slug:保留中英數,其餘轉 '-';避免 Windows 非法檔名字元。"""
    slug = re.sub(r"[^\w\u4e00-\u9fff]+", "-", text).strip("-").lower()
    return slug[:max_len] or "note"


def make_note_id(vault: Path, subdir: str, title: str, ts: int) -> str:
    """穩定 ID YYYYMMDD-slug;同日同 slug 撞號 → 附 -2, -3…(§5.2 永不重用)。"""
    date = datetime.fromtimestamp(ts).strftime("%Y%m%d")
    base = f"{date}-{_slugify(title)}"
    note_id, n = base, 1
    while (vault / subdir / f"{note_id}.md").exists():
        n += 1
        note_id = f"{base}-{n}"
    return note_id


def _yaml_scalar(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    s = str(v)
    return f'"{s}"' if any(c in s for c in ':#"[]{}') else s


# 合法子目錄白名單(audit S8:防打錯字建野目錄)
ALLOWED_SUBDIRS = {"episodic", "semantic", "agent/profile", "agent/ops", "agent/sop"}


def write_note(vault: Path, subdir: str, *, title: str, body: str,
               frontmatter: dict, ts: int) -> str:
    """寫一篇筆記 + 更新 INDEX registry。回傳 note_id。

    frontmatter 需含 source/tags 等(§5.2);id/title 由本函式補。
    summary 鍵用於 registry 一行描述(index-first 的資料源)。
    """
    if subdir not in ALLOWED_SUBDIRS:
        raise ValueError(f"illegal subdir: {subdir!r} (allowed: {sorted(ALLOWED_SUBDIRS)})")
    note_id = make_note_id(vault, subdir, title, ts)
    fm = {"id": note_id, "title": title, **frontmatter}

    lines = ["---"]
    for k, v in fm.items():
        if isinstance(v, list):
            lines.append(f"{k}:")
            lines.extend(f"  - {_yaml_scalar(item)}" for item in v)
        else:
            lines.append(f"{k}: {_yaml_scalar(v)}")
    lines += ["---", "", body, ""]

    rel_path = f"{subdir}/{note_id}.md"
    path = vault / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")

    summary = str(frontmatter.get("summary", title)).replace("\n", " ")[:120]
    _registry_append(vault, note_id, title, rel_path, summary)
    return note_id


def _registry_append(vault: Path, note_id: str, title: str,
                     rel_path: str, summary: str) -> None:
    index = vault / "INDEX.md"
    if not index.exists():
        init_vault(vault)
    with open(index, "a", encoding="utf-8") as f:
        f.write(f"- `{note_id}` — **{title}** — `{rel_path}` — {summary}\n")


def registry_entries(vault: Path) -> list[dict]:
    """讀 registry(index-first 檢索資料源)。壞行跳過。"""
    index = vault / "INDEX.md"
    out: list[dict] = []
    if not index.exists():
        return out
    for line in index.read_text(encoding="utf-8").splitlines():
        m = _REGISTRY_LINE.match(line)
        if m:
            out.append(m.groupdict())
    return out


def read_note(vault: Path, rel_path: str) -> dict | None:
    """讀一篇筆記 → {frontmatter, body}。壞 frontmatter → None(不炸全庫)。"""
    path = vault / rel_path
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return None
    try:
        _, fm_text, body = text.split("---", 2)
    except ValueError:
        return None
    fm: dict = {}
    current_list: str | None = None
    for line in fm_text.splitlines():
        if not line.strip():
            continue
        if line.startswith("  - ") and current_list:
            fm.setdefault(current_list, []).append(line[4:].strip().strip('"'))
        elif ":" in line:
            key, _, val = line.partition(":")
            key, val = key.strip(), val.strip().strip('"')
            if val == "":
                current_list = key
                fm[key] = []
            else:
                current_list = None
                fm[key] = val
    return {"frontmatter": fm, "body": body.strip()}
