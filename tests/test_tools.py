"""part-006-slice-000: typed capability tools and static exposure catalog."""

from pathlib import Path

import pytest

from core import ltm, stm, transcript
from core.tools import catalog, memory, projects, schedule, tasks
from core.tools.contracts import CapabilityContext, CapabilityResult, Permission


@pytest.fixture()
def db(tmp_path: Path) -> Path:
    path = tmp_path / "state.db"
    stm.init(path)
    return path


def test_catalog_names_are_unique_and_writer_is_only_apply_capability() -> None:
    # Given: the complete static capability catalog.
    specs = catalog.CAPABILITIES

    # When: capability names and write-capable entries are inspected.
    names = [spec.name for spec in specs]
    applying = [spec.name for spec in specs if spec.permission is Permission.APPLY]

    # Then: names are unique and only writer.apply can commit validated writes.
    assert len(names) == len(set(names))
    assert applying == ["writer.apply"]


def test_catalog_keeps_agent_and_interface_exposure_separate() -> None:
    # Given: recall exists as a user-visible capability.
    spec = catalog.by_name("memory.recall")

    # When/Then: its agent allowlist is independent from its interface exposure.
    assert spec.agents == ("recall",)
    assert spec.interfaces == ("cli", "mcp")
    assert spec.permission is Permission.READ
    assert spec.storage == ("vault", "index", "cold-transcript")


def test_tools_document_lists_every_catalog_capability() -> None:
    # Given: the authoritative human-readable capability matrix.
    document = (Path(__file__).parents[1] / "docs" / "TOOLS.md").read_text(
        encoding="utf-8"
    )

    # When/Then: every programmatic capability name appears in the matrix.
    assert all(f"`{spec.name}`" in document for spec in catalog.CAPABILITIES)


def test_today_combines_schedule_and_tasks_without_pending(db: Path) -> None:
    # Given: one active schedule item and one pending task.
    stm.schedule_add(db, "既有會議", 1_800_000_000)
    stm.task_add(db, "買貓砂")

    # When: the today capability is called directly.
    result = schedule.today(CapabilityContext(db=db))

    # Then: it returns the same user-facing summary without staging a write.
    assert result == CapabilityResult(
        text="今日行程/待辦:\n#1 2027-01-15 16:00 既有會議\n---\n#1 買貓砂"
    )


def test_projects_status_formats_progress(db: Path) -> None:
    # Given: a tracked project with blockers and a next action.
    stm.project_set(
        db,
        "my-agent",
        phase="part-006",
        blockers=["token"],
        next_action="build tools",
    )

    # When: project status is requested.
    result = projects.status(CapabilityContext(db=db))

    # Then: the typed result contains the existing observable format.
    assert result.text == (
        "專案進度:\nmy-agent: part-006 | blockers: token | next: build tools"
    )


def test_task_add_stages_pending_through_writer(db: Path) -> None:
    # Given: a task command and a channel reference.
    context = CapabilityContext(db=db, channel_ref="user:7")

    # When: the task-add capability stages the proposal.
    result = tasks.add("買貓砂", evidence="todo 買貓砂", context=context)

    # Then: no task is written before confirmation and pending metadata is preserved.
    assert result.needs_confirmation is True
    assert result.pending_id is not None
    assert stm.task_list(db) == []
    pending = stm.pending_get(db, result.pending_id)
    assert pending is not None
    assert pending["channel_ref"] == "user:7"
    assert pending["proposal"]["evidence"] == ["todo 買貓砂"]


def test_task_complete_uses_validated_writer_path(db: Path) -> None:
    # Given: a pending task.
    task_id = stm.task_add(db, "買貓砂")

    # When: the completion capability is called.
    result = tasks.complete(str(task_id), CapabilityContext(db=db))

    # Then: writer applies the validated proposal immediately.
    assert result.text.startswith("✔")
    assert stm.task_list(db) == []


def test_complete_rejects_ambiguous_unqualified_id_and_accepts_explicit_kind(
    db: Path,
) -> None:
    # Given: schedule and task tables independently allocated the same row id.
    schedule_id = stm.schedule_add(db, "週會", 1_800_000_000)
    task_id = stm.task_add(db, "買貓砂")
    assert schedule_id == task_id

    # When: the unqualified id is completed.
    ambiguous = tasks.complete(str(task_id), CapabilityContext(db=db))

    # Then: neither row is silently chosen and explicit references resolve both.
    assert "同時存在" in ambiguous.text
    assert stm.task_list(db)[0]["status"] == "pending"
    assert stm.schedule_list(db)[0]["status"] == "active"
    assert tasks.complete(f"task {task_id}", CapabilityContext(db=db)).text.startswith("✔")
    assert tasks.complete(
        f"schedule {schedule_id}", CapabilityContext(db=db)
    ).text.startswith("✔")


def test_memory_recall_forwards_typed_context(monkeypatch: pytest.MonkeyPatch, db: Path) -> None:
    # Given: a recall boundary with an injected API marker.
    marker = lambda _s, _u, _m, _j: "unused"  # noqa: E731
    observed: dict[str, str | Path | None] = {}

    def fake_ask(query: str, **kwargs):
        from core.recall import RecallResult

        observed["query"] = query
        observed["db"] = kwargs["db"]
        observed["api"] = "same" if kwargs["_api"] is marker else "different"
        return RecallResult("有來源的回答", citations=["note-1"])

    monkeypatch.setattr(memory.recall, "ask", fake_ask)

    # When: memory recall is invoked.
    result = memory.query("RAG", CapabilityContext(db=db, api=marker))

    # Then: the capability preserves the answer and invocation dependencies.
    assert result.text == "有來源的回答"
    assert observed == {"query": "RAG", "db": db, "api": "same"}


def test_memory_rehydrate_reads_raw_sources(tmp_path: Path) -> None:
    # Given: a vault note linked to one cold transcript entry.
    vault = tmp_path / "vault"
    cold = tmp_path / "transcript"
    ltm.init_vault(vault)
    source_id = transcript.append(
        cold,
        "raw:test:1",
        "event_raw",
        {"text": "原始內容"},
        ts=1_800_000_000,
    )
    note_id = ltm.write_note(
        vault,
        "semantic",
        title="RAG",
        body="摘要",
        frontmatter={
            "source": "test",
            "source_ids": [source_id],
            "tags": ["reference"],
            "summary": "RAG 摘要",
        },
        ts=1_800_000_000,
    )

    # When: the memory rehydrate capability follows the note source ids.
    result = memory.rehydrate(
        f"semantic/{note_id}.md",
        CapabilityContext(vault=vault, transcript_dir=cold),
    )

    # Then: the typed result exposes the raw entry without adding a write path.
    assert result.entries[0]["payload"]["text"] == "原始內容"
