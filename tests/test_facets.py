"""part-007-slice-000:profile_facets 資料層 + stability detector。

驗證目標(DESIGN §Verification Targets 對應):
- 單次證據不建 stable facet;N 次跨 M 天 → provisional → stable(detector 純函數)
- pin 後評分不再改動;forget 後不再升級、不再載入,但證據列仍在
- UNIQUE active 約束:同 class+key 只一個 active;superseded 歷史可多筆
"""

import json
import sqlite3

import pytest

import config
from core import facets, stm

DAY = 86400
T0 = 1_800_000_000  # 固定基準時間(確定性)


@pytest.fixture()
def db(tmp_path):
    path = tmp_path / "state.db"
    stm.init(path)
    return path


def make_evidence(state="provisional", user_state="auto", count=1,
                  first=T0, last=None):
    return facets.FacetEvidence(
        state=state, user_state=user_state, evidence_count=count,
        first_seen_at=first,
        last_seen_at=last if last is not None else first)


# ── detector 純函數:決策表重放 ──────────────────────────────────────

def test_single_evidence_never_stable():
    a = facets.assess(make_evidence(count=1))
    assert a.decision == "hold"


def test_enough_count_same_day_holds():
    """N 次證據但同一天(未跨天)→ 不升級(防單日洗量)。"""
    a = facets.assess(make_evidence(count=config.FACET_STABLE_MIN_EVIDENCE))
    assert a.decision == "hold"


def test_enough_days_too_few_evidence_holds():
    a = facets.assess(make_evidence(
        count=config.FACET_STABLE_MIN_EVIDENCE - 1,
        last=T0 + config.FACET_STABLE_MIN_DAYS * DAY))
    assert a.decision == "hold"


def test_threshold_met_promotes():
    a = facets.assess(make_evidence(
        count=config.FACET_STABLE_MIN_EVIDENCE,
        last=T0 + config.FACET_STABLE_MIN_DAYS * DAY))
    assert a.decision == "promote"
    assert 0.0 < a.stability <= 1.0


def test_pinned_holds_regardless_of_evidence():
    """pinned ⇒ 評分無效化:再多證據也不動。"""
    a = facets.assess(make_evidence(
        user_state="pinned", count=99, last=T0 + 30 * DAY))
    assert a.decision == "hold"
    assert "pinned" in a.reason


def test_forgotten_blocks():
    for ev in (make_evidence(user_state="forgotten", count=99, last=T0 + 30 * DAY),
               make_evidence(state="forgotten", count=99, last=T0 + 30 * DAY),
               make_evidence(state="superseded", count=99, last=T0 + 30 * DAY)):
        assert facets.assess(ev).decision == "block"


def test_stable_holds():
    assert facets.assess(make_evidence(state="stable", count=10,
                                       last=T0 + 10 * DAY)).decision == "hold"


def test_unknown_state_raises():
    with pytest.raises(ValueError):
        facets.assess(make_evidence(state="bogus"))


def test_assess_is_deterministic():
    ev = make_evidence(count=5, last=T0 + 5 * DAY)
    assert facets.assess(ev) == facets.assess(ev)


def test_stability_score_monotonic_and_bounded():
    prev = -1.0
    for count in range(1, 12):
        s = facets.stability_score(count, count)
        assert 0.0 <= s <= 1.0
        assert s >= prev
        prev = s


# ── stm CRUD:真 DB ──────────────────────────────────────────────────

def test_insert_and_get_active(db):
    fid = stm.facet_insert(db, "preference", "reply_lang", "zh-TW",
                           confidence=0.5, evidence_ids=["evt:1"], seen_at=T0)
    row = stm.facet_get_active(db, "preference", "reply_lang")
    assert row["id"] == fid
    assert row["state"] == "provisional"
    assert row["evidence_count"] == 1
    assert json.loads(row["evidence_ids"]) == ["evt:1"]


def test_insert_validation_fail_closed(db):
    with pytest.raises(ValueError):
        stm.facet_insert(db, "bogus_class", "k", "v")
    with pytest.raises(ValueError):
        stm.facet_insert(db, "preference", "  ", "v")
    with pytest.raises(ValueError):
        stm.facet_insert(db, "preference", "k", "")
    with pytest.raises(ValueError):
        stm.facet_insert(db, "preference", "k", "v", confidence=1.5)


def test_unique_active_constraint(db):
    """同 class+key 第二個 active → IntegrityError(partial unique index)。"""
    stm.facet_insert(db, "preference", "editor", "vscode", seen_at=T0)
    with pytest.raises(sqlite3.IntegrityError):
        stm.facet_insert(db, "preference", "editor", "neovim", seen_at=T0)


def test_superseded_history_allows_same_key(db):
    """兩筆 superseded 同 key 是合法歷史(原設計 UNIQUE 三欄的修正點)。"""
    a = stm.facet_insert(db, "preference", "editor", "vim", seen_at=T0)
    b = stm.facet_insert(db, "preference", "editor2", "vscode", seen_at=T0)
    assert stm.facet_supersede(db, a, b)
    # a superseded 後同 key 可再建 active,之後再 supersede 一次 → 兩筆 superseded 同 key
    c = stm.facet_insert(db, "preference", "editor", "emacs", seen_at=T0)
    assert stm.facet_supersede(db, c, b)
    rows = stm.facet_list(db, include_inactive=True)
    superseded_editor = [r for r in rows
                         if r["facet_key"] == "editor" and r["state"] == "superseded"]
    assert len(superseded_editor) == 2


