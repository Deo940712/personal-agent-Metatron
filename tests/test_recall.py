"""part-004-slice-003:recall(工具迴圈/引用硬規則/步數上限/回血/
Phase 4 gate 端到端)。LLM 全 mock。"""

import json

import pytest

from core import curate, ltm, recall, retrieve, stm, vindex

TS = 1_752_300_000


@pytest.fixture()
def env(tmp_path):
    vault = tmp_path / "vault"
    ltm.init_vault(vault)
    db = tmp_path / "state.db"
    stm.init(db)
    return {"vault": vault, "idx": tmp_path / "index.db", "db": db,
            "tdir": tmp_path / "transcript"}


def add_note(env, title, summary, body, tags=("rag-knowledge",)):
    nid = ltm.write_note(env["vault"], "semantic", title=title, body=body,
                         frontmatter={"source": "threads", "tags": list(tags),
                                      "summary": summary}, ts=TS)
    vindex.upsert(env["idx"], nid, title=title, summary=summary, tags=list(tags))
    return nid


def scripted_llm(moves):
    """mock LLM:依序回傳 moves(每輪一個 dict)。"""
    queue = [json.dumps(m, ensure_ascii=False) for m in moves]
    return lambda s, u, m, j: queue.pop(0)


def kw(env):
    return dict(vault=env["vault"], idx_db=env["idx"], db=env["db"],
                transcript_dir=env["tdir"])


# ── 基本迴圈 ─────────────────────────────────────────────────────────

def test_search_read_answer_with_citation(env):
    nid = add_note(env, "RAG 調優", "chunk 512→128 recall+30%",
                   "完整內文:chunk size 實驗數據……")
    api = scripted_llm([
        {"tool": "search", "query": "RAG"},
        {"tool": "read_note", "path": f"semantic/{nid}.md"},
        {"tool": "answer", "text": "你存過 RAG chunk 調優,recall +30%。",
         "citations": [nid]},
    ])
    r = recall.ask("我存過哪些 RAG 做法?", **kw(env), _api=api)
    assert r.ok and r.citations == [nid] and r.steps == 3
    assert "RAG" in r.text


def test_honest_not_found(env):
    api = scripted_llm([
        {"tool": "search", "query": "量子計算"},
        {"tool": "answer", "text": "知識庫中找不到關於量子計算的內容。",
         "citations": []},
    ])
    r = recall.ask("量子計算?", **kw(env), _api=api)
    assert r.ok and r.citations == [] and "找不到" in r.text
    assert r.outcome == "not_found"                          # 空引用 = not_found


# ── 裂縫3(part-006-slice-001):嚴格 found/not_found 契約 ──────────────

def test_found_has_valid_citation(env):
    nid = add_note(env, "RAG", "s", "b")
    api = scripted_llm([
        {"tool": "search", "query": "RAG"},
        {"tool": "answer", "text": "你存過 RAG。", "citations": [nid]},
    ])
    r = recall.ask("RAG?", **kw(env), _api=api)
    assert r.ok and r.outcome == "found" and r.citations == [nid]


def test_found_claim_without_citation_downgraded(env):
    """LLM 回有主張的 answer 但 citations=[] → 不得斷言,降級 not_found。

    這是裂縫3 的核心:舊碼只在 citations 非空時驗證,LLM 可「有主張、空引用」
    繞過『無來源不得斷言』。新契約強制 found 必附有效引用。
    """
    add_note(env, "真筆記", "s", "b")
    api = scripted_llm([
        {"tool": "search", "query": "RAG"},
        {"tool": "answer", "text": "你一定存過某個很棒的做法。", "citations": []},
    ])
    r = recall.ask("我存過什麼?", **kw(env), _api=api)
    assert r.outcome == "not_found"                          # 有主張無引用 → 降級
    assert r.citations == []
    assert r.ok                                              # 降級是誠實結果,非執行異常


