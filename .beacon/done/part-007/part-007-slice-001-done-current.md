# part-007-slice-001 — profile_facet 提案 + writer 落地 + supersede(done 2026-07-19)

Snapshot of CURRENT at completion.

## Goal(達成)

`profile_facet` proposal type + writer 驗證落地路徑 + 矛盾 supersede 執行。

## Delivered

- `core/proposals.py`:`validate_profile_facet`(action/class/key/value/
  evidence_ids/supersedes_id 結構驗證,bool 陷阱防禦)+ 確認政策
  (create/reinforce 免確認;supersede 需確認,§3.2 閘門)+ consolidator 進
  KNOWN_AGENTS
- `core/writer.py`:`apply_facet`——evidence_ids 逐條驗證存在於 transcript
  (不得虛構來源);create 防重複 active;reinforce 內建 detector 就地升級;
  supersede 走 mark → insert → link 三步(釋放 unique active 槽),Mneme 防線
  (目標真實/active/未被取代/非 pinned/class+key 相符);precheck 加
  `facet:<class>/<key>` 定址驗證;apply_validated dispatch
- `core/stm.py`:`facet_supersede_mark` + `facet_link_supersede` 兩步原語
- `tests/test_facets_writer.py`:16 tests(三 action 落地/五類拒絕/確認政策/
  fail-closed/events 記錄)

## Verification

- Unit: `python -m pytest tests/test_facets_writer.py -q` → 16 passed
- Regression: `python -m pytest tests/ -q` → **672 passed**(基線 656 + 16)
- Manual QA: 手組 proposal dict → writer.apply → `facets list` 顯示 provisional;
  偽造 evidence_ids → rejected(實跑證據見對話記錄)

## Notes

- transcript.read_by_ids 回傳 (entries, missing) tuple——實作時修正初版誤用。
- supersede 非同交易(mark → insert → link 順序保證);insert 失敗時舊 facet
  已標 superseded,由 events 可稽核。個人量級接受此設計,未引入交易包裝。
