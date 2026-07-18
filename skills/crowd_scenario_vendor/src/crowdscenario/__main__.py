"""Enable `python -m crowdscenario ...`."""

from __future__ import annotations

import sys

from crowdscenario.cli import main

if __name__ == "__main__":
    sys.exit(main())
