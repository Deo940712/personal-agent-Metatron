# part-011-slice-000 — 作息迴圈接線(done 2026-07-19)

Snapshot of CURRENT at completion.

## Goal(達成)

補完 routine 迴圈根因(todo 1-4):完成事件 → extract_routine → routine facet →
advisor 偏離偵測 → 建議。死程式碼 `extract_routine` 從此有 caller。

## Delivered

- **todo 1** `core/writer.py`:done → `completed` 事件(actor='user')+ transcript
  entry(evt:<id>,durable source_id);cancel 不寫;state_change 保留。
  `_item_title` + `_record_completed` 輔助。(tests/test_completed_event.py:5)
- **todo 2** `core/consolidate.py`:`run_routine_producer` + `_completed_in_window`
  (讀近 14 天 alive+trash completed 事件——**關鍵:completed 會被代謝進 trash,
  故 window-read 非只讀 alive**);extract_routine → routine facet via writer;
  evidence 指向 transcript source_id(durable);掛 `run` 尾端(與代謝同跑)。
  (tests/test_routine_producer.py:5)
- **todo 3-4** `tests/test_routine_loop.py`:端到端鎖定(completed→facet→deviation
  →advice);advisor 既有邏輯已正確讀 completed 事件,無需改碼(3 tests)。

## Verification

- Unit: routine_producer(5)+ completed_event(5)+ routine_loop(3)= 13 new, all green
- Regression: `python -m pytest tests/ -q` → **820 passed**(基線 807 + 13)
- Manual QA(實跑):真 `consolidate.run` → routine_facet=True → 學到 morning
  routine facet(evidence_count=1)。死程式碼確認復活。

## 關鍵設計決定(gap 分析 G1)

`completed` 事件是普通 alive 事件——verified core/health.py:decay + due_for_distill
會代謝/蒸餾它。因此:
- producer window-read(alive + trash),與蒸餾同跑(掛 consolidate 尾端,非獨立
  job——獨立 job 會跟代謝賽跑)
- routine evidence 指向 transcript source_id(永久,事件歸檔後仍可回水)
- 接受 completed 也成 episodic 筆記(不同記憶層,非重複計算)
