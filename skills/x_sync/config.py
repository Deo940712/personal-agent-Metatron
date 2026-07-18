"""x-sync 探勘階段設定(單一路徑真相源)。

X (Twitter) 版 sync,目前只做 phase 0 探勘——確認 x.com/i/bookmarks 的資料怎麼載入、
schema 長怎樣、能不能穩定攔。**尚未寫 transform/store/media**;探勘成功才進實作。

X bookmarks 走 GraphQL(x.com/i/api/graphql/<id>/Bookmarks),帶 Bearer + ct0 CSRF。
風險比 FB 低(X 對讀自己 bookmarks 較寬鬆),但仍低頻、不做偵測規避為上。
"""

from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent


def _path_from_env(env_var: str, default: Path) -> Path:
    raw = os.environ.get(env_var)
    return Path(raw).expanduser().resolve() if raw else default


# --- Paths --------------------------------------------------------------------

DATA_DIR = _path_from_env("X_SYNC_DATA", PROJECT_ROOT / "x_data")
RAW_DIR = DATA_DIR / "raw"
USER_DATA_DIR = DATA_DIR / "playwright"
VAULT_PATH = _path_from_env("X_SYNC_VAULT", PROJECT_ROOT / "x_vault")
ATTACHMENTS_DIRNAME = "attachments"
ATTACHMENTS_PATH = VAULT_PATH / ATTACHMENTS_DIRNAME
DB_PATH = DATA_DIR / "state.db"

# --- Browser ------------------------------------------------------------------

HEADLESS = os.environ.get("X_SYNC_HEADLESS", "0") == "1"

# 抓取目標:likes(按讚清單)。bookmarks 端點也支援,但實測該帳號 bookmarks 空、
# likes 有內容。likes 頁 = x.com/<username>/likes;端點 GraphQL 是 /Likes。
# 資料路徑(phase 0 釘死):data.user.result.timeline.timeline.instructions[]
#   → TimelineAddEntries → entries[] (entryId=tweet-<id>)
#   → content.itemContent.tweet_results.result (rest_id/legacy.full_text/core...)
USERNAME = os.environ.get("X_SYNC_USERNAME", "ludmng2")
BOOKMARKS_URL = f"https://x.com/{USERNAME}/likes"
BASE_URL = "https://x.com"

# X session 的關鍵 cookie。auth_token = 登入 token;ct0 = CSRF token(GraphQL 需要)。
KEY_COOKIE_NAMES = ("auth_token", "ct0")
RELEVANT_DOMAIN_MARKERS = ("x.com", "twitter.com")

# --- Incremental sync ---------------------------------------------------------

STOP_AFTER_SEEN = 15
MAX_SCROLLS = 200

# --- Probe tunables -----------------------------------------------------------

PROBE_SCROLLS = 10
SCROLL_DELAY = 3.0
SCROLL_JITTER = 2.0


def ensure_dirs() -> None:
    for path in (DATA_DIR, RAW_DIR, USER_DATA_DIR):
        path.mkdir(parents=True, exist_ok=True)