def test_bogus_citation_is_not_found_not_found_outcome(env):
    """幻覺引用整答丟棄:ok=False(執行異常),outcome 不是 found。"""
    add_note(env, "真筆記", "s", "b")
    api = scripted_llm([
        {"tool": "answer", "text": "編造", "citations": ["20990101-fake"]},
    ])
    r = recall.ask("問題", **kw(env), _api=api)
    assert not r.ok and r.outcome != "found"


# ── 引用硬規則(程式面保障,不信 LLM 自律)─────────────────────────────

def test_bogus_citation_rejected(env):
    add_note(env, "真筆記", "s", "b")
    api = scripted_llm([
        {"tool": "answer", "text": "編造的答案", "citations": ["20990101-fake"]},
    ])
    r = recall.ask("問題", **kw(env), _api=api)
    assert not r.ok and "引用驗證失敗" in r.text            # 幻覺引用 → 整答丟棄


def test_mixed_real_and_bogus_citations_rejected(env):
    nid = add_note(env, "真筆記", "s", "b")
    api = scripted_llm([
        {"tool": "answer", "text": "半真半假", "citations": [nid, "20990101-fake"]},
    ])
    r = recall.ask("問題", **kw(env), _api=api)
    assert not r.ok                                          # 一個假的就全丟


# ── 白名單與防護 ─────────────────────────────────────────────────────

def test_unknown_tool_rejected_loop_continues(env):
    nid = add_note(env, "筆記", "s", "b")
    api = scripted_llm([
        {"tool": "delete_note", "path": "x"},                # 白名單外
        {"tool": "answer", "text": "找不到。", "citations": []},
    ])
    r = recall.ask("問題", **kw(env), _api=api)
    assert r.ok and r.steps == 2                             # 拒絕後迴圈繼續


def test_read_note_path_traversal_blocked(env):
    api = scripted_llm([
        {"tool": "read_note", "path": "../../etc/passwd"},
        {"tool": "answer", "text": "找不到。", "citations": []},
    ])
    r = recall.ask("問題", **kw(env), _api=api)
    assert r.ok                                              # 不 crash,工具回 error


def test_step_limit(env):
    api = scripted_llm([{"tool": "read_note", "path": "semantic/x.md"}] * 10)
    r = recall.ask("問題", **kw(env), _api=api)
    assert not r.ok and r.steps == recall.MAX_STEPS


def test_search_limit_three(env):
    api = scripted_llm([
        {"tool": "search", "query": "a"},
        {"tool": "search", "query": "b"},
        {"tool": "search", "query": "c"},
        {"tool": "search", "query": "d"},                    # 第 4 次 → 上限提示
        {"tool": "answer", "text": "找不到。", "citations": []},
    ])
    r = recall.ask("問題", **kw(env), _api=api)
    assert r.ok


def test_llm_failure_honest(env):
    def boom(s, u, m, j):
        raise ConnectionError("down")
    r = recall.ask("問題", **kw(env), _api=boom)
    assert not r.ok and "檢索失敗" in r.text


def test_r2_citations_not_list_rejected(env):
    """audit R2:citations 是字串 → 曾靜默轉空放行(有主張無引用)→ 拒答。"""
    api = scripted_llm([{"tool": "answer", "text": "有主張的答案",
                         "citations": "not-a-list"}])
    r = recall.ask("問題", **kw(env), _api=api)
    assert not r.ok and "格式錯誤" in r.text


# ── part-004.5-slice-002:superseded_by 提示(Mneme)────────────────────

def test_read_note_surfaces_superseded_by(env):
    """讀到被取代的筆記 → 工具結果帶 _superseded_by_note 提示。"""
    old_id = add_note(env, "舊偏好", "回覆用繁中", "使用者要求回覆一律使用繁體中文")
    ltm.mark_superseded(env["vault"], old_id, "20260710-new-pref")

    captured = {}
    def spy_api(s, u, m, j):
        # 第二輪時 u 會含工具結果;抓下來驗證
        captured["u"] = u
        if "read_note" not in u:
            return json.dumps({"tool": "read_note",
                               "path": f"semantic/{old_id}.md"})
        return json.dumps({"tool": "answer", "text": "找不到。", "citations": []})

    recall.ask("舊偏好?", **kw(env), _api=spy_api)
    assert "_superseded_by_note" in captured["u"]
    assert "20260710-new-pref" in captured["u"]


