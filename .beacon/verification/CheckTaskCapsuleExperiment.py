# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
# ─── How to run ───
# python .beacon/verification/CheckTaskCapsuleExperiment.py --report docs/ECC-TASK-CAPSULE-REPORT-zh.md --phase pre-result
"""Fail-closed structural checks for the ECC / Task Capsule report (part-003.2).

--phase pre-result : allow the two named result/recommendation placeholders.
--phase final      : allow none; cross-check evidence paths and forbid B/C/D adoption.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Final

ROOT: Final = Path(__file__).resolve().parents[2]
DEFAULT_REPORT: Final = ROOT / "docs" / "ECC-TASK-CAPSULE-REPORT-zh.md"

REQUIRED_SECTIONS: Final = (
    "## 範圍與方法",
    "## 已實作機制",
    "## 文件建議",
    "## 限制",
    "## Metatron 對應",
    "## A/B 方法",
    "## 實驗結果",
    "## 建議",
    "## 來源附錄",
)

ECC_SOURCES: Final = (
    "scripts/lib/state-store/migrations.js",
    "scripts/lib/state-store/queries.js",
    "scripts/lib/state-store/index.js",
    "scripts/lib/session-adapters/canonical-session.js",
    "scripts/hooks/session-start.js",
    "scripts/hooks/session-end.js",
    "scripts/hooks/pre-compact.js",
    "scripts/lib/transcript-context.js",
)

KEY_PHRASES: Final = (
    "ECC 是參考證據",          # ECC is evidence, not authority
    "非 semantic RAG",         # not semantic RAG
    "未找到自主",              # no autonomous paging found
    "無 LLM",                  # no LLM invoked (proxy metrics)
)

# 結果/建議 placeholder(pre-result 允許,final 禁止)
PLACEHOLDERS: Final = ("<!-- RESULT_PLACEHOLDER -->", "<!-- RECOMMENDATION_PLACEHOLDER -->")

# final 階段禁止的採用聲明(affirmative only;不誤傷「不採用 B」等否定語境)
FORBIDDEN_ADOPTION: Final = (
    "B [IMPLEMENTED]", "B 已採用", "已採用 B", "決定採用 B",
    "C [IMPLEMENTED]", "D [IMPLEMENTED]", "C 已採用", "D 已採用",
)


def _check(report: Path, phase: str) -> list[str]:
    if not report.exists():
        return [f"report not found: {report}"]
    text = report.read_text(encoding="utf-8")
    errors: list[str] = []

    for section in REQUIRED_SECTIONS:
        if section not in text:
            errors.append(f"missing section: {section}")

    for src in ECC_SOURCES:
        if src not in text:
            errors.append(f"missing ECC source: {src}")

    for phrase in KEY_PHRASES:
        if phrase not in text:
            errors.append(f"missing key phrase: {phrase}")

    if phase == "final":
        for ph in PLACEHOLDERS:
            if ph in text:
                errors.append(f"unresolved placeholder in final phase: {ph}")
        for bad in FORBIDDEN_ADOPTION:
            if bad in text:
                errors.append(f"forbidden adoption claim: {bad}")
        # final 需引用 evidence summary
        if "task-13-ecc-task-capsule-experiment-summary.json" not in text:
            errors.append("final report must reference the evidence summary JSON")

    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--phase", choices=["pre-result", "final"], default="pre-result")
    args = parser.parse_args(argv)

    errors = _check(args.report, args.phase)
    if errors:
        print(f"FAIL ({args.phase}): {len(errors)} issue(s)")
        for e in errors:
            print(f"  - {e}")
        return 1
    print(f"OK ({args.phase}): report structural checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
