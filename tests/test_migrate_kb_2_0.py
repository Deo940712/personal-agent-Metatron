"""Tests for KB 2.0 migration script."""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.migrate_kb_2_0 import (
    MIGRATION_GROUPS,
    create_topic_note,
    find_note_file,
    load_frontmatter,
    migrate_evidence_note,
    rollback,
    run_migration,
    save_frontmatter,
)


@pytest.fixture
def temp_vault():
    """Create a temporary vault structure for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        vault = Path(tmpdir) / "vault"
        semantic = vault / "semantic"
        topic = semantic / "topic"
        backup = vault / ".backup_kb_2_0"
        
        semantic.mkdir(parents=True)
        topic.mkdir(parents=True)
        
        # Create test evidence notes
        test_notes = [
            ("20260614-ai-開源工具學習", "AI 開源工具學習"),
            ("20260615-ai-開源工具學習", "AI 開源工具學習"),
            ("20260403-claude-code-的-token-太貴", "Claude Code 的 token 太貴"),
        ]
        
        for note_id, title in test_notes:
            fm = {
                "id": note_id,
                "title": title,
                "source": "threads",
                "tags": ["threads", "ai-agents"],
                "summary": f"Summary for {title}",
            }
            body = f"Content for {title}"
            file_path = semantic / f"{note_id}.md"
            save_frontmatter(file_path, fm, body)
        
        yield {
            "vault": vault,
            "semantic": semantic,
            "topic": topic,
            "backup": backup,
        }


def test_load_save_frontmatter(temp_vault):
    """Test frontmatter loading and saving."""
    file_path = temp_vault["semantic"] / "20260614-ai-開源工具學習.md"
    fm, body = load_frontmatter(file_path)
    
    assert fm["id"] == "20260614-ai-開源工具學習"
    assert fm["title"] == "AI 開源工具學習"
    assert "Content for AI 開源工具學習" in body


def test_migrate_evidence_note_dry_run(temp_vault):
    """Test evidence note migration in dry-run mode."""
    file_path = temp_vault["semantic"] / "20260614-ai-開源工具學習.md"
    
    result = migrate_evidence_note(file_path, "ai-agent-open-source-tools", dry_run=True)
    
    assert result["dry_run"] is True
    assert result["topic_id"] == "ai-agent-open-source-tools"
    assert "modified" not in result  # Dry run should not modify
    
    # Verify file was not changed
    fm, _ = load_frontmatter(file_path)
    assert "note_type" not in fm


def test_migrate_evidence_note_execute(temp_vault):
    """Test evidence note migration with actual execution."""
    file_path = temp_vault["semantic"] / "20260614-ai-開源工具學習.md"
    
    # Patch BACKUP_DIR for testing
    import scripts.migrate_kb_2_0 as mig
    original_backup = mig.BACKUP_DIR
    mig.BACKUP_DIR = temp_vault["backup"]
    
    try:
        result = migrate_evidence_note(file_path, "ai-agent-open-source-tools", dry_run=False)
        
        assert result["dry_run"] is False
        assert result["modified"] is True
        assert result["backed_up"] is True
        
        # Verify file was changed
        fm, _ = load_frontmatter(file_path)
        assert fm["note_type"] == "evidence"
        assert fm["evidence_status"] == "linked"
        assert fm["consolidated_into"] == ["ai-agent-open-source-tools"]
        
        # Verify backup exists
        assert (temp_vault["backup"] / file_path.name).exists()
    finally:
        mig.BACKUP_DIR = original_backup


def test_create_topic_note_dry_run(temp_vault):
    """Test topic note creation in dry-run mode."""
    group = MIGRATION_GROUPS["ai-agent-open-source-tools"]
    
    result = create_topic_note("ai-agent-open-source-tools", group, dry_run=True)
    
    assert result["dry_run"] is True
    assert result["topic_id"] == "ai-agent-open-source-tools"
    assert result["evidence_count"] == 9
    assert "created" not in result


def test_create_topic_note_execute(temp_vault):
    """Test topic note creation with actual execution."""
    group = MIGRATION_GROUPS["ai-agent-open-source-tools"]
    
    # Patch TOPIC_DIR for testing
    import scripts.migrate_kb_2_0 as mig
    original_topic = mig.TOPIC_DIR
    mig.TOPIC_DIR = temp_vault["topic"]
    
    try:
        result = create_topic_note("ai-agent-open-source-tools", group, dry_run=False)
        
        assert result["dry_run"] is False
        assert result["created"] is True
        
        # Verify file was created
        file_path = temp_vault["topic"] / "ai-agent-open-source-tools.md"
        assert file_path.exists()
        
        fm, body = load_frontmatter(file_path)
        assert fm["id"] == "ai-agent-open-source-tools"
        assert fm["note_type"] == "topic"
        assert fm["topic_status"] == "active"
        assert len(fm["source_evidence"]) == 9
        assert fm["consolidation_version"] == 1
    finally:
        mig.TOPIC_DIR = original_topic


def test_find_note_file(temp_vault):
    """Test finding a note file by ID."""
    import scripts.migrate_kb_2_0 as mig
    original_semantic = mig.SEMANTIC_DIR
    mig.SEMANTIC_DIR = temp_vault["semantic"]
    
    try:
        file_path = find_note_file("20260614-ai-開源工具學習")
        assert file_path is not None
        assert file_path.name == "20260614-ai-開源工具學習.md"
        
        file_path = find_note_file("nonexistent")
        assert file_path is None
    finally:
        mig.SEMANTIC_DIR = original_semantic


def test_migration_groups_integrity():
    """Test that migration groups have valid structure."""
    total_evidence = 0
    for topic_id, group in MIGRATION_GROUPS.items():
        assert "title" in group
        assert "evidence_ids" in group
        assert "tags" in group
        assert "summary" in group
        assert len(group["evidence_ids"]) > 0
        total_evidence += len(group["evidence_ids"])
    
    # Should have 21 total evidence notes
    assert total_evidence == 21


def test_rollback_no_backup(temp_vault):
    """Test rollback when no backup exists."""
    import scripts.migrate_kb_2_0 as mig
    original_backup = mig.BACKUP_DIR
    mig.BACKUP_DIR = temp_vault["backup"]
    
    try:
        result = rollback()
        assert len(result["restored"]) == 0
        assert len(result["errors"]) > 0
        assert "No backup found" in result["errors"]
    finally:
        mig.BACKUP_DIR = original_backup
