"""part-020 slice-002 operational probe for B7/B10 DB path safety.

Usage:
    python scripts/probes/probe_db_b7.py --path <disposable-db-path>

The path must not exist before the probe. The probe expects stm.connect() to
fail closed with FileNotFoundError and verifies that no empty SQLite file was
created.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core import stm


def main(argv: list[str]) -> int:
    if len(argv) != 2 or argv[0] != "--path":
        print("usage: probe_db_b7.py --path <disposable-db-path>")
        return 2
    target = Path(argv[1])
    if target.exists():
        print(f"FAIL path already exists: {target}")
        return 1
    try:
        stm.connect(target)
    except FileNotFoundError as error:
        if target.exists():
            print(f"FAIL rejected path was created: {target}")
            return 1
        print(f"PASS fail-closed: {error}")
        return 0
    except OSError as error:
        print(f"FAIL unexpected OS error: {error}")
        return 1
    print(f"FAIL connect unexpectedly succeeded and/or created: {target}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

