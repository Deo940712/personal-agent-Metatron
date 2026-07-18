# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
# ─── How to run ───
# uv run .beacon/verification/CheckMemoryDocs.py
# python .beacon/verification/CheckMemoryDocs.py
"""Fail-closed structural checks for the bilingual memory contract."""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Final

ROOT: Final = Path(__file__).resolve().parents[2]
DEFAULT_ZH: Final = ROOT / "docs" / "MEMORY-zh.md"
DEFAULT_EN: Final = ROOT / "docs" / "MEMORY-en.md"
SECTION_RE: Final = re.compile(r"^## (\d+)\. ", re.MULTILINE)
INVARIANT_RE: Final = re.compile(r"\bMEM-(\d{2})\b")
LINK_RE: Final = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
WINDOWS_ABSOLUTE_RE: Final = re.compile(r"(?<![`\w])[A-Za-z]:\\")
STALE_PHRASES: Final = ("314 tests", "八張表", "eight tables", "四段級聯", "four-stage cascade")
EXPECTED_SECTIONS: Final = tuple(str(number) for number in range(1, 11))
EXPECTED_INVARIANTS: Final = tuple(f"{number:02d}" for number in range(1, 18))
REQUIRED_LITERALS: Final = (
    "[IMPLEMENTED]",
    "[CANDIDATE]",
    "[PLANNED]",
    "[NON-GOAL]",
    "run_id",
    "task_id",
    "job_id",
    "pending_id",
    "source_id",
    "evidence_id",
    "Task Capsule",
    "writer.apply",
)


@dataclass(frozen=True, slots=True)
class Document:
    """Parsed memory document with structural facts used by the verifier."""

    path: Path
    text: str
    sections: tuple[str, ...]
    invariants: tuple[str, ...]


def parse_args() -> argparse.Namespace:
    """Parse optional document paths used by disposable negative probes."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--zh", type=Path, default=DEFAULT_ZH)
    parser.add_argument("--en", type=Path, default=DEFAULT_EN)
    return parser.parse_args()


def load_document(path: Path) -> Document:
    """Read one UTF-8 document and extract its numbered structure."""
    text = path.resolve().read_text(encoding="utf-8")
    return Document(
        path=path.resolve(),
        text=text,
        sections=tuple(SECTION_RE.findall(text)),
        invariants=tuple(INVARIANT_RE.findall(text)),
    )


def check_structure(document: Document) -> list[str]:
    """Return topology, invariant, literal, and path-policy violations."""
    errors: list[str] = []
    if document.sections != EXPECTED_SECTIONS:
        errors.append(
            f"{document.path}: numbered H2 sections {document.sections!r}; "
            f"expected {EXPECTED_SECTIONS!r}"
        )

    for invariant in EXPECTED_INVARIANTS:
        count = document.invariants.count(invariant)
        if count != 1:
            errors.append(
                f"{document.path}: MEM-{invariant} occurs {count} times; expected once"
            )

    unexpected = sorted(set(document.invariants) - set(EXPECTED_INVARIANTS))
    if unexpected:
        errors.append(f"{document.path}: unexpected invariant ids {unexpected!r}")

    for literal in REQUIRED_LITERALS:
        if literal not in document.text:
            errors.append(f"{document.path}: missing required literal {literal!r}")

    if WINDOWS_ABSOLUTE_RE.search(document.text) is not None:
        errors.append(f"{document.path}: contains a repository-specific absolute path")

    for phrase in STALE_PHRASES:
        if phrase in document.text:
            errors.append(f"{document.path}: contains stale phrase {phrase!r}")
    return errors


def check_links(document: Document) -> list[str]:
    """Return errors for unresolved local Markdown links."""
    errors: list[str] = []
    for target in LINK_RE.findall(document.text):
        clean_target = target.split("#", maxsplit=1)[0].strip()
        if not clean_target or "://" in clean_target or clean_target.startswith("mailto:"):
            continue
        resolved = (document.path.parent / clean_target).resolve()
        if not resolved.exists():
            errors.append(f"{document.path}: broken local link {target!r}")
    return errors


def verify(zh_path: Path, en_path: Path) -> tuple[str, ...]:
    """Verify both documents and return all diagnostics."""
    try:
        zh = load_document(zh_path)
        en = load_document(en_path)
    except (OSError, UnicodeError) as error:
        return (f"cannot read memory document as UTF-8: {error}",)

    errors = [
        *check_structure(zh),
        *check_structure(en),
        *check_links(zh),
        *check_links(en),
    ]
    if zh.sections != en.sections:
        errors.append("Chinese and English numbered H2 topology differs")
    if sorted(zh.invariants) != sorted(en.invariants):
        errors.append("Chinese and English invariant sets differ")
    return tuple(errors)


def main() -> int:
    """Run the verifier and expose a scheduler-friendly exit code."""
    args = parse_args()
    errors = verify(args.zh, args.en)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print("MEMORY_DOCS_OK: bilingual topology, invariants, literals, and links verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
