"""part-008-slice-000:watchlist 表 + allowlist + research query 建構。

Done gate 對應:
- allowlist 准/拒（子網域/大小寫/非法 scheme）fail-closed
- watchlist CRUD + state 機 + due 判定
- query 建構確定性
"""

import sqlite3

import pytest

import config
from core import scout, stm

DAY = 86_400
T0 = 1_800_000_000


@pytest.fixture()
def db(tmp_path):
    path = tmp_path / "state.db"
    stm.init(path)
    return path


# ── allowlist（fail-closed）─────────────────────────────────────────

def test_allowlist_permits_listed_domain():
    al = ["arxiv.org", "github.com"]
    assert scout.is_allowed_url("https://arxiv.org/abs/2601.07372", al)
    assert scout.is_allowed_url("http://github.com/x/y", al)


def test_allowlist_permits_subdomain():
    al = ["arxiv.org"]
    assert scout.is_allowed_url("https://export.arxiv.org/rss/cs.AI", al)


def test_allowlist_case_and_www_insensitive():
    al = ["GitHub.com"]
    assert scout.is_allowed_url("https://WWW.github.COM/x", al)


def test_allowlist_rejects_unlisted():
    al = ["arxiv.org"]
    assert not scout.is_allowed_url("https://evil.com/x", al)
    # 子字串攻擊:arxiv.org.evil.com 不得通過
    assert not scout.is_allowed_url("https://arxiv.org.evil.com/x", al)


def test_allowlist_rejects_bad_scheme_and_empty():
    al = ["arxiv.org"]
    assert not scout.is_allowed_url("ftp://arxiv.org/x", al)
    assert not scout.is_allowed_url("file:///etc/passwd", al)
    assert not scout.is_allowed_url("javascript:alert(1)", al)
    assert not scout.is_allowed_url("", al)
    assert not scout.is_allowed_url("not a url", al)


def test_allowlist_empty_denies_all():
    assert not scout.is_allowed_url("https://arxiv.org/x", [])


def test_allowlist_uses_config_default(monkeypatch):
    monkeypatch.setattr(config, "SCOUT_ALLOWLIST_DOMAINS", ["example.org"])
    assert scout.is_allowed_url("https://example.org/x")
    assert not scout.is_allowed_url("https://arxiv.org/x")


# ── build_query（確定性）─────────────────────────────────────────────

def test_build_query_deterministic():
    assert scout.build_query("  RAG   最新  做法 ") == "RAG 最新 做法"
    assert scout.build_query("x") == scout.build_query("x")


def test_build_query_rejects_empty():
    with pytest.raises(ValueError):
        scout.build_query("   ")


# ── watchlist CRUD ───────────────────────────────────────────────────

def test_watchlist_add_and_list(db):
    wid = stm.watchlist_add(db, "RAG 做法", "https://arxiv.org/rss/cs.AI",
                            interval_days=7)
    rows = stm.watchlist_list(db)
    assert len(rows) == 1
    assert rows[0]["id"] == wid
    assert rows[0]["state"] == "active"
    assert rows[0]["last_checked_at"] is None


def test_watchlist_add_validation(db):
    with pytest.raises(ValueError):
        stm.watchlist_add(db, "  ", "https://arxiv.org")
    with pytest.raises(ValueError):
        stm.watchlist_add(db, "t", "")
    with pytest.raises(ValueError):
        stm.watchlist_add(db, "t", "https://arxiv.org", interval_days=0)


def test_watchlist_unique_topic_url(db):
    stm.watchlist_add(db, "t", "https://arxiv.org")
    with pytest.raises(sqlite3.IntegrityError):
        stm.watchlist_add(db, "t", "https://arxiv.org")


def test_watchlist_pause_resume(db):
    wid = stm.watchlist_add(db, "t", "https://arxiv.org")
    assert stm.watchlist_set_state(db, wid, "paused")
    assert stm.watchlist_list(db, state="active") == []
    assert stm.watchlist_set_state(db, wid, "active")
    assert len(stm.watchlist_list(db, state="active")) == 1
    with pytest.raises(ValueError):
        stm.watchlist_set_state(db, wid, "bogus")


def test_watchlist_touch_checked(db):
    wid = stm.watchlist_add(db, "t", "https://arxiv.org")
    assert stm.watchlist_touch_checked(db, wid, now_ts=T0)
    assert stm.watchlist_list(db)[0]["last_checked_at"] == T0


# ── due_watchlist ────────────────────────────────────────────────────

def test_due_never_checked(db, monkeypatch):
    monkeypatch.setattr(config, "SCOUT_ALLOWLIST_DOMAINS", ["arxiv.org"])
    stm.watchlist_add(db, "t", "https://arxiv.org/rss", interval_days=7)
    due = scout.due_watchlist(db, now_ts=T0)
    assert len(due) == 1


def test_due_respects_interval(db, monkeypatch):
    monkeypatch.setattr(config, "SCOUT_ALLOWLIST_DOMAINS", ["arxiv.org"])
    wid = stm.watchlist_add(db, "t", "https://arxiv.org/rss", interval_days=7)
    stm.watchlist_touch_checked(db, wid, now_ts=T0)
    assert scout.due_watchlist(db, now_ts=T0 + 3 * DAY) == []     # 未到期
    assert len(scout.due_watchlist(db, now_ts=T0 + 8 * DAY)) == 1  # 到期


def test_due_excludes_paused(db, monkeypatch):
    monkeypatch.setattr(config, "SCOUT_ALLOWLIST_DOMAINS", ["arxiv.org"])
    wid = stm.watchlist_add(db, "t", "https://arxiv.org/rss")
    stm.watchlist_set_state(db, wid, "paused")
    assert scout.due_watchlist(db, now_ts=T0) == []


def test_due_excludes_non_allowlisted_source(db, monkeypatch):
    """來源 URL 不在 allowlist → 即使到期也排除（fail-closed）。"""
    monkeypatch.setattr(config, "SCOUT_ALLOWLIST_DOMAINS", ["arxiv.org"])
    stm.watchlist_add(db, "t", "https://evil.com/rss")
    assert scout.due_watchlist(db, now_ts=T0) == []


def test_due_enforces_min_interval(db, monkeypatch):
    """interval_days 低於 SCOUT_MIN_INTERVAL_DAYS 時以下限為準。"""
    monkeypatch.setattr(config, "SCOUT_ALLOWLIST_DOMAINS", ["arxiv.org"])
    monkeypatch.setattr(config, "SCOUT_MIN_INTERVAL_DAYS", 5)
    wid = stm.watchlist_add(db, "t", "https://arxiv.org/rss", interval_days=1)
    stm.watchlist_touch_checked(db, wid, now_ts=T0)
    assert scout.due_watchlist(db, now_ts=T0 + 2 * DAY) == []      # 下限 5 天未到
    assert len(scout.due_watchlist(db, now_ts=T0 + 6 * DAY)) == 1


# ── CLI ──────────────────────────────────────────────────────────────

def test_cli_watchlist_add_list(db, capsys):
    assert stm.main(["--db", str(db), "watchlist", "add", "RAG",
                     "https://arxiv.org/rss"]) == 0
    assert stm.main(["--db", str(db), "watchlist", "list"]) == 0
    assert "RAG" in capsys.readouterr().out


def test_cli_watchlist_pause(db, capsys):
    wid = stm.watchlist_add(db, "t", "https://arxiv.org")
    assert stm.main(["--db", str(db), "watchlist", "pause", str(wid)]) == 0
    assert stm.watchlist_list(db)[0]["state"] == "paused"
    assert stm.main(["--db", str(db), "watchlist", "pause", "9999"]) == 1
