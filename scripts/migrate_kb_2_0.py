#!/usr/bin/env python3
"""Migrate KB 1.0 to KB 2.0: mark existing notes as evidence, create topic seed files.

Usage:
    python scripts/migrate_kb_2_0.py --dry-run     # preview only
    python scripts/migrate_kb_2_0.py --execute     # actually modify files
    python scripts/migrate_kb_2_0.py --rollback    # restore from backup
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import yaml


VAULT_PATH = Path("C:/Users/tcart/my-agent-data/vault")
SEMANTIC_DIR = VAULT_PATH / "semantic"
TOPIC_DIR = SEMANTIC_DIR / "topic"
BACKUP_DIR = VAULT_PATH / ".backup_kb_2_0"


# The 21 evidence notes to be consolidated into 5 topic notes
MIGRATION_GROUPS = {
    "ai-agent-open-source-tools": {
        "title": "AI Agent 開源工具目錄",
        "evidence_ids": [
            "20260614-ai-開源工具學習",
            "20260615-ai-開源工具學習",
            "20260620-ai-開源工具學習",
            "20260620-ai-開源工具學習-2",
            "20260620-ai-開源工具學習-3",
            "20260701-ai-開源工具學習",
            "20260701-ai-開源工具學習-2",
            "20260714-ai-開源工具學習",
            "20260714-ai-開源工具學習-2",
        ],
        "tags": ["ai-agents", "automation", "learning"],
        "summary": "9 個精選 AI Agent 開源工具，涵蓋程式碼檢測、知識庫、閘道器、終端機、簡報生成等領域",
    },
    "claude-code-cost-optimization": {
        "title": "Claude Code 成本優化：模型分工策略",
        "evidence_ids": [
            "20260403-claude-code-的-token-太貴讓它收-gemini-當小弟雜活全丟",
            "20260405-claude-省-token-的小技巧上網查資料叫-gemini-cli-幫忙",
            "20260418-claude-code-真的太噴token",
        ],
        "tags": ["claude", "ai-agents", "automation"],
        "summary": "透過 Gemini CLI 處理搜尋與初步規劃，Claude Code 專注深度分析，有效降低 token 消耗",
    },
    "fable-5-system-prompt-analysis": {
        "title": "Claude Fable 5 System Prompt 外洩事件分析",
        "evidence_ids": [
            "20260615-最近看到一堆人在把-fable-5-的-system-prompt-套給-opu",
            "20260617-claude-fable-5-的-system-prompt-被完整公開了",
            "20260618-炸了-地表最强ai的大脑说明书被人公开挂上了github-anthropic-6",
        ],
        "tags": ["claude", "ai-agents"],
        "summary": "Fable 5 system prompt 外洩事件：內容解析、Opus 4.8 復活方法、安全風險評估",
    },
    "karpathy-claude-md-workflow": {
        "title": "Karpathy CLAUDE.md：AI 工程工作流守則",
        "evidence_ids": [
            "20260526-karpathy的claudemd衝上github-1220k-stars多數人",
            "20260628-karpathy-的-claudemdhttpclaudemd-被傳出來後很多人",
        ],
        "tags": ["claude", "ai-agents", "learning"],
        "summary": "Karpathy 的 CLAUDE.md 工程守則：先讀檔案、最小改動、驗證輸出、記錄錯誤",
    },
    "obsidian-as-ai-knowledge-base": {
        "title": "Obsidian 作為 AI 知識庫的設計模式",
        "evidence_ids": [
            "20251203-notion-obsidian-搬家日記-day-2第二大腦插上-ai-晶片",
            "20260618-很多人把obsidian當作知識庫或claude-code第二個大腦或者記憶但我",
            "20260628-day-180-我的-obsidian-筆記庫ai-搜得到但搜得很慢",
            "20260702-我把obsidian-當成我的-ai-筆記資料庫",
        ],
        "tags": ["rag-knowledge", "ai-agents", "learning"],
        "summary": "Obsidian 作為 AI 知識庫的四種實踐：Copilot 整合、MCP 自動化、OKF 格式、專案資料庫",
    },
}


def load_frontmatter(file_path: Path) -> tuple[dict, str]:
    """Load frontmatter and body from a markdown file."""
    content = file_path.read_text(encoding="utf-8")
    if not content.startswith("---"):
        return {}, content
    parts = content.split("---", 2)
    if len(parts) < 3:
        return {}, content
    fm = yaml.safe_load(parts[1]) or {}
    body = parts[2].strip()
    return fm, body


def save_frontmatter(file_path: Path, fm: dict, body: str) -> None:
    """Save frontmatter and body to a markdown file."""
    content = f"---\n{yaml.dump(fm, allow_unicode=True, sort_keys=False)}---\n\n{body}\n"
    file_path.write_text(content, encoding="utf-8")


def backup_file(file_path: Path) -> Path:
    """Create a backup of the file."""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    backup_path = BACKUP_DIR / file_path.name
    shutil.copy2(file_path, backup_path)
    return backup_path


def migrate_evidence_note(file_path: Path, topic_id: str | None, dry_run: bool = True) -> dict:
    """Mark a note as evidence and optionally link to a topic."""
    fm, body = load_frontmatter(file_path)
    original_fm = fm.copy()
    
    # Add KB 2.0 fields
    fm["note_type"] = "evidence"
    fm["evidence_status"] = "linked" if topic_id else "raw"
    if topic_id:
        fm["consolidated_into"] = [topic_id]
    
    changes = {
        "file": file_path.name,
        "note_id": fm.get("id", "unknown"),
        "topic_id": topic_id,
        "dry_run": dry_run,
    }
    
    if not dry_run:
        backup_file(file_path)
        save_frontmatter(file_path, fm, body)
        changes["backed_up"] = True
        changes["modified"] = True
    
    return changes


def create_topic_note(topic_id: str, group: dict, dry_run: bool = True) -> dict:
    """Create a topic note seed file."""
    TOPIC_DIR.mkdir(parents=True, exist_ok=True)
    file_path = TOPIC_DIR / f"{topic_id}.md"
    
    fm = {
        "id": topic_id,
        "title": group["title"],
        "note_type": "topic",
        "topic_status": "active",
        "source_evidence": group["evidence_ids"],
        "last_consolidated": "2026-07-21",
        "consolidation_version": 1,
        "tags": group["tags"],
        "summary": group["summary"],
    }
    
    body = f"""# {group['title']}

