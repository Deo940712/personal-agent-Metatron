"""part-004-slice-002:curator(前處理/去重/評分閘門/配額/manual_tags/
驗證攔截 + boundary)。LLM 全 mock。"""

import json

import pytest

import config
from core import curate, curator_pre, ltm, stm, vindex

TS = 1_752_300_000


@pytest.fixture()
def env(tmp_path):
    vault = tmp_path / "vault"
    ltm.init_vault(vault)
    db = tmp_path / "state.db"
    stm.init(db)
    return {"vault": vault, "idx": tmp_path / "index.db", "db": db}


def add_inbox_post(vault, name, body, *, url=None, manual=False, date="2026-06-30 10:00"):
    """模擬 threads-sync 產出:inbox tag、無 id/content_hash。"""
    lines = ["---", "source: threads", 'author: "tester"']
    if url:
        lines.append(f"url: {url}")
    lines += [f"date: {date}", "likes: 10", "tags:", "  - threads", "  - inbox"]
    if manual:
        lines.append("manual_tags: true")
    lines += ["---", "", body, ""]
    (vault / "semantic").mkdir(exist_ok=True)
    (vault / "semantic" / f"{name}.md").write_text("\n".join(lines), encoding="utf-8")
    return f"semantic/{name}.md"


def curator_api(items):
    """mock LLM:items = [{path, score, tags, summary, evidence}]。"""
    return lambda s, u, m, j: json.dumps({"notes": items})


# ── curator_pre ──────────────────────────────────────────────────────

def test_scan_inbox_finds_only_inbox_tagged(env):
    add_inbox_post(env["vault"], "a", "內容A")
    ltm.write_note(env["vault"], "episodic", title="非inbox", body="x",
                   frontmatter={"source": "consolidation", "tags": ["daily-log"],
                                "summary": "s"}, ts=TS)
    notes = curator_pre.scan_inbox(env["vault"])
    assert len(notes) == 1 and notes[0]["path"] == "semantic/a.md"


def test_enrich_idempotent(env):
    p = add_inbox_post(env["vault"], "a", "內容", url="https://www.threads.com/@u/post/ABC123")
    note = {"path": p, **ltm.read_note(env["vault"], p)}
    curator_pre.enrich(note, TS)
    h1 = note["frontmatter"]["content_hash"]
    assert note["frontmatter"]["source_id"] == "ABC123"
    curator_pre.enrich(note, TS + 999)                     # 再跑:不覆蓋
    assert note["frontmatter"]["content_hash"] == h1


def test_content_hash_whitespace_insensitive():
    assert curator_pre.content_hash("a  b\nc") == curator_pre.content_hash("a b c")


def test_normalize_url():
    f = curator_pre.normalize_url
    assert f("https://X.com/post/1?utm=x#top") == f("https://x.com/post/1/")


def test_dedupe_by_url_and_hash(env):
    add_inbox_post(env["vault"], "a", "同一篇內容", url="https://t.co/@u/post/X1")
    add_inbox_post(env["vault"], "b", "同一篇內容", url="https://other.com/y")  # hash 撞
    add_inbox_post(env["vault"], "c", "不同內容", url="https://t.co/@u/post/X1?utm=z")  # url 撞
    pre = curator_pre.prepare(env["vault"], TS)
    assert pre["scanned"] == 3
    assert len(pre["uniques"]) == 1 and len(pre["duplicates"]) == 2


# ── 管線:評分閘門 ────────────────────────────────────────────────────

def test_high_score_promoted_low_score_metadata(env):
    p_hi = add_inbox_post(env["vault"], "hi", "RAG chunk 調優實測,recall +30%")
    p_lo = add_inbox_post(env["vault"], "lo", "今天天氣真好")
    api = curator_api([
        {"path": p_hi, "score": 8.5, "tags": ["rag-knowledge"],
         "summary": "RAG 調優實測", "evidence": ["RAG chunk 調優實測"]},
        {"path": p_lo, "score": 0.5, "tags": ["low-score"],
         "summary": "日常貼文", "evidence": ["今天天氣真好"]},
    ])
    stats = curate.run(vault=env["vault"], idx_db=env["idx"], db=env["db"],
                       now_ts=TS, _api=api)
    assert stats == {"scanned": 2, "duplicates": 0, "classified": 2,
                     "promoted": 1, "rejected": 0, "batches_failed": 0}

    # 高分:進 registry + vindex 可檢索;inbox tag 移除
    entries = ltm.registry_entries(env["vault"])
    assert len(entries) == 1 and "RAG" in entries[0]["summary"]
    assert vindex.search_fts(env["idx"], "調優實測")
    hi = ltm.read_note(env["vault"], p_hi)["frontmatter"]
    assert hi["tags"] == ["rag-knowledge"] and float(hi["score"]) == 8.5

    # 低分:metadata 保留但不進 registry
    lo = ltm.read_note(env["vault"], p_lo)["frontmatter"]
    assert lo["tags"] == ["low-score"]
    assert len(ltm.registry_entries(env["vault"])) == 1


