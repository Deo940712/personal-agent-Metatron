"""冷儲存 transcript(docs/MEMORY-zh.md §2;ARCHITECTURE §5.3)。

append-only JSONL + byte-offset .idx,按月輪替。JSONL 是唯一真相,
.idx 是衍生物(壞掉用 rebuild_idx 重建)。

不變量:
1. append-only——任何函式不得改寫既有行;無 delete API
2. 寫入順序:先 JSONL flush,再 .idx——中斷最壞 = .idx 少行(可重建)
3. entry_id 命名空間:evt:<events.id> | raw:<pipeline>:<post_id>
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import config

KINDS = ("event_raw", "sync_raw", "llm_io")


def _month_of(ts: int) -> str:
    return datetime.fromtimestamp(ts).strftime("%Y-%m")


def _paths(base_dir: Path, month: str) -> tuple[Path, Path]:
    jsonl = base_dir / f"{month}.jsonl"
    return jsonl, jsonl.with_suffix(".jsonl.idx")


def append(base_dir: Path | None, entry_id: str, kind: str, payload: dict,
           ts: int) -> str:
    """寫一筆。回傳 entry_id。kind 非法 → ValueError(呼叫端程式錯,fail fast)。"""
    if kind not in KINDS:
        raise ValueError(f"unknown kind: {kind!r} (allowed: {KINDS})")
    base = base_dir or config.TRANSCRIPT_DIR
    base.mkdir(parents=True, exist_ok=True)
    jsonl_path, idx_path = _paths(base, _month_of(ts))

    line = json.dumps({"entry_id": entry_id, "ts": ts, "kind": kind,
                       "payload": payload}, ensure_ascii=False) + "\n"
    data = line.encode("utf-8")

    # 不變量 2:先 JSONL(flush 落地)再 .idx
    with open(jsonl_path, "ab") as f:
        offset = f.tell()
        f.write(data)
        f.flush()
    with open(idx_path, "a", encoding="utf-8") as f:
        f.write(f"{entry_id}\t{offset}\t{len(data)}\n")
    return entry_id


def _load_idx(idx_path: Path) -> dict[str, tuple[int, int]]:
    """entry_id → (offset, length)。壞行跳過(JSONL 才是真相)。"""
    table: dict[str, tuple[int, int]] = {}
    if not idx_path.exists():
        return table
    with open(idx_path, encoding="utf-8") as f:
        for line in f:
            parts = line.rstrip("\n").split("\t")
            if len(parts) == 3 and parts[1].isdigit() and parts[2].isdigit():
                table[parts[0]] = (int(parts[1]), int(parts[2]))
    return table


def _months(base: Path) -> list[str]:
    return sorted(p.stem for p in base.glob("*.jsonl"))


def read_by_ids(base_dir: Path | None,
                entry_ids: list[str]) -> tuple[list[dict], list[str]]:
    """O(1) seek 經 .idx。回傳 (找到的 entries, 缺的 ids)——缺 id 回報不拋錯。"""
    base = base_dir or config.TRANSCRIPT_DIR
    wanted = set(entry_ids)
    found: dict[str, dict] = {}
    if base.exists():
        for month in _months(base):
            if not wanted:
                break
            jsonl_path, idx_path = _paths(base, month)
            idx = _load_idx(idx_path)
            hits = wanted & idx.keys()
            if not hits:
                continue
            with open(jsonl_path, "rb") as f:
                for eid in hits:
                    offset, length = idx[eid]
                    f.seek(offset)
                    try:
                        found[eid] = json.loads(f.read(length).decode("utf-8"))
                    except (json.JSONDecodeError, UnicodeDecodeError):
                        continue  # .idx 過期指錯位 → 當缺;rebuild_idx 可修
            wanted -= found.keys()
    # 保持輸入順序
    entries = [found[e] for e in entry_ids if e in found]
    missing = [e for e in entry_ids if e not in found]
    return entries, missing


def read_by_time(base_dir: Path | None, start_ts: int,
                 end_ts: int) -> list[dict]:
    """線性掃時間範圍(月檔內 ts 有序;跨月合併)。"""
    base = base_dir or config.TRANSCRIPT_DIR
    out: list[dict] = []
    if not base.exists():
        return out
    lo, hi = _month_of(start_ts), _month_of(end_ts)
    for month in _months(base):
        if not (lo <= month <= hi):
            continue
        jsonl_path, _ = _paths(base, month)
        with open(jsonl_path, encoding="utf-8") as f:
            for line in f:
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue  # 壞行跳過,不炸全檔
                if start_ts <= entry.get("ts", -1) <= end_ts:
                    out.append(entry)
    return out


def read_by_keyword(base_dir: Path | None, keyword: str,
                    limit: int = 50) -> list[dict]:
    """全檔線性掃(新→舊)。實測 10k 行 17ms,個人量級足夠(MEMORY §8)。"""
    base = base_dir or config.TRANSCRIPT_DIR
    out: list[dict] = []
    if not base.exists():
        return out
    for month in reversed(_months(base)):
        jsonl_path, _ = _paths(base, month)
        with open(jsonl_path, encoding="utf-8") as f:
            for line in f:
                if keyword in line:
                    try:
                        out.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
                    if len(out) >= limit:
                        return out
    return out


def rebuild_idx(base_dir: Path | None, month: str) -> int:
    """.idx 從 JSONL 全量重掃(中斷自癒)。回傳筆數。"""
    base = base_dir or config.TRANSCRIPT_DIR
    jsonl_path, idx_path = _paths(base, month)
    if not jsonl_path.exists():
        idx_path.unlink(missing_ok=True)
        return 0
    rows: list[str] = []
    with open(jsonl_path, "rb") as f:
        offset = 0
        for raw in f:
            try:
                eid = json.loads(raw)["entry_id"]
                rows.append(f"{eid}\t{offset}\t{len(raw)}")
            except (json.JSONDecodeError, KeyError, UnicodeDecodeError):
                pass  # 壞行不進 idx
            offset += len(raw)
    idx_path.write_text("\n".join(rows) + ("\n" if rows else ""), encoding="utf-8")
    return len(rows)
