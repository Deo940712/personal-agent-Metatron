"""part-002.5-slice-003:discord_bot 純函式(白名單/custom_id/import 守衛)。
零 discord 連線;真連線是手動 QA。"""

import pytest

import config
from channels import discord_bot as bot


# ── user 白名單(fail-closed)──────────────────────────────────────────

def test_allowed_user_ids_parses_env(monkeypatch):
    monkeypatch.setenv(config.DISCORD_ALLOWED_USER_ID_ENV, "123, 456 ,789")
    assert bot.allowed_user_ids() == {123, 456, 789}


def test_allowed_user_ids_empty(monkeypatch):
    monkeypatch.delenv(config.DISCORD_ALLOWED_USER_ID_ENV, raising=False)
    assert bot.allowed_user_ids() == set()


def test_allowed_user_ids_ignores_garbage(monkeypatch):
    monkeypatch.setenv(config.DISCORD_ALLOWED_USER_ID_ENV, "123,abc,,456")
    assert bot.allowed_user_ids() == {123, 456}


def test_is_authorized_fail_closed():
    assert not bot.is_authorized(123, set())            # 空白名單 → 全拒
    assert bot.is_authorized(123, {123})
    assert not bot.is_authorized(999, {123})


# ── custom_id 編解碼 ──────────────────────────────────────────────────

@pytest.mark.parametrize("pid,approve", [(1, True), (42, False), (99999, True)])
def test_custom_id_roundtrip(pid, approve):
    cid = bot.encode_custom_id(pid, approve)
    assert bot.decode_custom_id(cid) == (pid, approve)


def test_decode_rejects_foreign_custom_id():
    assert bot.decode_custom_id("otherbot:1:y") is None     # 非本 bot 前綴
    assert bot.decode_custom_id("mycfg:abc:y") is None       # 非數字 id
    assert bot.decode_custom_id("mycfg:1:maybe") is None     # 非法 approve
    assert bot.decode_custom_id("garbage") is None
    assert bot.decode_custom_id("mycfg:1") is None           # 欄位不足
    assert bot.decode_custom_id("mycfg:1:y:extra") is None   # 欄位過多


@pytest.mark.parametrize("aid,accepted", [(1, True), (7, False), (500, True)])
def test_advice_id_roundtrip(aid, accepted):
    cid = bot.encode_advice_id(aid, accepted)
    assert bot.decode_advice_id(cid) == (aid, accepted)


def test_advice_and_confirm_ids_dont_collide():
    # advice 回饋按鈕不得被 confirm 解碼器誤認,反之亦然
    assert bot.decode_custom_id(bot.encode_advice_id(1, True)) is None
    assert bot.decode_advice_id(bot.encode_custom_id(1, True)) is None


def test_decode_advice_rejects_foreign():
    assert bot.decode_advice_id("otherbot:1:a") is None
    assert bot.decode_advice_id("myadv:abc:a") is None
    assert bot.decode_advice_id("myadv:1:maybe") is None
    assert bot.decode_advice_id("myadv:1") is None


def test_encode_rejects_nonpositive_id():
    """audit D2:pending_id 是 AUTOINCREMENT 永遠正;encode/decode 對稱契約。"""
    with pytest.raises(ValueError, match="positive"):
        bot.encode_custom_id(0, True)
    with pytest.raises(ValueError, match="positive"):
        bot.encode_custom_id(-5, True)


# ── token 守衛 ───────────────────────────────────────────────────────

def test_token_missing_raises(monkeypatch):
    monkeypatch.delenv(config.DISCORD_TOKEN_ENV, raising=False)
    with pytest.raises(RuntimeError, match="未設"):
        bot.token()


def test_token_present(monkeypatch):
    monkeypatch.setenv(config.DISCORD_TOKEN_ENV, "fake-token")
    assert bot.token() == "fake-token"


# ── import 守衛:discord.py 未裝也能 import 本模組 ────────────────────

def test_module_imports_without_discord_py():
    """薄 adapter 解耦:純函式不需 discord.py;連線函式才延遲 import。"""
    import importlib
    m = importlib.import_module("channels.discord_bot")
    assert hasattr(m, "allowed_user_ids") and hasattr(m, "build_client")
    # build_client 才需要 discord.py;純函式已可用(上面測試證明)


# ── remind job 順掃 expire(整合)─────────────────────────────────────

def test_remind_job_expires_pending(tmp_path, monkeypatch):
    from core import agent, chat, stm
    db = tmp_path / "state.db"
    stm.init(db)
    # 造一個逾時 pending
    pid = stm.pending_add(db, {"x": 1}, "preview")
    con = stm.connect(db)
    con.execute("UPDATE pending_proposals SET created_at = ? WHERE id = ?",
                (stm.now() - chat.CONFIRM_TTL_SECONDS - 1, pid))
    con.commit()
    con.close()

    notes = []
    agent.job_remind(db, notify_fn=notes.append)
    assert stm.pending_get(db, pid)["status"] == "expired"  # remind 順掃清理
