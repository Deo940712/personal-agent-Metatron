"""fb-sync 探勘階段設定(單一路徑真相源)。

FB 版 threads-sync,目前只做 phase 0 探勘——確認 facebook.com/saved 的資料怎麼載入、
schema 長怎樣、能不能穩定攔。**尚未寫 transform/store/media**;探勘成功才進實作。

風險提醒:FB 反爬比 Threads 嚴、封鎖動作快。原則同 threads-sync:低頻、增量、
不做偵測規避。建議用次要帳號探勘。
"""

from __future__ import annotations

import os
from pathlib import Path

# 專案根 = fb_sync 的父目錄(skills/)。與 threads_sync_vendor 完全隔離。
PROJECT_ROOT = Path(__file__).resolve().parent


def _path_from_env(env_var: str, default: Path) -> Path:
    raw = os.environ.get(env_var)
    return Path(raw).expanduser().resolve() if raw else default


# --- Paths --------------------------------------------------------------------

# 探勘產物(raw dumps + session)在 DATA_DIR 下。與 threads 的 data 完全分開。
DATA_DIR = _path_from_env("FB_SYNC_DATA", PROJECT_ROOT / "fb_data")
RAW_DIR = DATA_DIR / "raw"
USER_DATA_DIR = DATA_DIR / "playwright"

# vault 目標(實作階段才用;探勘不寫)。
VAULT_PATH = _path_from_env("FB_SYNC_VAULT", PROJECT_ROOT / "fb_vault")

# 圖片下載目錄(相對路徑寫進 .md;media 階段用)。
ATTACHMENTS_DIRNAME = "attachments"
ATTACHMENTS_PATH = VAULT_PATH / ATTACHMENTS_DIRNAME

# SQLite state(去重 by id + cursor 續傳 + sync_runs)。
DB_PATH = DATA_DIR / "state.db"

# 增量停止:連續看到這麼多已知 id 就停(非首個,使用者可能中途取消存幾篇)。
STOP_AFTER_SEEN = 15

# 單次爬的滾動安全上限。
MAX_SCROLLS = 200

# --- Browser ------------------------------------------------------------------

# Headed on the dev machine (manual first login). Override with FB_SYNC_HEADLESS=1.
HEADLESS = os.environ.get("FB_SYNC_HEADLESS", "0") == "1"

# FB saved 資料入口(phase 0 釘死):/saved 主頁只是導覽面板,真正的 saved 貼文在
# 特定 collection 的 list_id URL。滾動它才觸發 content_collection GraphQL。
# list_id 由 FB_SYNC_LIST_ID 環境變數指定(你的 saved collection id)。
_LIST_ID = os.environ.get("FB_SYNC_LIST_ID", "1898283180920831")
SAVED_URL = (f"https://www.facebook.com/saved/?list_id={_LIST_ID}"
             "&referrer=SAVE_DASHBOARD_NAVIGATION_PANEL")
BASE_URL = "https://www.facebook.com"

# FB session 的關鍵 cookie(不同於 Threads 的 sessionid/ds_user_id)。
# c_user = 使用者 id;xs = session token。缺這兩個通常認證不了。
KEY_COOKIE_NAMES = ("c_user", "xs")
RELEVANT_DOMAIN_MARKERS = ("facebook.com",)

# --- Probe tunables -----------------------------------------------------------

# 探勘只捲幾次取樣,不做全量爬(只需看懂 schema + 分頁機制)。
PROBE_SCROLLS = 8

# 低頻捲動 + jitter(不做偵測規避,但降低頻率)。
SCROLL_DELAY = 3.0
SCROLL_JITTER = 2.0


def ensure_dirs() -> None:
    """建立探勘會寫入的目錄。idempotent。"""
    for path in (DATA_DIR, RAW_DIR, USER_DATA_DIR):
        path.mkdir(parents=True, exist_ok=True)
