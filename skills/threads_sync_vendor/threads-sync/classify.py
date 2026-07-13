"""Classify inbox notes into the CLAUDE.md taxonomy (keyword scoring).

Finds every vault note still tagged `- inbox`, scores its title (3x weight) and
body (capped per keyword to resist spam) against each category's keyword list,
and replaces `- inbox` with the winning category tag. Idempotent: notes without
`- inbox` are untouched, so re-runs only process newly synced posts.

    uv run python threads-sync/classify.py

The taxonomy must stay in sync with vault/CLAUDE.md's tag table. Machine
classification is ~85-90% accurate; users refine tags by hand in Obsidian, and
those hand edits are never overwritten (no inbox tag -> skipped).
"""

from __future__ import annotations

import re
from collections import Counter

import config

# category -> keywords (case-insensitive substring match)
KEYWORDS: dict[str, list[str]] = {
    "ai-agents": [
        "agent", "hermes", "openclaw", "mcp", "multi-agent", "skills hub",
        "skill", "harness", "subagent", "a2a", "tool-calling", "openhands",
    ],
    "claude": [
        "claude", "anthropic", "opus", "fable", "sonnet", "claude.md", "claudemd",
    ],
    "codex-openai": [
        "codex", "openai", "chatgpt", "gpt-5", "gpt5", "gpt 5", "o3", "sora",
    ],
    "local-llm": [
        "ollama", "gguf", "llama.cpp", "llamacpp", "quantiz", "vram", "qat",
        "gemma", "qwen", "deepseek", "mistral", "minimax", "glm", "kimi",
        "本地模型", "本地執行", "本機推論", "local llm", "8b", "12b", "27b", "70b",
    ],
    "rag-knowledge": [
        "rag", "embedding", "vector", "obsidian", "notion", "notebooklm",
        "知識庫", "第二大腦", "筆記", "qdrant", "知識圖譜",
    ],
    "ai-tools": [
        "tts", "ocr", "whisper", "elevenlabs", "suno", "生圖", "簡報",
        "ppt", "powerpoint", "剪輯", "剪片", "影片生成", "voice",
        "seedance", "veo", "midjourney", "stable diffusion", "語音",
    ],
    "dev-frontend": [
        "css", "react", "frontend", "tailwind", "next.js", "nextjs", "vue",
        "前端", "ui", "ux", "動畫", "hover", "shadcn", "component",
        "design", "設計", "typescript", "javascript", "網頁",
    ],
    "dev-backend": [
        "fastapi", "python", "rust", "golang", " go ", "sql", "database",
        "資料庫", "後端", "api", "backend", "supabase", "postgres",
        "redis", "演算法", "leetcode", "c語言", "llvm", "transformer",
    ],
    "devops-infra": [
        "vps", "docker", "linux", "cloudflare", "dns", "部署", "nginx",
        "server", "伺服器", "ssh", "tailscale", "vpn", "內網",
        "lambda", "aws", "gcp", "oracle cloud", "self-host", "自架",
    ],
    "github-picks": [
        "github", "trending", "開源專案", "open source", "stars",
        "顆星", "repo", "萬星",
    ],
    "learning": [
        "課程", "教學", "cs50", "course", "學習", "tutorial",
        "書", "自學", "大學", "學生", "免費課",
        "講義", "考試", "期末", "apcs", "李宏毅",
    ],
    "automation": [
        "n8n", "workflow", "自動化", "bot", "機器人",
        "line bot", "telegram", "排程", "zapier", "自動化流程",
    ],
    "career-life": [
        "職涯", "轉職", "面試", "接案", "徵才",
        "徵人", "薪", "下班", "副業", "創業",
        "自媒體", "獨立開發",
    ],
}

# tie-break priority: more specific categories first
PRIORITY = [
    "local-llm", "claude", "codex-openai", "ai-agents", "rag-knowledge",
    "automation", "devops-infra", "dev-frontend", "dev-backend", "ai-tools",
    "learning", "career-life", "github-picks", "misc",
]

_FM_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)


def classify(title: str, body: str) -> str:
    """Return the best category for one note. Title hits count 3x."""
    t = title.lower()
    b = body.lower()
    scores: Counter = Counter()
    for cat, words in KEYWORDS.items():
        for w in words:
            wl = w.lower()
            scores[cat] += 3 * t.count(wl) + min(b.count(wl), 5)
    if not scores or max(scores.values()) == 0:
        return "misc"
    best = max(scores.values())
    candidates = [c for c, s in scores.items() if s == best]
    if len(candidates) > 1 or candidates[0] == "github-picks":
        close = [c for c, s in scores.items() if s >= best * 0.6 and s > 0]
        close.sort(key=lambda c: PRIORITY.index(c))
        return close[0]
    return candidates[0]


def run() -> int:
    vault = config.VAULT_PATH
    results: list[tuple[str, str]] = []
    for md in sorted(vault.glob("*.md")):
        if md.name == "CLAUDE.md":
            continue
        text = md.read_text(encoding="utf-8")
        if "  - inbox" not in text:
            continue
        m = _FM_RE.match(text)
        body = text[m.end():] if m else text
        cat = classify(md.stem, body)
        md.write_text(text.replace("  - inbox", f"  - {cat}", 1), encoding="utf-8")
        results.append((md.name, cat))

    if not results:
        print("No inbox notes to classify. All done.")
        return 0

    dist = Counter(cat for _, cat in results)
    print(f"Classified {len(results)} note(s):")
    for cat, n in dist.most_common():
        print(f"  {cat}: {n}")
    print("\nPer-note mapping:")
    for name, cat in sorted(results, key=lambda r: (r[1], r[0])):
        print(f"  {cat}\t{name}")
    print("\nNext: uv run python threads-sync/build_moc.py  (rebuild the index)")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
