"""part-003-slice-001:transcript 冷儲存(roundtrip 三模式、.idx 一致性、
月輪替、rebuild_idx 自癒、boundary)。"""

import json

import pytest

from core import transcript

JULY = 1_752_300_000     # 2025-07(本地時區)內的 epoch
AUG = 1_755_000_000      # 下個月


@pytest.fixture()
def tdir(tmp_path):
    return tmp_path / "transcript"


def test_append_and_read_by_ids_roundtrip(tdir):
    transcript.append(tdir, "evt:1", "event_raw", {"summary": "決定了架構"}, JULY)
    transcript.append(tdir, "evt:2", "event_raw", {"summary": "修了 bug"}, JULY + 60)
    entries, missing = transcript.read_by_ids(tdir, ["evt:2", "evt:1", "evt:999"])
    assert [e["entry_id"] for e in entries] == ["evt:2", "evt:1"]   # 保持輸入順序
    assert missing == ["evt:999"]                                    # 缺 id 回報不拋錯
    assert entries[1]["payload"]["summary"] == "決定了架構"


def test_append_unknown_kind_raises(tdir):
    with pytest.raises(ValueError, match="unknown kind"):
        transcript.append(tdir, "evt:1", "bogus", {}, JULY)


def test_monthly_rotation(tdir):
    transcript.append(tdir, "evt:1", "event_raw", {}, JULY)
    transcript.append(tdir, "evt:2", "event_raw", {}, AUG)
    files = sorted(p.name for p in tdir.glob("*.jsonl"))
    assert len(files) == 2                                           # 兩個月檔
    entries, _ = transcript.read_by_ids(tdir, ["evt:1", "evt:2"])   # 跨月讀取
    assert len(entries) == 2


def test_read_by_time_window(tdir):
    transcript.append(tdir, "evt:1", "event_raw", {}, JULY)
    transcript.append(tdir, "evt:2", "event_raw", {}, JULY + 100)
    transcript.append(tdir, "evt:3", "event_raw", {}, AUG)
    hits = transcript.read_by_time(tdir, JULY + 50, AUG + 50)
    assert [e["entry_id"] for e in hits] == ["evt:2", "evt:3"]


def test_read_by_keyword_newest_first_with_limit(tdir):
    transcript.append(tdir, "evt:1", "event_raw", {"summary": "檢索增強生成筆記"}, JULY)
    transcript.append(tdir, "evt:2", "event_raw", {"summary": "無關內容"}, JULY + 1)
    transcript.append(tdir, "evt:3", "sync_raw", {"summary": "又一篇檢索增強"}, AUG)
    hits = transcript.read_by_keyword(tdir, "檢索增強", limit=10)
    assert [e["entry_id"] for e in hits] == ["evt:3", "evt:1"]      # 新月份先
    assert transcript.read_by_keyword(tdir, "檢索增強", limit=1)[0]["entry_id"] == "evt:3"


def test_idx_matches_jsonl(tdir):
    """不變量:.idx 的 offset/length 必須指回正確的 JSONL 行。"""
    for i in range(20):
        transcript.append(tdir, f"evt:{i}", "event_raw", {"n": i, "中": "文"}, JULY + i)
    entries, missing = transcript.read_by_ids(tdir, [f"evt:{i}" for i in range(20)])
    assert missing == [] and [e["payload"]["n"] for e in entries] == list(range(20))


def test_rebuild_idx_after_corruption(tdir):
    transcript.append(tdir, "evt:1", "event_raw", {"a": 1}, JULY)
    transcript.append(tdir, "evt:2", "event_raw", {"a": 2}, JULY + 1)
    month = "2025-07"
    idx = tdir / f"{month}.jsonl.idx"
    assert idx.exists()
    idx.write_text("garbage\tnot\tnumbers\n", encoding="utf-8")     # 毀掉 .idx
    _, missing = transcript.read_by_ids(tdir, ["evt:1"])
    assert missing == ["evt:1"]                                      # 壞 idx → 讀不到
    n = transcript.rebuild_idx(tdir, month)                          # 自癒
    assert n == 2
    entries, missing = transcript.read_by_ids(tdir, ["evt:1", "evt:2"])
    assert missing == [] and len(entries) == 2


def test_rebuild_idx_skips_corrupt_jsonl_lines(tdir):
    transcript.append(tdir, "evt:1", "event_raw", {}, JULY)
    month = "2025-07"
    with open(tdir / f"{month}.jsonl", "a", encoding="utf-8") as f:
        f.write("這不是 JSON\n")                                     # 壞行混入
    transcript.append(tdir, "evt:2", "event_raw", {}, JULY + 1)
    assert transcript.rebuild_idx(tdir, month) == 2                  # 壞行不進 idx
    entries, missing = transcript.read_by_ids(tdir, ["evt:1", "evt:2"])
    assert missing == []


def test_read_from_nonexistent_dir(tdir):
    """boundary:目錄不存在 → 空結果,不拋錯、不建檔。"""
    entries, missing = transcript.read_by_ids(tdir, ["evt:1"])
    assert entries == [] and missing == ["evt:1"]
    assert transcript.read_by_time(tdir, 0, 9_999_999_999) == []
    assert transcript.read_by_keyword(tdir, "x") == []
    assert not tdir.exists()                                         # 讀取不產生副作用


def test_rebuild_idx_nonexistent_month(tdir):
    assert transcript.rebuild_idx(tdir, "1999-01") == 0