def test_manual_tags_never_overridden(env):
    p = add_inbox_post(env["vault"], "m", "人工整理過的內容", manual=True)
    api = curator_api([{"path": p, "score": 9.0, "tags": ["ai-agents"],
                        "summary": "x", "evidence": ["人工整理過的內容"]}])
    stats = curate.run(vault=env["vault"], idx_db=env["idx"], db=env["db"],
                       now_ts=TS, _api=api)
    assert stats["rejected"] == 1 and stats["classified"] == 0
    fm = ltm.read_note(env["vault"], p)["frontmatter"]
    assert "inbox" in fm["tags"]                            # 原 tags 不動


def test_duplicates_marked_not_deleted(env):
    add_inbox_post(env["vault"], "a", "同文", url="https://t.co/p/1")
    p_dup = add_inbox_post(env["vault"], "b", "同文", url="https://t.co/p/1?x=1")
    api = curator_api([])   # 唯一篇也不分類(LLM 回空)
    stats = curate.run(vault=env["vault"], idx_db=env["idx"], db=env["db"],
                       now_ts=TS, _api=api)
    assert stats["duplicates"] == 1
    dup = ltm.read_note(env["vault"], p_dup)
    assert dup is not None                                  # 不刪
    assert dup["frontmatter"]["tags"] == ["duplicate"]


# ── writer 驗證攔截(boundary)────────────────────────────────────────

@pytest.mark.parametrize("bad", [
    {"score": 11.0},                                        # 界外
    {"score": True},                                        # bool 偽裝
    {"tags": ["not-in-vocab"]},                             # 詞彙表外
    {"tags": []},
    {"summary": ""},
    {"summary": "x" * 161},
    {"evidence": ["原文裡沒有這句話"]},                       # evidence 不屬實
])
def test_writer_rejects_bad_classify(env, bad):
    p = add_inbox_post(env["vault"], "t", "真實的原文內容在此")
    item = {"path": p, "score": 7.0, "tags": ["ai-agents"],
            "summary": "ok", "evidence": ["真實的原文內容在此"]}
    item.update(bad)
    stats = curate.run(vault=env["vault"], idx_db=env["idx"], db=env["db"],
                       now_ts=TS, _api=curator_api([item]))
    assert stats["classified"] == 0 and stats["rejected"] == 1
    assert "inbox" in ltm.read_note(env["vault"], p)["frontmatter"]["tags"]  # 留 inbox


def test_llm_unknown_path_dropped(env):
    add_inbox_post(env["vault"], "t", "內容")
    api = curator_api([{"path": "semantic/hallucinated.md", "score": 5.0,
                        "tags": ["misc"], "summary": "x", "evidence": ["內容"]}])
    stats = curate.run(vault=env["vault"], idx_db=env["idx"], db=env["db"],
                       now_ts=TS, _api=api)
    assert stats["classified"] == 0                          # 幻覺 path 丟棄
    rejected = [e for e in stm.event_query(env["db"], actor="curator")
                if e["action"] == "proposal_rejected"]
    assert rejected


def test_llm_failure_keeps_inbox(env):
    p = add_inbox_post(env["vault"], "t", "內容")
    def boom(s, u, m, j):
        raise ConnectionError("down")
    stats = curate.run(vault=env["vault"], idx_db=env["idx"], db=env["db"],
                       now_ts=TS, _api=boom)
    assert stats["batches_failed"] == 1
    assert "inbox" in ltm.read_note(env["vault"], p)["frontmatter"]["tags"]  # 下輪重試


# ── 配額 ─────────────────────────────────────────────────────────────

def test_tag_quota_defers_promotion(env, monkeypatch):
    monkeypatch.setattr(config, "CURATE_TAG_QUOTA", 2)
    items = []
    for i in range(4):
        p = add_inbox_post(env["vault"], f"q{i}", f"AI agent 內容 {i}")
        items.append({"path": p, "score": 8.0, "tags": ["ai-agents"],
                      "summary": f"agent 貼文 {i}", "evidence": [f"AI agent 內容 {i}"]})
    stats = curate.run(vault=env["vault"], idx_db=env["idx"], db=env["db"],
                       now_ts=TS, _api=curator_api(items))
    assert stats["classified"] == 4
    assert stats["promoted"] == 2                            # 配額 2,其餘 defer
    assert len(ltm.registry_entries(env["vault"])) == 2
    # deferred 的標記可辨識(下輪/手動再提)
    deferred = [ltm.read_note(env["vault"], f"semantic/q{i}.md")["frontmatter"]
                for i in range(4)]
    assert sum("quota-deferred" in str(fm.get("summary", "")) for fm in deferred) == 2


# ── --job curate 接線 ────────────────────────────────────────────────

def test_job_curate_records_run(env, monkeypatch):
    from core import agent, curate as curate_mod
    monkeypatch.setattr(curate_mod, "run",
                        lambda **kw: {"scanned": 0, "duplicates": 0, "classified": 0,
                                      "promoted": 0, "rejected": 0, "batches_failed": 0})
    rc = agent.job_curate(env["db"])
    assert rc == 0
    con = stm.connect(env["db"])
    row = con.execute("SELECT status FROM agent_runs ORDER BY id DESC LIMIT 1").fetchone()
    con.close()
    assert row[0] == "ok"
