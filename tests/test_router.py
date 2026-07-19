"""part-012-slice-000:router 意圖分類器。

Done gate 對應:
- 七 intent 分類重放（mock LLM）
- 非法輸出 → FALLBACK（enum 外 intent / 非 dict / argument 非 str）
- date_range 驗證（ISO / 起迄順序 / 幻覺日期擋）
- LLMError → FALLBACK（永不拋出）
"""

import json
from datetime import date

import pytest

from core import llm, router, stm

T0 = 1_800_000_000                     # 2027-01-15(本地)
TODAY = date(2027, 1, 15)


@pytest.fixture()
def db(tmp_path):
    path = tmp_path / "state.db"
    stm.init(path)
    return path


def _api(payload: dict):
    return lambda s, u, m, j: json.dumps(payload)


# ── 七 intent 重放 ───────────────────────────────────────────────────

@pytest.mark.parametrize("payload,expected_intent", [
    ({"intent": "schedule_write", "argument": "明天兩點開會"}, "schedule_write"),
    ({"intent": "knowledge", "argument": "RAG 做法"}, "knowledge"),
    ({"intent": "knowledge_list", "argument": ""}, "knowledge_list"),
    ({"intent": "note_create", "argument": "存這段"}, "note_create"),
    ({"intent": "note_edit", "argument": "改 20260101-x"}, "note_edit"),
    ({"intent": "note_delete", "argument": "20260101-x"}, "note_delete"),
    ({"intent": "directive", "argument": "修 dev_status"}, "directive"),
    ({"intent": "advice", "argument": ""}, "advice"),
    ({"intent": "status", "argument": ""}, "status"),
    ({"intent": "smalltalk", "argument": "早安"}, "smalltalk"),
])
def test_intents_roundtrip(db, payload, expected_intent):
    r = router.classify("x", db, now_ts=T0, _api=_api(payload))
    assert r.intent == expected_intent
    assert r.argument == payload["argument"]


def test_schedule_query_with_valid_range(db):
    r = router.classify("明天有什麼", db, now_ts=T0, _api=_api(
        {"intent": "schedule_query", "argument": "明天",
         "date_range": ["2027-01-16", "2027-01-16"]}))
    assert r.intent == "schedule_query"
    assert r.date_range == ("2027-01-16", "2027-01-16")


def test_unclear_with_guess(db):
    r = router.classify("那個弄一下", db, now_ts=T0, _api=_api(
        {"intent": "unclear", "argument": "那個弄一下",
         "guess": ["schedule_write", "knowledge", "bogus"]}))
    assert r.intent == "unclear"
    assert r.guess == ("schedule_write", "knowledge")   # bogus 濾掉,最多 2 個


# ── 非法輸出 → FALLBACK ──────────────────────────────────────────────

def test_unknown_intent_falls_back(db):
    r = router.classify("x", db, now_ts=T0, _api=_api(
        {"intent": "hack_the_db", "argument": ""}))
    assert r is router.FALLBACK


def test_non_dict_falls_back(db):
    r = router.classify("x", db, now_ts=T0,
                        _api=lambda s, u, m, j: '["not", "a", "dict"]')
    assert r is router.FALLBACK


def test_bad_argument_type_falls_back(db):
    r = router.classify("x", db, now_ts=T0, _api=_api(
        {"intent": "knowledge", "argument": 123}))
    assert r is router.FALLBACK


def test_llm_error_falls_back(db):
    def boom(s, u, m, j):
        raise llm.LLMError("down")
    assert router.classify("x", db, now_ts=T0, _api=boom) is router.FALLBACK


def test_bad_json_falls_back(db):
    r = router.classify("x", db, now_ts=T0,
                        _api=lambda s, u, m, j: "not json at all {{{")
    assert r is router.FALLBACK


# ── date_range 驗證 ──────────────────────────────────────────────────

def test_query_without_range_becomes_unclear(db):
    """查詢意圖但無時間窗 → unclear(追問),不亂查。"""
    r = router.classify("有什麼", db, now_ts=T0, _api=_api(
        {"intent": "schedule_query", "argument": "有什麼"}))
    assert r.intent == "unclear"
    assert r.guess == ("schedule_query",)


@pytest.mark.parametrize("bad_range", [
    ["2027-01-20"],                          # 只一個
    ["not-a-date", "2027-01-20"],            # 非 ISO
    ["2027-01-25", "2027-01-20"],            # 起 > 迄
    ["1970-01-01", "1970-01-02"],            # 幻覺過去
    ["2099-01-01", "2099-01-02"],            # 幻覺未來
])
def test_bad_ranges_become_unclear(db, bad_range):
    r = router.classify("x", db, now_ts=T0, _api=_api(
        {"intent": "schedule_query", "argument": "x", "date_range": bad_range}))
    assert r.intent == "unclear"


def test_valid_range_helper_directly():
    assert router._valid_date_range(["2027-01-16", "2027-01-18"], TODAY) == \
        ("2027-01-16", "2027-01-18")
    assert router._valid_date_range(None, TODAY) is None


# ── 契約存在性 ───────────────────────────────────────────────────────

def test_router_contract_exists():
    from core import subagents
    text = subagents.load_contract("router")
    assert "schedule_query" in text and "unclear" in text
