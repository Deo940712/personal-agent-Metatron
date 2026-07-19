"""part-011 todo 8:golden-queries 檢索回歸防護（backlog-007）。

15 筆確定性種子筆記 + 20+ 條「query → expected note ∈ top-k」斷言。
測 `retrieve.search`（不給 embed_fn → 走 index-first + FTS，確定性、零網路、零 LLM）。
改索引/檢索邏輯必跑此測——防止記憶檢索品質靜默退化。

斷言 top-k 成員（非精確排名，避免脆弱）。含一條負向斷言證明 harness 有鑑別力。
"""

import pytest

from core import ltm, retrieve, stm, vindex

TS = 1_800_000_000


# (title, summary, tags) — 15 筆跨主題種子。summary 進 INDEX registry + FTS。
GOLDEN_NOTES = [
    ("RAG 檢索增強生成做法", "index-first 到向量 KNN 的四段級聯檢索管線", ["rag-knowledge"]),
    ("向量資料庫選型 sqlite-vec", "本機 sqlite-vec vec0 虛擬表做 KNN 的實測", ["rag-knowledge"]),
    ("FTS5 中文 trigram 全文檢索", "unicode61 不命中中文、trigram 需三字的設定", ["rag-knowledge"]),
    ("Claude Agent SDK 子代理拓撲", "orchestrator 加無狀態 subagent 的生產標準", ["claude"]),
    ("Codex CLI 開發迴圈", "OpenAI codex 在終端機的自動化編碼流程", ["codex-openai"]),
    ("本地 LLM Ollama 部署", "在本機跑 Ollama 提供 OpenAI 相容端點", ["local-llm"]),
    ("Playwright 瀏覽器自動化", "用 persistent context 攔截 GraphQL 回應", ["automation"]),
    ("Windows Task Scheduler 排程", "用 schtasks 註冊每日 job 的做法", ["devops-infra"]),
    ("Discord bot 兩階段確認", "預覽加按鈕確認再落地的互動模式", ["ai-agents"]),
    ("SQLite WAL 併發寫入", "journal_mode WAL 提升讀寫併發的設定", ["dev-backend"]),
    ("React 前端狀態管理", "用 hooks 管理元件狀態的模式", ["dev-frontend"]),
    ("Python uv 套件管理", "用 uv 取代 pip venv 的現代工具鏈", ["dev-backend"]),
    ("Obsidian 知識庫 MOC", "用 map of content 組織 markdown 筆記", ["learning"]),
    ("Prompt injection 防禦", "把外部內容當資料非指令的隔離框做法", ["ai-agents"]),
    ("記憶健康值代謝", "命中回血久不用衰減的遺忘曲線設計", ["ai-agents"]),
]

# (query, expected_title_fragment) — 20+ 條斷言。expected 必在 top-k。
GOLDEN_QUERIES = [
    ("檢索增強生成", "RAG 檢索增強生成做法"),
    ("四段級聯檢索", "RAG 檢索增強生成做法"),
    ("sqlite-vec", "向量資料庫選型 sqlite-vec"),
    ("向量資料庫", "向量資料庫選型 sqlite-vec"),
    ("trigram", "FTS5 中文 trigram 全文檢索"),
    ("全文檢索", "FTS5 中文 trigram 全文檢索"),
    ("Agent SDK", "Claude Agent SDK 子代理拓撲"),
    ("子代理拓撲", "Claude Agent SDK 子代理拓撲"),
    ("Codex", "Codex CLI 開發迴圈"),
    ("Ollama", "本地 LLM Ollama 部署"),
    ("本地 LLM", "本地 LLM Ollama 部署"),
    ("Playwright", "Playwright 瀏覽器自動化"),
    ("Task Scheduler", "Windows Task Scheduler 排程"),
    ("schtasks", "Windows Task Scheduler 排程"),
    ("Discord", "Discord bot 兩階段確認"),
    ("兩階段確認", "Discord bot 兩階段確認"),
    ("WAL 併發", "SQLite WAL 併發寫入"),
    ("React 前端", "React 前端狀態管理"),
    ("uv 套件管理", "Python uv 套件管理"),
    ("Obsidian", "Obsidian 知識庫 MOC"),
    ("prompt injection", "Prompt injection 防禦"),
    ("隔離框", "Prompt injection 防禦"),
    ("健康值代謝", "記憶健康值代謝"),
    ("遺忘曲線", "記憶健康值代謝"),
]


@pytest.fixture()
def env(tmp_path):
    vault = tmp_path / "vault"
    ltm.init_vault(vault)
    idx = tmp_path / "index.db"
    for title, summary, tags in GOLDEN_NOTES:
        nid = ltm.write_note(vault, "semantic", title=title, body=summary,
                             frontmatter={"source": "manual", "tags": tags,
                                          "summary": summary}, ts=TS)
        vindex.upsert(idx, nid, title=title, summary=summary, tags=tags)
    return {"vault": vault, "idx": idx}


def _hit_titles(env, query, k=5):
    hits = retrieve.search(env["vault"], env["idx"], query, limit=k)
    # Hit.note_id 是 id;用 registry 對回 title;或直接讀 note
    titles = []
    for h in hits:
        note = ltm.read_note(env["vault"], _path_of(env["vault"], h.note_id))
        if note:
            titles.append(note["frontmatter"].get("title", ""))
    return titles


def _path_of(vault, note_id):
    for e in ltm.registry_entries(vault):
        if e["id"] == note_id:
            return e["path"]
    return f"semantic/{note_id}.md"


@pytest.mark.parametrize("query,expected", GOLDEN_QUERIES)
def test_golden_query_hits_expected(env, query, expected):
    """每條 golden query 的 expected note 必在 top-5。"""
    titles = _hit_titles(env, query, k=5)
    assert any(expected in t for t in titles), \
        f"query {query!r} expected {expected!r} in top-5, got {titles}"


def test_harness_count():
    """守衛:確保種子/斷言數量達 backlog-007 下限（15 筆記 / 20 斷言）。"""
    assert len(GOLDEN_NOTES) >= 15
    assert len(GOLDEN_QUERIES) >= 20


def test_harness_discriminates(env):
    """負向:一個庫中不存在的主題不應命中任何 golden note（證明 harness 有鑑別力）。"""
    titles = _hit_titles(env, "量子密碼學區塊鏈共識演算法", k=5)
    # 不存在的主題:不應命中任何一筆 golden note 的 title
    golden_titles = {n[0] for n in GOLDEN_NOTES}
    assert not any(t in golden_titles for t in titles), \
        f"unrelated query should not hit golden notes, got {titles}"
