"""Single source of truth for all paths and tunables.

Moving the project between machines (Windows -> Linux) should require editing
ONLY this file. Never hardcode absolute paths anywhere else.
"""

from __future__ import annotations

import os
from pathlib import Path

# Project root = parent of the threads-sync/ package dir.
PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _path_from_env(env_var: str, default: Path) -> Path:
    """Resolve a path from an env var, falling back to a project-relative default."""
    raw = os.environ.get(env_var)
    return Path(raw).expanduser().resolve() if raw else default


# --- Paths --------------------------------------------------------------------

# Obsidian vault target folder. Synced .md files land here.
# Defaults to a project-local ./vault; override with THREADS_SYNC_VAULT.
VAULT_PATH = _path_from_env("THREADS_SYNC_VAULT", PROJECT_ROOT / "vault")

# Where images are downloaded (relative path is referenced inside the .md).
ATTACHMENTS_DIRNAME = "attachments"
ATTACHMENTS_PATH = VAULT_PATH / ATTACHMENTS_DIRNAME

# state.db, raw response dumps, and the Playwright session live under DATA_DIR.
DATA_DIR = _path_from_env("THREADS_SYNC_DATA", PROJECT_ROOT / "data")
RAW_DIR = DATA_DIR / "raw"
USER_DATA_DIR = DATA_DIR / "playwright"
DB_PATH = DATA_DIR / "state.db"

# --- Browser ------------------------------------------------------------------

# Headed on the dev machine (manual first login); toggle per environment.
# Override with THREADS_SYNC_HEADLESS=1.
HEADLESS = os.environ.get("THREADS_SYNC_HEADLESS", "0") == "1"

# Threads pages. Meta migrated Threads from threads.net to threads.com; the old
# domain force-redirects into the Instagram SSO flow.
SAVED_URL = "https://www.threads.com/saved"
BASE_URL = "https://www.threads.com"

# --- Incremental sync ---------------------------------------------------------

# Stop after this many CONSECUTIVE already-known post_ids (not the first hit,
# because the user may have un-saved a few posts mid-list).
STOP_AFTER_SEEN = 15

# Base scroll interval in seconds; jitter is added on top (see SCROLL_JITTER).
SCROLL_DELAY = 2.5
SCROLL_JITTER = 1.5

# Max scroll iterations as a hard safety cap for a single run.
MAX_SCROLLS = 200


def ensure_dirs() -> None:
    """Create all directories this project writes to. Idempotent."""
    for path in (DATA_DIR, RAW_DIR, USER_DATA_DIR, VAULT_PATH, ATTACHMENTS_PATH):
        path.mkdir(parents=True, exist_ok=True)
