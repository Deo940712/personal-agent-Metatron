"""Rebuild the vault's MOC (Map of Content) index notes.

Writes vault/_index/<category>.md for every category found in note tags, each
listing that category's notes as [[wikilinks]] sorted by likes desc, plus
vault/_index/00-總索引.md as the master entry point.

Fully regenerates _index/ on every run — safe to re-run after classify.py or
after hand-editing tags in Obsidian.

    uv run python threads-sync/build_moc.py

NOTE: the "claude" category's file is named claude-anthropic.md because
claude.md would collide with the vault's CLAUDE.md rules file on Windows
(case-insensitive filesystem).
"""

from __future__ import annotations

import re
from collections import defaultdict

import config

CATEGORY_LABELS = {
    "ai-agents": "AI Agent 框架與生態",
    "claude": "Claude / Anthropic",
    "codex-openai": "Codex / OpenAI",
    "local-llm": "本地模型部署",
    "rag-knowledge": "RAG 與知識庫",
    "ai-tools": "AI 工具箱",
    "dev-frontend": "前端與設計",
    "dev-backend": "後端與程式語言",
    "devops-infra": "DevOps / 基礎建設",
    "github-picks": "GitHub 開源精選",
    "learning": "學習資源",
    "automation": "自動化流程",
    "career-life": "職涯與心得",
    "misc": "其他",
}

# Filename overrides to avoid collisions (claude.md vs CLAUDE.md on Windows).
FILENAME_OVERRIDES = {"claude": "claude-anthropic"}

_FM_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)

MASTER_NAME = "00-總索引"


def _moc_filename(cat: str) -> str:
    return FILENAME_OVERRIDES.get(cat, cat)


def run() -> int:
    vault = config.VAULT_PATH
    index_dir = vault / "_index"
    index_dir.mkdir(exist_ok=True)

    by_cat: dict[str, list] = defaultdict(list)
    for md in sorted(vault.glob("*.md")):
        if md.name == "CLAUDE.md":
            continue
        text = md.read_text(encoding="utf-8")
        m = _FM_RE.match(text)
        if not m:
            continue
        fm = m.group(1)
        likes_m = re.search(r"^likes: (\d+)$", fm, re.MULTILINE)
        likes = int(likes_m.group(1)) if likes_m else 0
        author_m = re.search(r'^author: "(.*)"$', fm, re.MULTILINE)
        author = author_m.group(1) if author_m else ""
        date_m = re.search(r"^date: (\S+)", fm, re.MULTILINE)
        date = date_m.group(1) if date_m else ""
        tags = re.findall(r"^  - (.+)$", fm, re.MULTILINE)
        cat = next((t for t in tags if t not in ("threads", "inbox")), None)
        if cat is None:
            continue  # still inbox / untagged - classify first
        by_cat[cat].append((likes, date, author, md.stem))

    # Wipe stale per-category MOCs (categories may disappear after re-tagging).
    for old in index_dir.glob("*.md"):
        old.unlink()

    total = 0
    for cat, items in sorted(by_cat.items()):
        label = CATEGORY_LABELS.get(cat, cat)
        items.sort(key=lambda it: -it[0])
        total += len(items)
        lines = [
            "---",
            "tags:",
            "  - moc",
            "---",
            "",
            f"# {label}",
            "",
            f"共 {len(items)} 篇，依按讚數排序。回到 [[{MASTER_NAME}]]",
            "",
        ]
        for likes, date, author, stem in items:
            lines.append(f"- [[{stem}]] — @{author}，{likes} 讚，{date}")
        out = index_dir / f"{_moc_filename(cat)}.md"
        out.write_text("\n".join(lines) + "\n", encoding="utf-8")

    master = [
        "---",
        "tags:",
        "  - moc",
        "---",
        "",
        "# 總索引",
        "",
        f"知識庫共 {total} 篇筆記，來自 Threads 已儲存貼文。",
        "",
        "| 分類 | 篇數 |",
        "|---|---|",
    ]
    for cat, items in sorted(by_cat.items(), key=lambda kv: -len(kv[1])):
        label = CATEGORY_LABELS.get(cat, cat)
        master.append(f"| [[{_moc_filename(cat)}\\|{label}]] | {len(items)} |")
    master.append("")
    (index_dir / f"{MASTER_NAME}.md").write_text("\n".join(master) + "\n", encoding="utf-8")

    print(f"Rebuilt _index/: {len(by_cat)} categories + {MASTER_NAME} ({total} notes indexed)")
    for cat, items in sorted(by_cat.items(), key=lambda kv: -len(kv[1])):
        print(f"  {cat}: {len(items)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