> 本筆記為 KB 2.0 主題筆記，彙整 {len(group['evidence_ids'])} 篇原始貼文。

## 核心內容

{group['summary']}

## 來源證據

本主題筆記彙整自以下原始貼文：
"""
    for eid in group["evidence_ids"]:
        body += f"- `{eid}`\n"
    
    body += """
## 後續更新

本筆記為持續累積型知識，後續相關新證據將追加至此。
"""
    
    changes = {
        "file": f"topic/{topic_id}.md",
        "topic_id": topic_id,
        "evidence_count": len(group["evidence_ids"]),
        "dry_run": dry_run,
    }
    
    if not dry_run:
        save_frontmatter(file_path, fm, body)
        changes["created"] = True
    
    return changes


def find_note_file(note_id: str) -> Path | None:
    """Find a note file by its ID."""
    for file_path in SEMANTIC_DIR.glob("*.md"):
        fm, _ = load_frontmatter(file_path)
        if fm.get("id") == note_id:
            return file_path
    return None


def run_migration(dry_run: bool = True) -> dict:
    """Run the full migration."""
    results = {
        "evidence_marked": [],
        "topic_created": [],
        "errors": [],
    }
    
    # Mark all existing semantic notes as evidence (except those in topic/)
    for file_path in SEMANTIC_DIR.glob("*.md"):
        fm, _ = load_frontmatter(file_path)
        note_id = fm.get("id")
        
        # Skip if already has note_type
        if fm.get("note_type"):
            continue
        
        # Find which topic this note belongs to (if any)
        topic_id = None
        for tid, group in MIGRATION_GROUPS.items():
            if note_id in group["evidence_ids"]:
                topic_id = tid
                break
        
        try:
            result = migrate_evidence_note(file_path, topic_id, dry_run)
            results["evidence_marked"].append(result)
        except Exception as e:
            results["errors"].append({"file": file_path.name, "error": str(e)})
    
    # Create topic notes
    for topic_id, group in MIGRATION_GROUPS.items():
        try:
            result = create_topic_note(topic_id, group, dry_run)
            results["topic_created"].append(result)
        except Exception as e:
            results["errors"].append({"topic_id": topic_id, "error": str(e)})
    
    return results


def rollback() -> dict:
    """Restore from backup."""
    results = {"restored": [], "errors": []}
    
    if not BACKUP_DIR.exists():
        results["errors"].append("No backup found")
        return results
    
    for backup_file in BACKUP_DIR.glob("*.md"):
        target = SEMANTIC_DIR / backup_file.name
        try:
            shutil.copy2(backup_file, target)
            results["restored"].append(backup_file.name)
        except Exception as e:
            results["errors"].append({"file": backup_file.name, "error": str(e)})
    
    return results


def main():
    parser = argparse.ArgumentParser(description="Migrate KB 1.0 to KB 2.0")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true", help="Preview changes only")
    group.add_argument("--execute", action="store_true", help="Execute migration")
    group.add_argument("--rollback", action="store_true", help="Restore from backup")
    args = parser.parse_args()
    
    if args.rollback:
        results = rollback()
        print(f"Restored {len(results['restored'])} files")
        for err in results["errors"]:
            print(f"ERROR: {err}")
        return
    
    dry_run = args.dry_run
    results = run_migration(dry_run=dry_run)
    
    mode = "DRY RUN" if dry_run else "EXECUTE"
    print(f"=== KB 2.0 Migration ({mode}) ===\n")
    
    print(f"Evidence notes to mark: {len(results['evidence_marked'])}")
    print(f"Topic notes to create: {len(results['topic_created'])}")
    
    if results["errors"]:
        print(f"\nERRORS ({len(results['errors'])}):")
        for err in results["errors"]:
            print(f"  - {err}")
    
    if dry_run:
        print("\nRun with --execute to apply changes.")
    else:
        print(f"\nBackup created in: {BACKUP_DIR}")
        print("Run with --rollback to restore.")


if __name__ == "__main__":
    main()
