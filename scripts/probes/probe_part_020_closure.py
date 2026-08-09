#!/usr/bin/env python3
"""Verify part-020 evidence and issue dispositions deterministically.

# --- How to run ---
# python scripts/probes/probe_part_020_closure.py --design .beacon/parts/part-020/DESIGN.md --todo .beacon/parts/part-020/TODO.md --issues KNOWN_ISSUES.md --evidence-root .beacon/done
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Final

REQUIRED_SLICES: Final[tuple[str, ...]] = ("001", "002", "003", "004")
REQUIRED_ISSUES: Final[dict[str, str]] = {
    "W1": "fixed@020-1",
    "W2": "fixed@020-1",
    "M2": "fixed@020-1",
    "B7": "mitigated@020-2",
    "B10": "fixed@020-2",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify part-020 closure evidence.")
    parser.add_argument("--design", type=Path, required=True)
    parser.add_argument("--todo", type=Path, required=True)
    parser.add_argument("--issues", type=Path, required=True)
    parser.add_argument("--evidence-root", type=Path, required=True)
    return parser.parse_args()


def heading_block(text: str, heading: str, next_heading: str | None) -> str:
    start = text.find(heading)
    if start < 0:
        raise ValueError(f"missing issue heading: {heading}")
    end = text.find(next_heading, start) if next_heading else len(text)
    return text[start:end if end >= 0 else len(text)]


def run(args: argparse.Namespace) -> dict[str, object]:  # noqa: DICT_OK
    design = args.design.read_text(encoding="utf-8")
    todo = args.todo.read_text(encoding="utf-8")
    issues = args.issues.read_text(encoding="utf-8")
    reports: list[str] = []
    for suffix in REQUIRED_SLICES:
        report = args.evidence_root / "part-020" / f"part-020-slice-{suffix}-verification.md"
        if not report.is_file():
            raise ValueError(f"missing verification report: {report}")
        report_text = report.read_text(encoding="utf-8")
        if "PASS" not in report_text or "Evidence" not in report_text:
            raise ValueError(f"verification report is not passing: {report}")
        reports.append(str(report))

    for issue, status in REQUIRED_ISSUES.items():
        start = issues.find(f"### {issue} ")
        if start < 0:
            raise ValueError(f"missing issue: {issue}")
        next_start = issues.find("\n### ", start + 5)
        block = issues[start:next_start if next_start >= 0 else len(issues)]
        if f"`{status}`" not in block:
            raise ValueError(f"{issue} does not have expected status {status}")

    required_terms = ("part-021", "job_runs", "RPO/RTO", "W1", "W2", "M2", "B7", "B10")
    missing = [term for term in required_terms if term not in design + todo]
    if missing:
        raise ValueError(f"closure documents missing terms: {missing}")

    payload = {
        "part": "part-020",
        "verified_slices": list(REQUIRED_SLICES),
        "verification_reports": reports,
        "issue_statuses": REQUIRED_ISSUES,
        "part_021_dependency_present": True,
        "closure": "pass",
    }
    return payload


def main() -> int:
    args = parse_args()
    try:
        payload = run(args)
    except (OSError, ValueError) as error:
        print(json.dumps({"closure": "fail", "error": str(error)}, ensure_ascii=False, sort_keys=True))
        return 1
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
