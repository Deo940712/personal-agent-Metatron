"""part-003-slice-003:vindex(FTS/vec/rebuild)+ retrieve 四段級聯 + 回血閉環。
embedding 全 mock(固定向量);sqlite-vec 真載入(本機已驗)。"""

import pytest

import config
from core import health, ltm, retrieve, stm, transcript, vindex

TS = 1_752_300_000
DIM = config.EMBED_DIM


def vec(seed: float) -> list[float]:
    """確定性假向量:第一維 = seed,其餘 0。距離 = |seed差|。"""
    v = [0.0] * DIM
    v[0] = seed
    return v


@pytest.fixture()
def env(tmp_path):
    vault = tmp_path / "vault"
    ltm.init_vault(vault)
    idx = tmp_path / "index.db"
    db = tmp_path / "state.db"
    stm.init(db)
    return {"vault": vault, "idx": idx, "db": db, "tdir": tmp_path / "transcript"}


def add_note(env, title, summary, tags=("daily-log",), source_ids=None, vector=None):
    nid = ltm.write_note(env["vault"], "episodic", title=title, body=summary,
                         frontmatter={"source": "consolidation", "tags": list(tags),
                                      "summary": summary,
                                      **({"source_ids": source_ids} if source_ids else {})},
                         ts=TS)
    vindex.upsert(env["idx"], nid, title=title, summary=summary,
                  tags=list(tags), vector=vector)
    return nid


# ── vindex ───────────────────────────────────────────────────────────

def test_fts_match_chinese_3plus_chars(env):
    add_note(env, "檢索增強生成筆記", "RAG 的各種做法")
    hits = vindex.search_fts(env["idx"], "檢索增強")
    assert hits and hits[0][0].endswith("檢索增強生成筆記")


def test_fts_like_fallback_2char_chinese(env):
    """P4:2 字中文 MATCH 不到 → LIKE 降級。"""
    add_note(env, "檢索增強生成筆記", "RAG 做法")
    hits = vindex.search_fts(env["idx"], "檢索")
    assert len(hits) == 1 and hits[0][1] == 0.0            # LIKE 無排名


def test_fts_english(env):
    add_note(env, "RAG techniques", "retrieval augmented generation")
    assert vindex.search_fts(env["idx"], "retrieval")


def test_fts_empty_query(env):
    assert vindex.search_fts(env["idx"], "  ") == []


def test_vec_knn_order(env):
    a = add_note(env, "近的", "s", vector=vec(0.1))
    b = add_note(env, "遠的", "s2", vector=vec(0.9))
    hits = vindex.search_vec(env["idx"], vec(0.12), k=2)
    assert [h[0] for h in hits] == [a, b]                  # 距離排序


def test_upsert_replaces(env):
    """P2:同 note_id 再 upsert = DELETE+INSERT,不炸也不重複。"""
    nid = add_note(env, "原標題", "原摘要", vector=vec(0.1))
    vindex.upsert(env["idx"], nid, title="新標題", summary="新摘要",
                  tags=["daily-log"], vector=vec(0.5))
    hits = vindex.search_fts(env["idx"], "新摘要")
    assert len(hits) == 1
    assert vindex.search_vec(env["idx"], vec(0.5), k=1)[0][0] == nid


def test_pack_vector_dim_guard():
    with pytest.raises(ValueError, match="dim"):
        vindex.pack_vector([0.1, 0.2])


def test_rebuild_equivalence(env):
    """衍生物哲學:整檔刪除重建後 FTS 查詢結果等價。"""
    add_note(env, "重建測試甲", "第一篇")
    add_note(env, "重建測試乙", "第二篇")
    before = {h[0] for h in vindex.search_fts(env["idx"], "重建測試")}
    n = vindex.rebuild(env["idx"], env["vault"], embed_fn=None)
    assert n == 2
    after = {h[0] for h in vindex.search_fts(env["idx"], "重建測試")}
    assert before == after
    assert vindex.get_meta(env["idx"], "embed_model") == config.EMBED_MODEL


# ── retrieve 四段級聯 ─────────────────────────────────────────────────

def test_stage1_index_first_hits_registry(env):
    add_note(env, "sqlite-vec 定案", "向量索引選型結論")
    hits = retrieve.search(env["vault"], env["idx"], "向量索引")
    assert hits and hits[0].stage == "index"               # 第一段就命中


def test_stage2_fts_when_index_misses(env):
    add_note(env, "標題甲", "摘要沒有那個詞", tags=("coding",))
    # registry 一行(title+summary)不含 'coding' 中文比對 → 落到 FTS tags 欄位
    hits = retrieve.search(env["vault"], env["idx"], "coding")
    assert hits and hits[0].stage == "fts"


def test_stage3_vec_when_fts_misses(env):
    add_note(env, "完全無關標題", "完全無關摘要", vector=vec(0.1))
    hits = retrieve.search(env["vault"], env["idx"], "語意查詢",
                           embed_fn=lambda q: vec(0.11))
    assert hits and hits[0].stage == "vec"


def test_all_miss_returns_empty(env):
    add_note(env, "某筆記", "某摘要")
    assert retrieve.search(env["vault"], env["idx"], "zzzqqq") == []


def test_no_embed_fn_skips_vec(env):
    add_note(env, "無關", "無關", vector=vec(0.1))
    assert retrieve.search(env["vault"], env["idx"], "zzzqqq", embed_fn=None) == []


# ── 回血閉環 + rehydrate ─────────────────────────────────────────────

@pytest.fixture()
def full_env(env):
    """真實鏈:event → trash(落地 transcript)→ 筆記帶 source_ids。"""
    eid = stm.event_append(env["db"], "user", "decision", "選了 sqlite-vec")
    con = stm.connect(env["db"])
    created = con.execute("SELECT created_at FROM events").fetchone()[0]
    con.close()
    t = created + 21 * 86_400
    health.decay(env["db"], now_ts=t)
    health.to_trash(env["db"], now_ts=t, transcript_dir=env["tdir"])
    add_note(env, "向量索引定案", "選了 sqlite-vec 當索引",
             source_ids=[f"evt:{eid}"])
    env["eid"] = eid
    return env


def test_hit_heals_source_events(full_env):
    con = stm.connect(full_env["db"])
    before = con.execute("SELECT health, state FROM events").fetchone()
    con.close()
    assert before[1] == "trash"

    hits = retrieve.search(full_env["vault"], full_env["idx"], "向量索引",
                           db=full_env["db"])
    assert hits
    con = stm.connect(full_env["db"])
    after = con.execute("SELECT health, state FROM events").fetchone()
    con.close()
    assert after == (1.0, "alive")                         # 命中 → 回血 + 復活


def test_rehydrate_reads_raw_text(full_env):
    hits = retrieve.search(full_env["vault"], full_env["idx"], "向量索引")
    raw = retrieve.rehydrate(full_env["vault"], hits[0].path,
                             transcript_dir=full_env["tdir"])
    assert raw and "sqlite-vec" in raw[0]["payload"]["summary"]   # 原文讀回


def test_rehydrate_note_without_sources(env):
    add_note(env, "無來源筆記", "手寫的")
    hits = retrieve.search(env["vault"], env["idx"], "無來源")
    assert retrieve.rehydrate(env["vault"], hits[0].path,
                              transcript_dir=env["tdir"]) == []
