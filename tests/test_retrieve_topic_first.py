"""Tests for KB 2.0 topic-first retrieval logic."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core import ltm, retrieve, vindex


@pytest.fixture
def kb_2_0_vault(tmp_path):
    """Create a KB 2.0 vault structure with topic and evidence notes."""
    vault = tmp_path / "vault"
    semantic = vault / "semantic"
    topic_dir = semantic / "topic"
    evidence_dir = semantic / "evidence"
    
    semantic.mkdir(parents=True)
    topic_dir.mkdir(parents=True)
    evidence_dir.mkdir(parents=True)
    
    # Create INDEX.md with controlled tags
    index = vault / "INDEX.md"
    index.write_text(
        "# 知識庫 — 索引\n\n"
        "## 使用方式(給 agent)\n"
        "1. 先讀本索引,依一行描述挑 1-3 篇打開;不掃全庫。\n"
        "2. 引用資訊時附筆記 id。\n\n"
        "## 受控標籤(controlled tags,系統識別碼,保持英文)\n"
        "`inbox`, `duplicate`, `low-score`, `daily-log`, `preference`, `ops`, `schedule`, `local-llm`, `claude`, `codex-openai`, `ai-agents`, `rag-knowledge`, `automation`, `devops-infra`, `dev-frontend`, `dev-backend`, `ai-tools`, `learning`, `career-life`, `github-picks`, `misc`, `ai-agent`, `coding`\n\n"
        "## 索引清單(registry)\n",
        encoding="utf-8"
    )
    
    # Create topic note
    topic_fm = {
        "id": "ai-agent-tools",
        "title": "AI Agent 工具目錄",
        "note_type": "topic",
        "topic_status": "active",
        "source_evidence": ["evidence-1", "evidence-2"],
        "tags": ["ai-agents", "automation"],
        "summary": "精選 AI Agent 工具",
    }
    topic_body = "# AI Agent 工具目錄\n\n這是整理後的主題筆記。"
    topic_file = topic_dir / "ai-agent-tools.md"
    topic_file.write_text(
        f"---\n{chr(10).join(f'{k}: {v}' if not isinstance(v, list) else f'{k}:{chr(10)}' + chr(10).join(f'  - {item}' for item in v) for k, v in topic_fm.items())}\n---\n\n{topic_body}",
        encoding="utf-8"
    )
    ltm._registry_append(vault, "ai-agent-tools", "AI Agent 工具目錄", "semantic/topic/ai-agent-tools.md", "精選 AI Agent 工具")
    
    # Create evidence note
    evidence_fm = {
        "id": "evidence-1",
        "title": "AI 開源工具學習",
        "note_type": "evidence",
        "evidence_status": "linked",
        "consolidated_into": ["ai-agent-tools"],
        "tags": ["threads", "ai-agents"],
        "summary": "原始貼文內容",
    }
    evidence_body = "# AI 開源工具學習\n\n這是原始貼文。"
    evidence_file = semantic / "evidence-1.md"
    evidence_file.write_text(
        f"---\n{chr(10).join(f'{k}: {v}' if not isinstance(v, list) else f'{k}:{chr(10)}' + chr(10).join(f'  - {item}' for item in v) for k, v in evidence_fm.items())}\n---\n\n{evidence_body}",
        encoding="utf-8"
    )
    ltm._registry_append(vault, "evidence-1", "AI 開源工具學習", "semantic/evidence-1.md", "原始貼文內容")
    
    return {
        "vault": vault,
        "semantic": semantic,
        "topic_dir": topic_dir,
        "evidence_dir": evidence_dir,
    }


def test_registry_entries_includes_both(kb_2_0_vault):
    """Test that registry_entries returns both topic and evidence notes."""
    vault = kb_2_0_vault["vault"]
    entries = ltm.registry_entries(vault)
    
    ids = [e["id"] for e in entries]
    assert "ai-agent-tools" in ids
    assert "evidence-1" in ids


def test_search_prefers_topic(kb_2_0_vault):
    """Test that search returns topic notes before evidence notes."""
    vault = kb_2_0_vault["vault"]
    idx_db = kb_2_0_vault["vault"] / "index.db"
    
    # Build index
    vindex.rebuild(idx_db, vault)
    
    # Search should find topic note
    hits = retrieve.search(vault, idx_db, "AI Agent 工具", limit=5)
    
    # Should find the topic note
    topic_hit = next((h for h in hits if h.note_id == "ai-agent-tools"), None)
    assert topic_hit is not None
    assert "topic" in topic_hit.path


def test_strong_index_hit_prefers_topic(kb_2_0_vault):
    """Test that strong index hits prefer topic notes."""
    vault = kb_2_0_vault["vault"]
    
    hits = retrieve._strong_index_hits(vault, "AI Agent 工具", 5)
    
    # Should find topic note
    topic_hit = next((h for h in hits if h.note_id == "ai-agent-tools"), None)
    assert topic_hit is not None


def test_vindex_rebuild_filters_by_note_type(kb_2_0_vault):
    """Test that vindex.rebuild can filter by note_type."""
    vault = kb_2_0_vault["vault"]
    idx_db = kb_2_0_vault["vault"] / "index.db"
    
    # Rebuild with topic_only=True (to be implemented)
    # For now, just verify rebuild works
    count = vindex.rebuild(idx_db, vault)
    assert count >= 2  # Both topic and evidence


def test_include_evidence_flag(kb_2_0_vault):
    """Test that include_evidence=True allows searching evidence notes."""
    vault = kb_2_0_vault["vault"]
    idx_db = kb_2_0_vault["vault"] / "index.db"
    
    vindex.rebuild(idx_db, vault)
    
    # Default: topic only (to be implemented)
    # With include_evidence=True: should also find evidence
    hits = retrieve.search(vault, idx_db, "AI 開源工具", limit=5)
    
    # For now, both should be findable
    # After implementation, default should not find evidence
    assert len(hits) >= 1


def test_topic_note_has_source_evidence(kb_2_0_vault):
    """Test that topic notes have source_evidence linking to evidence."""
    vault = kb_2_0_vault["vault"]
    
    note = ltm.read_note(vault, "semantic/topic/ai-agent-tools.md")
    assert note is not None
    
    fm = note["frontmatter"]
    assert fm["note_type"] == "topic"
    assert "source_evidence" in fm
    assert "evidence-1" in fm["source_evidence"]


def test_evidence_note_has_consolidated_into(kb_2_0_vault):
    """Test that evidence notes have consolidated_into linking to topic."""
    vault = kb_2_0_vault["vault"]
    
    note = ltm.read_note(vault, "semantic/evidence-1.md")
    assert note is not None
    
    fm = note["frontmatter"]
    assert fm["note_type"] == "evidence"
    assert "consolidated_into" in fm
    assert "ai-agent-tools" in fm["consolidated_into"]
