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
    # registry 一行(title+summary)不含 'coding' → 靠 FTS tags 欄位進融合池
    hits = retrieve.search(env["vault"], env["idx"], "coding")
    assert hits and hits[0].stage == "rrf"                  # part-004.5:融合結果


def test_stage3_vec_when_fts_misses(env):
    add_note(env, "完全無關標題", "完全無關摘要", vector=vec(0.1))
    hits = retrieve.search(env["vault"], env["idx"], "語意查詢",
                           embed_fn=lambda q: vec(0.11))
    assert hits and hits[0].stage == "rrf"                  # 向量候選經融合輸出


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


# ── part-004.5-slice-003:RRF 融合(Cognis,backlog-024)──────────────────

def H(nid, stage="fts"):
    return retrieve.Hit(nid, f"semantic/{nid}.md", 0.0, stage)


def test_rrf_formula_hand_computed():
    """手算驗證:k=60。A 在兩清單各 rank1 → 2/61;B rank2+rank1 → 1/62+1/61。"""
    fused = retrieve._rrf_fuse([[H("A"), H("B")], [H("B"), H("A")]], k=60)
    scores = {h.note_id: h.score for h in fused}
    assert scores["A"] == pytest.approx(1 / 61 + 1 / 62)
    assert scores["B"] == pytest.approx(1 / 61 + 1 / 62)
    # 同分 → id 字典序穩定
    assert [h.note_id for h in fused] == ["A", "B"]


def test_rrf_cross_list_consensus_wins():
    """兩清單都出現的候選 > 單清單第一名。"""
    fused = retrieve._rrf_fuse([[H("solo"), H("both")], [H("both")]], k=60)
    assert fused[0].note_id == "both"                       # 1/62+1/61 > 1/61
    assert fused[0].stage == "rrf"


def test_rrf_empty_lists():
    assert retrieve._rrf_fuse([[], [], []]) == []


def test_strong_index_hit_short_circuits_no_embed_call(env):
    """≥2 token 命中 → 短路:embed_fn 不被呼叫(零成本路徑保留)。"""
    add_note(env, "向量索引選型", "sqlite-vec 定案結論")
    called = []
    def spy_embed(q):
        called.append(1)
        return vec(0.1)
    hits = retrieve.search(env["vault"], env["idx"], "向量索引 sqlite-vec 定案",
                           embed_fn=spy_embed)
    assert hits and hits[0].stage == "index"                # 短路,非 rrf
    assert called == []                                     # 未打 embedding


def test_weak_index_goes_through_fusion(env):
    """單 token 弱命中(多 token 查詢只中 1)→ 進融合,不短路。"""
    add_note(env, "向量筆記", "只提到向量一詞")
    hits = retrieve.search(env["vault"], env["idx"], "向量 完全無關詞彙")
    assert hits and hits[0].stage == "rrf"


def test_single_token_query_full_hit_short_circuits(env):
    """單 token 查詢:全部 token(=1)命中也算強命中。"""
    add_note(env, "sqlite 筆記", "關於 sqlite 的內容")
    hits = retrieve.search(env["vault"], env["idx"], "sqlite")
    assert hits and hits[0].stage == "index"


def test_fusion_result_heals_sources(env):
    """回血閉環對融合結果生效(非短路路徑)。"""
    from core import health
    eid = stm.event_append(env["db"], "user", "decision", "融合回血測試")
    con = stm.connect(env["db"])
    created = con.execute("SELECT created_at FROM events").fetchone()[0]
    con.close()
    t = created + 21 * 86_400
    health.decay(env["db"], now_ts=t)
    health.to_trash(env["db"], now_ts=t, transcript_dir=env["tdir"])

    nid = ltm.write_note(env["vault"], "semantic", title="標題甲",
                         body="內文", frontmatter={
                             "source": "consolidation", "tags": ["coding"],
                             "summary": "摘要沒有那個詞",
                             "source_ids": [f"evt:{eid}"]}, ts=TS)
    vindex.upsert(env["idx"], nid, title="標題甲", summary="摘要沒有那個詞",
                  tags=["coding"])
    hits = retrieve.search(env["vault"], env["idx"], "coding", db=env["db"])
    assert hits and hits[0].stage == "rrf"
    con = stm.connect(env["db"])
    state = con.execute("SELECT state, health FROM events WHERE id=?", (eid,)).fetchone()
    con.close()
    assert state == ("alive", 1.0)                          # 融合命中也回血
