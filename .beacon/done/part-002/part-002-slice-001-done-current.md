# DONE: part-002-slice-001 writer.py + 提案驗證 + 閘門

Completed: 2026-07-13
Design authority: `.beacon/parts/part-002/DESIGN.md`(規則權威:ARCHITECTURE §3.1/§3.2)

## 交付物

- `core/proposals.py` — 信封 dataclass + parse_envelope + payload 驗證
  (schedule_change/task_change;action enum、欄位白名單、epoch int 型別、
  rrule 確定性驗證 DAILY/WEEKLY 子集)+ needs_confirmation(規則 7)
- `core/writer.py` — apply(proposal, confirm_fn, db):
  - §3.1 驗證:信封/enum/confidence(規則 5)、target 存在(規則 1)、
    evidence 非空(規則 3)、拒絕必記 events(規則 6)、寫入類需確認(規則 7)
  - §3.2 閘門:需確認 → 預覽(時間格式化)→ confirm_fn;
    **confirm_fn=None(非互動)fail-closed**;使用者拒絕不落地
  - 落地:add/update/done/cancel → stm CRUD + INSERT events(state_change)
  - update 只改給定欄位;tasks cancel → archived(tasks 無 cancelled 狀態)
- `tests/test_writer.py` — 21 個測試

## Verification Evidence

Automated commands:
- command: `python -m pytest tests/test_writer.py -q` → **21 passed**
- command: `python -m pytest tests/ -q` → **49 passed**(28 既有迴歸不壞)

覆蓋:信封缺欄/未知 agent/confidence 界外/未知 proposal_type/非法 action(含
delete——物理刪除在 enum 層就不可能)/未知欄位/壞 rrule;target 不存在;
evidence 空;確認流(拒絕不落地、非互動 fail-closed、done 免確認、預覽含可讀時間);
落地(add/update 部分更新/cancel 雙表)+ 每次拒絕都記 events。

Manual QA: 無(純程式邏輯,依 TODO 規劃)

Incidents: none

## 設計筆記(移交 slice-002/003)

- 規則 2(tags 詞彙表)與規則 3 的逐字比對屬 vault 類提案,part-003 加入
  PAYLOAD_VALIDATORS 時實作——目前 evidence 僅驗非空(schedule 的 evidence
  = 使用者原句,slice-003 orchestrator 負責帶入)
- confirm_fn 介面已為 Discord 按鈕(part-002.5)預留:同一簽名換實作
