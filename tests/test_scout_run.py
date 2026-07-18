"""part-008-slice-002:觸發邏輯 + job 接線 + 端到端。

Done gate 對應:
- 無觸發不抓
- watchlist 到期才抓
- 知識缺口觸發（goal facet + 有對應 watchlist + vault 查不到）
- SCOUT_MAX_PER_RUN 上限
- 端到端（fetch → inbox → curate → recall 可見，帶 external_untrusted）
"""

import pytest

import config
from core import agent, curate, curator_pre, ltm, scout, stm
from skills.web_fetch import FetchedEntry

DAY = 86_400
T0 = 1_800_000_000


@pytest.fixture()
def env(tmp_path, monkeypatch):
    db = tmp_path / "state.db"
    stm.init(db)
    vault = tmp_path / "vault"
    monkeypatch.setattr(config, "SCOUT_ALLOWLIST_DOMAINS", ["arxiv.org"])
    return {"db": db, "vault": vault}


def _fetcher(entries):
    return lambda url: entries


def _one_entry(title="RAG 三段檢索", body="具體做法內文"):
    return [FetchedEntry(url="https://arxiv.org/abs/1", title=title,
                         author="a", body=body, published="2026-07-01")]


# ── 觸發收集 ─────────────────────────────────────────────────────────

def test_no_trigger_no_fetch(env):
    called = {"n": 0}

    def fetcher(url):
        called["n"] += 1
        return []
    stats = scout.run(env["db"], env["vault"], fetcher=fetcher, now_ts=T0)
    assert stats["triggers"] == 0 and stats["landed"] == 0
    assert called["n"] == 0                         # 無觸發 → 完全沒抓


def test_due_watchlist_triggers_fetch(env):
    stm.watchlist_add(env["db"], "RAG", "https://arxiv.org/rss", interval_days=7)
    stats = scout.run(env["db"], env["vault"], fetcher=_fetcher(_one_entry()),
                      now_ts=T0)
    assert stats["triggers"] == 1 and stats["landed"] == 1
    # 標 touched → 未到期不再抓
    stats2 = scout.run(env["db"], env["vault"], fetcher=_fetcher(_one_entry()),
                       now_ts=T0 + 3 * DAY)
    assert stats2["triggers"] == 0


def test_knowledge_gap_triggers_with_watchlist_source(env):
    """goal facet 主題有對應 active watchlist 且 vault 查不到 → 觸發研究。"""
    stm.facet_insert(env["db"], "goal", "learn", "向量檢索", seen_at=T0)
    stm.watchlist_add(env["db"], "向量檢索", "https://arxiv.org/rss",
                      interval_days=30)
    triggers = scout.collect_triggers(env["db"], env["vault"], now_ts=T0)
    assert any(t["topic"] == "向量檢索" for t in triggers)


def test_knowledge_gap_no_watchlist_source_no_trigger(env):
    """goal facet 但無對應 watchlist 來源 → 不憑空造 URL、不觸發。"""
    stm.facet_insert(env["db"], "goal", "learn", "冷門主題", seen_at=T0)
    # 只加不相關的 watchlist
    stm.watchlist_add(env["db"], "別的主題", "https://arxiv.org/rss")
    # 別的主題會因 due 觸發,但「冷門主題」不會另外觸發
    triggers = scout.collect_triggers(env["db"], env["vault"], now_ts=T0)
    assert not any(t["topic"] == "冷門主題" for t in triggers)


def test_knowledge_gap_already_covered_no_trigger(env):
    """vault 已有該主題筆記 → 無缺口 → 不重複研究。"""
    ltm.init_vault(env["vault"])
    ltm.write_note(env["vault"], "semantic", title="向量檢索綜述", body="已有內容",
                   frontmatter={"source": "manual", "tags": ["rag-knowledge"],
                                "summary": "向量檢索的做法"}, ts=T0)
    stm.facet_insert(env["db"], "goal", "learn", "向量檢索", seen_at=T0)
    wid = stm.watchlist_add(env["db"], "向量檢索", "https://arxiv.org/rss",
                            interval_days=30)
    stm.watchlist_touch_checked(env["db"], wid, now_ts=T0)   # 非 due
    triggers = scout.collect_triggers(env["db"], env["vault"], now_ts=T0)
    assert not any(t["topic"] == "向量檢索" for t in triggers)


def test_per_run_cap(env, monkeypatch):
    monkeypatch.setattr(config, "SCOUT_MAX_PER_RUN", 2)
    for i in range(5):
        stm.watchlist_add(env["db"], f"topic{i}", f"https://arxiv.org/rss/{i}")
    triggers = scout.collect_triggers(env["db"], env["vault"], now_ts=T0)
    assert len(triggers) == 2


# ── job 接線 ─────────────────────────────────────────────────────────

def test_job_scout_records_agent_run(env, monkeypatch):
    # job_scout 用預設 RSS fetcher(真網路)——mock 掉 rss.fetch 避免打網路
    from skills.web_fetch import rss
    monkeypatch.setattr(rss, "fetch", _fetcher(_one_entry()))
    stm.watchlist_add(env["db"], "RAG", "https://arxiv.org/rss")
    monkeypatch.setattr(config, "VAULT_PATH", env["vault"])
    rc = agent.job_scout(env["db"])
    assert rc == 0
    con = stm.connect(env["db"])
    n = con.execute("SELECT COUNT(*) FROM agent_runs WHERE status='ok'").fetchone()[0]
    con.close()
    assert n >= 1


def test_cli_job_scout(env, monkeypatch, capsys):
    from skills.web_fetch import rss
    monkeypatch.setattr(rss, "fetch", _fetcher([]))
    monkeypatch.setattr(config, "VAULT_PATH", env["vault"])
    rc = agent.main(["--job", "scout", "--db", str(env["db"])])
    assert rc == 0
    assert "OK" in capsys.readouterr().out


# ── 端到端:fetch → inbox → curate → recall 可見 ─────────────────────

def test_end_to_end_fetch_curate_recall(env):
    stm.watchlist_add(env["db"], "RAG", "https://arxiv.org/rss")
    # 1) scout：抓 → inbox（external_untrusted）
    scout.run(env["db"], env["vault"],
              fetcher=_fetcher(_one_entry(title="RAG 三段檢索做法",
                                          body="index → FTS → 向量 → rehydrate 的做法")),
              now_ts=T0)
    inbox = curator_pre.scan_inbox(env["vault"])
    assert len(inbox) == 1
    assert inbox[0]["frontmatter"]["external_untrusted"] == "true"

    # 2) curate：評分入庫（mock LLM 給高分）
    def curator_llm(system, user, model, json_mode):
        assert "外部不受信任資料" in user      # 隔離框確實送進 LLM
        import json
        path = inbox[0]["path"]
        return json.dumps({"notes": [{"path": path, "score": 8.5,
                                      "tags": ["rag-knowledge"],
                                      "summary": "RAG 三段檢索做法",
                                      "evidence": ["index → FTS → 向量"]}]})
    curate.run(vault=env["vault"], db=env["db"], now_ts=T0, _api=curator_llm)

    # 3) recall 可見：進 registry 且帶溯源
    reg = ltm.registry_entries(env["vault"])
    assert any("RAG" in e["summary"] or "RAG" in e["title"] for e in reg)
    # 溯源:external_untrusted + url 仍在 frontmatter
    note = ltm.read_note(env["vault"], inbox[0]["path"])
    assert note["frontmatter"]["external_untrusted"] == "true"
    assert note["frontmatter"]["url"] == "https://arxiv.org/abs/1"
    assert float(note["frontmatter"]["score"]) == 8.5