def test_touch_evidence_accumulates(db):
    fid = stm.facet_insert(db, "routine", "work_hours", "09-18",
                           evidence_ids=["evt:1"], seen_at=T0)
    assert stm.facet_touch_evidence(db, fid, ["evt:2"], seen_at=T0 + DAY)
    assert stm.facet_touch_evidence(db, fid, ["evt:3", "evt:2"], seen_at=T0 + 2 * DAY)
    row = stm.facet_get(db, fid)
    assert row["evidence_count"] == 3
    assert json.loads(row["evidence_ids"]) == ["evt:1", "evt:2", "evt:3"]  # 去重保序
    assert row["last_seen_at"] == T0 + 2 * DAY
    assert row["first_seen_at"] == T0


def test_touch_evidence_rejects_empty(db):
    fid = stm.facet_insert(db, "routine", "k", "v", seen_at=T0)
    with pytest.raises(ValueError):
        stm.facet_touch_evidence(db, fid, [])


def test_promote_only_from_provisional_auto(db):
    fid = stm.facet_insert(db, "preference", "k", "v", seen_at=T0)
    assert stm.facet_promote(db, fid, 0.6)
    assert stm.facet_get(db, fid)["state"] == "stable"
    assert not stm.facet_promote(db, fid, 0.7)  # 已 stable,再 promote 無效


def test_pin_promotes_and_freezes(db):
    """pin:provisional 直升 stable + user_state=pinned;之後 detector hold。"""
    fid = stm.facet_insert(db, "preference", "k", "v", seen_at=T0)
    assert stm.facet_set_user_state(db, fid, "pinned")
    row = stm.facet_get(db, fid)
    assert (row["state"], row["user_state"], row["stability"]) == ("stable", "pinned", 1.0)
    assert facets.assess_row(row).decision == "hold"
    # pinned 不可被 supersede
    other = stm.facet_insert(db, "preference", "k2", "v2", seen_at=T0)
    assert not stm.facet_supersede(db, fid, other)


def test_forget_deactivates_but_keeps_evidence(db):
    fid = stm.facet_insert(db, "preference", "k", "v",
                           evidence_ids=["evt:9"], seen_at=T0)
    assert stm.facet_set_user_state(db, fid, "forgotten")
    row = stm.facet_get(db, fid)
    assert (row["state"], row["user_state"]) == ("forgotten", "forgotten")
    assert json.loads(row["evidence_ids"]) == ["evt:9"]      # 證據仍在
    assert row not in stm.facet_list(db)                     # 不再載入(active 列表)
    assert not stm.facet_touch_evidence(db, fid, ["evt:10"]) # 不再累積
    assert not stm.facet_promote(db, fid, 0.9)               # 不再升級
    assert facets.assess_row(row).decision == "block"


def test_forget_then_same_key_can_restart(db):
    """forgotten 釋放 unique active 槽:同 key 可重新建立(重走生命週期)。"""
    fid = stm.facet_insert(db, "preference", "k", "v", seen_at=T0)
    stm.facet_set_user_state(db, fid, "forgotten")
    fid2 = stm.facet_insert(db, "preference", "k", "v2", seen_at=T0)
    assert fid2 != fid
    assert stm.facet_get_active(db, "preference", "k")["id"] == fid2


def test_supersede_guards(db):
    a = stm.facet_insert(db, "preference", "a", "1", seen_at=T0)
    b = stm.facet_insert(db, "preference", "b", "2", seen_at=T0)
    with pytest.raises(ValueError):
        stm.facet_supersede(db, a, a)             # 自我取代
    assert not stm.facet_supersede(db, a, 9999)   # new 不存在
    assert stm.facet_supersede(db, a, b)
    row = stm.facet_get(db, a)
    assert (row["state"], row["superseded_by"]) == ("superseded", b)
    assert not stm.facet_supersede(db, a, b)      # 已 superseded,不可重複轉出


def test_detector_promote_roundtrip_with_db(db):
    """端到端(無 LLM):insert → 累積 N 次跨 M 天 → detector promote → DB stable。"""
    fid = stm.facet_insert(db, "routine", "work_hours", "09-18",
                           evidence_ids=["evt:1"], seen_at=T0)
    for i in range(1, config.FACET_STABLE_MIN_EVIDENCE):
        stm.facet_touch_evidence(db, fid, [f"evt:{i + 1}"],
                                 seen_at=T0 + i * config.FACET_STABLE_MIN_DAYS * DAY)
    row = stm.facet_get(db, fid)
    a = facets.assess_row(row)
    assert a.decision == "promote"
    assert stm.facet_promote(db, fid, a.stability)
    assert stm.facet_get(db, fid)["state"] == "stable"


# ── CLI ──────────────────────────────────────────────────────────────

def test_cli_facets_list_empty_ok(db, capsys):
    assert stm.main(["--db", str(db), "facets", "list"]) == 0
    assert "(empty)" in capsys.readouterr().out


def test_cli_pin_and_forget(db, capsys):
    fid = stm.facet_insert(db, "preference", "k", "v", seen_at=T0)
    assert stm.main(["--db", str(db), "facets", "pin", str(fid)]) == 0
    assert stm.facet_get(db, fid)["user_state"] == "pinned"
    assert stm.main(["--db", str(db), "facets", "forget", str(fid)]) == 0
    assert stm.facet_get(db, fid)["state"] == "forgotten"
    assert stm.main(["--db", str(db), "facets", "forget", "9999"]) == 1


def test_cli_list_shows_facets(db, capsys):
    stm.facet_insert(db, "preference", "reply_lang", "zh-TW", seen_at=T0)
    assert stm.main(["--db", str(db), "facets", "list"]) == 0
    out = capsys.readouterr().out
    assert "reply_lang" in out and "provisional" in out
