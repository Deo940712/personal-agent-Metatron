"""part-004-slice-001:skills/runner(三路徑:ok/error/login_expired;
cursors/agent_runs 整合;步驟中止)。threads-sync 本體黑箱,全 mock。"""

import pytest

from core import stm
from skills import runner


@pytest.fixture()
def db(tmp_path):
    path = tmp_path / "state.db"
    stm.init(path)
    return path


def fake_steps(results):
    """results: {step腳本名: (rc, output)};依呼叫序回傳。"""
    calls = []

    def _run(script, env, timeout=1800):
        calls.append(script.name)
        return results.get(script.name, (0, "ok"))

    _run.calls = calls
    return _run


def last_run(db):
    con = stm.connect(db)
    try:
        cur = con.execute("SELECT trigger, status, summary FROM agent_runs "
                          "ORDER BY id DESC LIMIT 1")
        return dict(zip([d[0] for d in cur.description], cur.fetchone()))
    finally:
        con.close()


# ── classify_output ──────────────────────────────────────────────────

def test_classify_ok():
    assert runner.classify_output(0, "synced 5 posts") == "ok"


def test_classify_error_on_nonzero():
    assert runner.classify_output(1, "traceback ...") == "error"


@pytest.mark.parametrize("marker", ["LOGIN_EXPIRED", "Not Authenticated",
                                     "xfb_auth_platform_anti_scripting"])
def test_classify_login_expired_beats_exit_code(marker):
    assert runner.classify_output(0, f"... {marker} ...") == "login_expired"


# ── 管線三路徑 ────────────────────────────────────────────────────────

def test_all_steps_ok_sets_cursor(db):
    fake = fake_steps({})
    status = runner.run_threads_sync(db, _run_step=fake)
    assert status == "ok"
    assert fake.calls == ["sync.py", "sync_threads.py", "sync_media.py",
                          "classify.py", "build_moc.py"]          # 五步全跑
    assert stm.cursor_get(db, "threads_sync", "last_run") is not None
    r = last_run(db)
    assert r["status"] == "ok" and "moc=ok" in r["summary"]


def test_login_expired_aborts_pipeline(db):
    fake = fake_steps({"sync.py": (0, "ERROR: not authenticated, run import_session")})
    status = runner.run_threads_sync(db, _run_step=fake)
    assert status == "login_expired"
    assert fake.calls == ["sync.py"]                              # 後續不跑
    assert stm.cursor_get(db, "threads_sync", "last_run") is None  # 不記成功
    assert last_run(db)["status"] == "login_expired"


def test_error_midway_aborts(db):
    fake = fake_steps({"sync_media.py": (1, "network down")})
    status = runner.run_threads_sync(db, _run_step=fake)
    assert status == "error"
    assert fake.calls == ["sync.py", "sync_threads.py", "sync_media.py"]
    assert last_run(db)["status"] == "error"


def test_step_events_logged(db):
    fake = fake_steps({"sync_threads.py": (1, "boom")})
    runner.run_threads_sync(db, _run_step=fake)
    ev = stm.event_query(db, actor="sync-threads")
    assert len(ev) == 2                                            # sync ok + threads failed
    actions = {e["action"] for e in ev}                            # 同秒寫入,DESC 排序不穩定
    assert actions == {"completed", "failed"}


def test_steps_subset(db):
    fake = fake_steps({})
    runner.run_threads_sync(db, steps=["classify", "moc"], _run_step=fake)
    assert fake.calls == ["classify.py", "build_moc.py"]


# ── 整合面:環境變數覆蓋 ──────────────────────────────────────────────

def test_env_points_vault_to_project(monkeypatch):
    import config
    env = runner._threads_sync_env()
    assert env["THREADS_SYNC_VAULT"] == str(config.VAULT_PATH)
    assert env["PYTHONUTF8"] == "1"                                # part-001 教訓
    assert env["THREADS_SYNC_HEADLESS"] == "1"


def test_cli_rejects_unknown_step(db, capsys):
    rc = runner.main(["threads_sync", "--steps", "bogus", "--db", str(db)])
    assert rc == 2


# ── vendored 檔案存在(接線完整性)────────────────────────────────────

def test_vendored_scripts_exist():
    pkg = runner.SKILLS_DIR / "threads_sync_vendor" / "threads-sync"
    for script in runner.THREADS_SYNC_STEPS.values():
        assert (pkg / script).exists(), f"missing vendored script: {script}"
