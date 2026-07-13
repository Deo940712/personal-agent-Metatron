# DONE: part-004.5-slice-002 矛盾偵測 + supersede 執行（Mneme）

Completed: 2026-07-13
Design authority: `.beacon/parts/part-004.5/DESIGN.md`

## 交付物

- `agents/consolidator.md`：preference 蒸餾輸入注入「既有偏好清單」（漸進揭露）；
  輸出可選 `supersedes` 欄位（只能填清單中實際 id）+ 矛盾情境 few-shot
- `core/consolidate.py`：
  - `_existing_profile_index`：既有 profile 的 INDEX 一行描述 + id 集合
    （已 superseded 的排除——不疊舊鏈）
  - `_validate_supersedes`（第七條）：只允許 preference kind、必須真實存在、
    非已 superseded；同批次已用掉的 id 即時移出集合
  - 落地：新筆記帶 supersedes → `ltm.mark_superseded` 舊筆記補 superseded_by
    （雙側保留：不刪、不改內容）
- `core/ltm.py`：`mark_superseded`（registry 查路徑；已標記過 → False 冪等守衛）
- `agents/recall.md`：superseded_by 查詢規則（優先讀新版；矛盾並列不擅斷）
- `core/recall.py`：read_note 工具結果附 `_superseded_by_note` 提示

## Verification Evidence

- `python -m pytest tests/test_consolidate.py tests/test_recall.py -q` → 53 passed
- `python -m pytest tests/ -q` → **273 passed**

覆蓋：supersede 落地雙側保留（新帶 supersedes/舊補 superseded_by/內容不動）、
prompt 注入既有清單、虛構/空/已 superseded 目標拒絕、mark 冪等、幽靈 registry、
**U2 episodic 繞過漏洞**、recall 工具提示（有/無 superseded_by 兩路）。

## Audit gate

U2 真漏洞（驗證與執行不對稱）當場修；U1/U3/U4 clean。詳 KNOWN_ISSUES.md。
