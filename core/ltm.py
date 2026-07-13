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
# 含 threads-sync 14 類 taxonomy(part-004 slice-002 併入)+ 系統 tags
INITIAL_TAGS = [
    # 系統
    "inbox", "duplicate", "low-score", "daily-log", "preference", "ops", "schedule",
    # threads-sync taxonomy(與 vendored classify.py PRIORITY 完全同步,14 類)
    "local-llm", "claude", "codex-openai", "ai-agents", "rag-knowledge",
    "automation", "devops-infra", "dev-frontend", "dev-backend", "ai-tools",
    "learning", "career-life", "github-picks", "misc",
    # 本專案原有
    "ai-agent", "coding",
]

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


def update_note_frontmatter(vault: Path, rel_path: str, fm: dict) -> None:
    """重寫一篇筆記的 frontmatter(body 不動)。curator 正式化 inbox 用。

    注意:這是「更新 frontmatter 欄位」不是「改寫內容」——append-only 原則
    管的是筆記內文與既有筆記不刪;分類欄位本來就是 curator 的職權。
    """
    note = read_note(vault, rel_path)
    if note is None:
        raise ValueError(f"cannot update unparsable note: {rel_path}")
    lines = ["---"]
    for k, v in fm.items():
        if isinstance(v, list):
            lines.append(f"{k}:")
            lines.extend(f"  - {_yaml_scalar(item)}" for item in v)
        else:
            lines.append(f"{k}: {_yaml_scalar(v)}")
    lines += ["---", "", note["body"], ""]
    (vault / rel_path).write_text("\n".join(lines), encoding="utf-8")


def register_existing(vault: Path, rel_path: str, *, summary: str) -> str:
    """把既有筆記(sync 產出,無 id)登記進 registry:配 id + 寫回 frontmatter。

    回傳 note_id。冪等:已有 id 且已在 registry → 直接回。
    """
    note = read_note(vault, rel_path)
    if note is None:
        raise ValueError(f"cannot register unparsable note: {rel_path}")
    fm = note["frontmatter"]

    existing_ids = {e["id"] for e in registry_entries(vault)}
    if fm.get("id") and fm["id"] in existing_ids:
        return fm["id"]

    # 配穩定 ID:以 date(原文發布日)或今天 + 檔名 slug
    date_str = str(fm.get("date", ""))[:10].replace("-", "") or \
        datetime.now().strftime("%Y%m%d")
    base = f"{date_str}-{_slugify(Path(rel_path).stem)}"
    note_id, n = base, 1
    while note_id in existing_ids:
        n += 1
        note_id = f"{base}-{n}"

    fm["id"] = note_id
    update_note_frontmatter(vault, rel_path, fm)
    title = fm.get("title") or Path(rel_path).stem
    _registry_append(vault, note_id, title, rel_path, summary.replace("\n", " ")[:120])
    return note_id


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
