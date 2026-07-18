"""Project status read capability."""

from __future__ import annotations

from core import stm
from core.tools.contracts import CapabilityContext, CapabilityResult


def status(context: CapabilityContext) -> CapabilityResult:
    """List tracked projects in the established chat format."""
    rows = stm.project_show(context.db)
    if not rows:
        return CapabilityResult("專案進度:\n(無專案)")
    text = "\n".join(
        f"{row['name']}: {row.get('phase') or '-'}"
        + (f" | blockers: {', '.join(row['blockers'])}" if row.get("blockers") else "")
        + (f" | next: {row['next_action']}" if row.get("next_action") else "")
        for row in rows
    )
    return CapabilityResult("專案進度:\n" + text)
