# DONE: part-004.5-slice-001 主題連續性蒸餾（Membox）

Completed: 2026-07-13
Design authority: `.beacon/parts/part-004.5/DESIGN.md`

## 交付物

- `agents/consolidator.md`：輸出 schema 加 `topic`（必填≤30字）+ few-shot 示範
- `core/consolidate.py`：
  - `_validate_group` 第六條（topic 空/超長/None 拒絕）
  - `_link_same_topic`：近 30 天同 topic 的既有 episodic 筆記雙向補 related
    （不引入獨立 trace 結構，純 frontmatter 字串比對，零新模組）
  - `_add_related`：related list 補一筆去重（冪等）
- `tests/test_consolidate.py` 新增 8 個測試（topic boundary/跨天連結/不同主題不連結/
  直接函數測試/時間窗外不連結）+ 既有 fixtures 補 topic 欄位

## Verification Evidence

- `python -m pytest tests/test_consolidate.py -q` → **30 passed**
- `python -m pytest tests/ -q` → **262 passed**（254 既有迴歸不壞）

## Audit gate（4 探針,全 clean）

- T1：topic 30 字通過、31 字拒絕（邊界精確）
- T2：preference 類筆記（agent/profile/）不會被 episodic 連結掃描誤觸
- T3：同批次兩組同主題 → 確實互相連結（設計預期行為，非缺陷）
- T4：重複呼叫 `_link_same_topic` 冪等（第二次 linked=0）

## 移交

- topic 是自由文字，同義不同字（「RAG」vs「檢索增強」）不會連結——已知限制，
  精確 clustering 需 embedding 比對，本輪不做（DESIGN 已記錄）