def test_read_note_no_hint_when_not_superseded(env):
    nid = add_note(env, "現行偏好", "s", "b")
    captured = {}
    def spy_api(s, u, m, j):
        captured["u"] = u
        if "read_note" not in u:
            return json.dumps({"tool": "read_note", "path": f"semantic/{nid}.md"})
        return json.dumps({"tool": "answer", "text": "找不到。", "citations": []})
    recall.ask("偏好?", **kw(env), _api=spy_api)
    assert "_superseded_by_note" not in captured["u"]


# ── 回血接線(search 命中 → health.on_hit 經 retrieve)────────────────

def test_search_heals_source_events(env):
    import config
    from core import health
    eid = stm.event_append(env["db"], "user", "decision", "RAG 選型定案")
    con = stm.connect(env["db"])
    created = con.execute("SELECT created_at FROM events").fetchone()[0]
    con.close()
    t = created + 21 * 86_400
    health.decay(env["db"], now_ts=t)
    health.to_trash(env["db"], now_ts=t, transcript_dir=env["tdir"])

    nid = ltm.write_note(env["vault"], "semantic", title="RAG 選型",
                         body="內文", frontmatter={
                             "source": "consolidation", "tags": ["rag-knowledge"],
                             "summary": "RAG 選型定案", "source_ids": [f"evt:{eid}"]},
                         ts=TS)
    api = scripted_llm([
        {"tool": "search", "query": "RAG 選型"},
        {"tool": "answer", "text": "定案了。", "citations": [nid]},
    ])
    r = recall.ask("RAG 選型?", **kw(env), _api=api)
    assert r.ok
    con = stm.connect(env["db"])
    state = con.execute("SELECT state, health FROM events WHERE id=?", (eid,)).fetchone()
    con.close()
    assert state == ("alive", 1.0)                           # trash 復活


# ── Phase 4 gate:端到端(貼文 → curator → recall)─────────────────────

def test_phase4_gate_end_to_end(env):
    # 1. 模擬 threads-sync 產出(inbox 貼文)
    (env["vault"] / "semantic").mkdir(exist_ok=True)
    (env["vault"] / "semantic" / "post1.md").write_text(
        "---\nsource: threads\nauthor: \"a\"\n"
        "url: https://threads.com/@a/post/AAA\ndate: 2026-06-30 10:00\n"
        "likes: 50\ntags:\n  - threads\n  - inbox\n---\n\n"
        "RAG 優化:chunk 512→128 加 overlap,recall 提升 30%\n", encoding="utf-8")

    # 2. curator 入庫
    curator_api = lambda s, u, m, j: json.dumps({"notes": [
        {"path": "semantic/post1.md", "score": 8.5, "tags": ["rag-knowledge"],
         "summary": "RAG chunk 調優 recall+30%",
         "evidence": ["RAG 優化:chunk 512→128 加 overlap"]}]})
    stats = curate.run(vault=env["vault"], idx_db=env["idx"], db=env["db"],
                       now_ts=TS, _api=curator_api)
    assert stats["promoted"] == 1
    nid = ltm.registry_entries(env["vault"])[0]["id"]

    # 3. recall 檢索 + 引用(search 是真檢索,不 mock)
    recall_api = scripted_llm([
        {"tool": "search", "query": "RAG chunk"},
        {"tool": "read_note", "path": "semantic/post1.md"},
        {"tool": "answer",
         "text": "你存過 RAG chunk 調優:512→128 加 overlap,recall +30%。",
         "citations": [nid]},
    ])
    r = recall.ask("我存過哪些 RAG 優化?", **kw(env), _api=recall_api)
    assert r.ok and r.citations == [nid]
    assert "recall +30%" in r.text                           # Phase 4 gate ✅
